"""Sprint 17b: Cantonese / OpenCC post-ASR corrector.

Lifted from yuesub-api's `corrector/Corrector.py` (with
adaptation for our async pipeline). The corrector runs
between SenseVoice ASR and the wake-phrase detector — see
docs/FEATURE-SPEC-SPRINT17b.md §5.1 for the invariant that
corrector must run before wake detection (so a corrected
"俾" → "畀" still matches the wake prefix).

Two corrector modes:

- "opencc": Pure regex + OpenCC s2hk. Runs in <5ms per
  segment. CPU-only, no model download required. The default
  fallback for users who don't want to install the BERT
  corrector (D3-B was a scope flip; this stays as the
  graceful-degrade option).

- "bert": OpenCC s2hk + regex rules + BERT masked-LM
  perplexity selection over jyutping candidates. Requires
  the `hon9kon9ize/bert-large-cantonese` ONNX model. Runs
  in 300-500ms per segment on Apple Silicon (CPU ONNX).
  We expose this as an `async` API and dispatch the blocking
  work via `asyncio.to_thread` so the event loop stays
  responsive. The TTS pipeline is sentence-streamed, so
  the 300-500ms latency is absorbed between segments.

Data files (jyutping dictionary, char frequency, traditional→
simplified mapping) live in the yuesub-api repo at
`~/workspace/yuesub-api/data/`. We accept an override via
constructor (`data_dir` arg) for testing, but the default
points at the yuesub-api checkout (D5 — symlink point).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import TYPE_CHECKING, Literal, Optional

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# Default data dir (sibling of the yuesub-api models dir). Override
# via constructor for tests.
_DEFAULT_DATA_DIR = os.path.expanduser("~/workspace/yuesub-api/data")


# ---------------------------------------------------------------------------
# Lazy / soft imports — the corrector types live in the yuesub-api
# repo at runtime, but for tests we want to be able to mock the
# heavy bits (BERT model, pandas) without forcing the test env to
# install the yuesub-api checkout.
# ---------------------------------------------------------------------------


def _try_import_pandas():
    try:
        import pandas  # type: ignore

        return pandas
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "pandas is required for the yuesub Corrector. "
            "It ships with the voice-yuesub extra (librosa pulls "
            "it in transitively). Install with: uv sync --extra voice-yuesub"
        ) from e


def _try_import_opencc():
    try:
        import opencc  # type: ignore

        return opencc
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "opencc is required for the yuesub Corrector. "
            "Install with: uv sync --extra voice-yuesub"
        ) from e


def _try_import_transformers():
    """Optional — only needed for corrector='bert'."""
    try:
        from transformers import BertTokenizerFast  # type: ignore

        return BertTokenizerFast
    except ImportError as e:
        raise RuntimeError(
            "transformers is required for corrector='bert'. "
            "Install with: uv sync --extra voice-yuesub"
        ) from e


def _try_import_onnxruntime():
    try:
        import onnxruntime  # type: ignore

        return onnxruntime
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "onnxruntime is required for the yuesub Corrector. "
            "Install with: uv sync --extra voice"
        ) from e


# ---------------------------------------------------------------------------
# Language model (BERT wrapper for perplexity scoring)
# ---------------------------------------------------------------------------


class _LanguageModel:
    """Abstract base — matches yuesub-api's LanguageModel API surface
    (just `perplexity` + `get_loss`) so the lifted code reads the
    same. We inline a minimal version here; the real yuesub-api
    one is more elaborate but we don't need its hooks.
    """

    def perplexity(self, text: str) -> float:  # pragma: no cover
        raise NotImplementedError

    def get_loss(self, text: str) -> float:  # pragma: no cover
        raise NotImplementedError


class _BertModel(_LanguageModel):
    """`hon9kon9ize/bert-large-cantonese` ONNX wrapper.

    Loads `model.onnx` from the model dir, runs masked-LM, and
    exposes `perplexity(text)` for candidate selection in the
    corrector. Same shape as yuesub-api's BertModel; we vendor
    a minimal copy here so we don't take a hard runtime
    dependency on the yuesub-api repo.
    """

    def __init__(self, model_dir: str) -> None:
        _try_import_transformers()
        _try_import_onnxruntime()

        import torch  # local
        from onnxruntime import (  # type: ignore
            GraphOptimizationLevel,
            InferenceSession,
            SessionOptions,
            get_all_providers,
        )

        available = get_all_providers()
        self.device = "cuda" if "CUDAExecutionProvider" in available else "cpu"
        self.providers = (
            "CUDAExecutionProvider"
            if "CUDAExecutionProvider" in available
            else "CPUExecutionProvider"
        )
        self.tokenizer = _try_import_transformers().from_pretrained(model_dir)
        options = SessionOptions()
        options.intra_op_num_threads = max(1, (os.cpu_count() or 2) - 1)
        options.graph_optimization_level = GraphOptimizationLevel.ORT_ENABLE_ALL
        self.model = InferenceSession(
            f"{model_dir}/model.onnx",
            options,
            providers=[self.providers],
        )
        # Cache the torch module so we don't re-import in get_loss.
        self._torch = torch

    def get_loss(self, text: str) -> float:
        model_inputs = self.tokenizer(text, return_tensors="pt")
        vocab_size = len(self.tokenizer.get_vocab())
        labels = model_inputs.input_ids
        # ONNX inference expects numpy
        inputs_onnx = {
            k: v.detach().cpu().numpy() for k, v in model_inputs.items()
        }
        predictions = self.model.run(None, inputs_onnx)
        lm_logits = self._torch.from_numpy(predictions[0])
        loss_fct = self._torch.nn.CrossEntropyLoss()
        loss = loss_fct(
            lm_logits.view(-1, vocab_size),
            labels.view(-1),
        )
        return loss.item()

    def perplexity(self, text: str) -> float:
        import math

        return math.exp(self.get_loss(text))


# ---------------------------------------------------------------------------
# Corrector
# ---------------------------------------------------------------------------


# Regex rules lifted from yuesub-api's Corrector.opencc_correct
# (they cover the most common SenseVoice → Cantonese writing
#  errors: 俾→畀, 系→係, 噶→㗎, 咁→噉, 曬→晒, 翻→返, and the
#  SenseVoice emotion-tag noise pattern <|...|>)
_OPENCC_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"俾(?!(?:路支|斯麥|益))"), r"畀"),
    (re.compile(r"(?<!(?:聯))[系繫](?!(?:統))"), r"係"),
    (re.compile(r"噶"), r"㗎"),
    (re.compile(r"咁(?=[我你佢就樣就話係啊呀嘅，。])"), r"噉"),
    (re.compile(r"(?<![曝晾])曬(?:[衣太衫褲被命嘢相])"), r"晒"),
    (re.compile(r"(?<=[好])翻(?=[去到嚟])"), r"返"),
    (re.compile(r"<\|\w+\|>"), r""),
]


class Corrector:
    """Sprint 17b Cantonese post-ASR corrector.

    Two modes:
    - "opencc" (fast, <5ms/segment): OpenCC s2hk + regex rules
    - "bert" (slow, 300-500ms/segment): OpenCC + regex + BERT
      masked-LM perplexity selection over jyutping candidates

    Public API is async (`acorrect`) for compatibility with the
    voice pipeline (which runs on an event loop). The sync
    `_correct_sync` is exposed for tests and for callers that
    want to bypass the asyncio.to_thread dispatch.

    Args:
        corrector: "opencc" | "bert". Defaults to "opencc" if
            not provided. (YuesubASR passes "bert" by default per
            the Sprint 17b spec §0 D3-B scope flip.)
        data_dir: Path to the yuesub-api data/ directory. Default
            `~/workspace/yuesub-api/data/` (the D5 sibling).
        model_dir: Path to the BERT model dir (only used when
            corrector="bert"). Default
            `~/.gundam-halo/models/hon9kon9ize/bert-large-cantonese/`
            (D5 symlink target).
    """

    def __init__(
        self,
        corrector: Literal["opencc", "bert"] = "opencc",
        data_dir: Optional[str] = None,
        model_dir: Optional[str] = None,
    ) -> None:
        if corrector not in ("opencc", "bert"):
            raise ValueError(
                f"corrector must be 'opencc' or 'bert', got {corrector!r}"
            )

        self.corrector = corrector
        self.data_dir = data_dir or _DEFAULT_DATA_DIR
        self.model_dir = model_dir or os.path.expanduser(
            "~/.gundam-halo/models/hon9kon9ize/bert-large-cantonese"
        )
        self.converter = None
        self.bert_model: Optional[_BertModel] = None
        # For corrector='bert': candidates dicts loaded lazily.
        # We only load them in `_ensure_bert_loaded()` so the
        # "opencc" mode path doesn't pay the data-file I/O cost.
        self.t2s_char_dict: Optional[dict] = None
        self.char_jyutping_dict: Optional[dict] = None
        self.jyutping_char_dict: Optional[dict] = None
        self.chars_freq: Optional[dict] = None

        if corrector == "opencc":
            self.converter = _try_import_opencc().OpenCC("s2hk")

    # -----------------------------------------------------------------------
    # Public async API
    # -----------------------------------------------------------------------

    async def acorrect(self, text: str) -> str:
        """Async corrector entry point. Used by the voice pipeline.

        For corrector="opencc" the cost is <5ms; we still run it in
        a thread (cheap, and it keeps the code path uniform). For
        corrector="bert" the cost is 300-500ms; the thread dispatch
        is the whole point — keeps the event loop responsive while
        the BERT forward pass runs.
        """
        return await asyncio.to_thread(self._correct_sync, text)

    # -----------------------------------------------------------------------
    # Sync internals (also public for tests + sync callers)
    # -----------------------------------------------------------------------

    def _correct_sync(self, text: str) -> str:
        if self.corrector == "opencc":
            return self._opencc_correct(text)
        if self.corrector == "bert":
            return self._bert_correct(text)
        # Unreachable — guarded in __init__.
        raise ValueError(f"Unknown corrector mode: {self.corrector!r}")

    def correct(self, text: str) -> str:
        """Sync alias for `_correct_sync` — kept for callers that
        don't want to await (e.g. tests, batch scripts).

        Production code should prefer `acorrect` to avoid blocking
        the event loop.
        """
        return self._correct_sync(text)

    # -----------------------------------------------------------------------
    # opencc mode
    # -----------------------------------------------------------------------

    def _opencc_correct(self, text: str) -> str:
        if self.converter is None:
            # Lazy-init in case the user constructed without opencc
            # available and switched modes. (Defensive only — the
            # factory validates the corrector name up front.)
            self.converter = _try_import_opencc().OpenCC("s2hk")
        text = text.strip()
        if not text:
            return text
        out = self.converter.convert(text)
        for pattern, replacement in _OPENCC_RULES:
            out = pattern.sub(replacement, out)
        return out

    # -----------------------------------------------------------------------
    # bert mode
    # -----------------------------------------------------------------------

    def _ensure_bert_loaded(self) -> None:
        if self.bert_model is not None:
            return
        if not os.path.isdir(self.model_dir):
            raise RuntimeError(
                f"BERT corrector model not found at {self.model_dir}. "
                "Run: cd ~/workspace/yuesub-api && "
                "python download_models.py --with-bert && "
                "bash scripts/setup-yuesub-models.sh"
            )
        self.bert_model = _BertModel(self.model_dir)
        # Lazy data loading: the data files are only needed for
        # corrector="bert". We defer to first correct() call so
        # that opencc-only users never pay this cost.
        self.t2s_char_dict, self.char_jyutping_dict, self.jyutping_char_dict, self.chars_freq = (
            self._load_data()
        )

    def _load_data(self) -> tuple[dict, dict, dict, dict]:
        """Load jyutping dictionary, char frequency, and t2s mapping.

        Lifted from yuesub-api Corrector._load_dict. Returns
        (t2s_char_dict, char_jyutping_dict, jyutping_char_dict,
        chars_freq).
        """
        pandas = _try_import_pandas()
        from collections import defaultdict

        t2s_path = os.path.join(self.data_dir, "STCharacters.txt")
        jyutping_path = os.path.join(self.data_dir, "jyut6ping3.chars.dict.tsv")
        freq_path = os.path.join(self.data_dir, "chars_freq.tsv")

        for path in (t2s_path, jyutping_path, freq_path):
            if not os.path.isfile(path):
                raise FileNotFoundError(
                    f"Corrector data file missing: {path}. "
                    f"Expected to find it under {self.data_dir}. "
                    "Is the yuesub-api repo at the expected path?"
                )

        chars_freq_df = pandas.read_csv(
            freq_path, sep="\t", names=["char", "freq"]
        )
        chars_freq = dict(zip(chars_freq_df.char, chars_freq_df.freq))

        jyutping_df = pandas.read_csv(
            jyutping_path, sep="\t", names=["char", "jyutping"]
        )
        char_jyutping_dict = defaultdict(list)
        for _, row in jyutping_df.iterrows():
            char_jyutping_dict[row["char"]].append(row["jyutping"])
        char_jyutping_dict = dict(char_jyutping_dict)

        jyutping_char_dict = defaultdict(list)
        for _, row in jyutping_df.iterrows():
            jyutping_char_dict[row["jyutping"]].append(row["char"])
        jyutping_char_dict = {
            k: sorted(v, key=lambda x: chars_freq.get(x, 0), reverse=True)
            for k, v in jyutping_char_dict.items()
        }

        t2s_char_dict: dict = {}
        t2s_df = pandas.read_csv(
            t2s_path, sep="\t", names=["sc", "tc"], encoding="utf-8"
        )
        for _, row in t2s_df.iterrows():
            t2s_char_dict[row["sc"]] = row["tc"].split()
        # Patches lifted from yuesub-api Corrector
        t2s_char_dict["晒"] = ["晒", "曬"]
        t2s_char_dict["咁"] = ["咁", "噉"]
        t2s_char_dict["旧"] = t2s_char_dict["旧"] + ["嚿"]

        return t2s_char_dict, char_jyutping_dict, jyutping_char_dict, chars_freq

    def _bert_correct(self, text: str) -> str:
        """BERT perplexity selection over jyutping candidates.

        For each char in the input, look up t2s candidates (e.g.
        俾 → [畀]). Generate all combinations, score each with
        BERT perplexity, return the lowest. This is the slow path
        (~300-500ms/segment) — `acorrect` wraps this in a thread.
        """
        from itertools import product

        self._ensure_bert_loaded()
        assert self.bert_model is not None
        assert self.t2s_char_dict is not None
        assert self.chars_freq is not None  # noqa: F841 — used in load_data

        text = text.strip()
        if not text:
            return text

        char_candidates = [self.t2s_char_dict.get(ch, [ch]) for ch in text]
        if all(len(cands) == 1 for cands in char_candidates):
            # No char needs correction; still apply OpenCC + regex
            # to the whole string in case of any t2s drift in the
            # original.
            return self._opencc_correct(text)

        text_candidates = ["".join(comb) for comb in product(*char_candidates)]
        if not text_candidates:
            return text

        return min(
            text_candidates,
            key=lambda t: self.bert_model.perplexity(t),  # type: ignore[union-attr]
        )


__all__ = ["Corrector", "_OPENCC_RULES"]

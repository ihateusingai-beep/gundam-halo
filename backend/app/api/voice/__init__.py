"""Voice REST API subpackage — Sprint 56 R4 split.

Back-compat shim for `app.api.voice_config_api` (the 990-LoC
pre-Sprint-56 monolith). All previous imports continue to work:

    from app.api.voice_config_api import (
        voice_status, get_voice_config, put_voice_config,
        list_self_record_corpora, post_run_held_out_eval,
        get_run_held_out_eval, post_run_finetune, list_eval_jobs,
        get_eval_corpus_breakdown,
    )
    from app.api.voice_config_api import (
        _resolve_train_corpus_dir, _resolve_base_model_path,
        _preflight_validate_manifest, _run_orchestrator_thread,
        RunEvalRequest, RunFinetuneRequest,
    )

The actual modules:
  - `app.api.voice.rest`         — voice_status + get_voice_config +
                                    get_voice_eval_results + put_voice_config
  - `app.api.voice.eval_jobs`    — post_run_held_out_eval +
                                    get_run_held_out_eval + post_run_finetune +
                                    list_eval_jobs + get_eval_corpus_breakdown
  - `app.api.voice.corpora`      — list_self_record_corpora
  - `app.api.voice._shared`      — Pydantic models + path resolvers +
                                    preflight + background-thread target
                                    (not a FastAPI router module —
                                    underscore prefix)

All 3 router modules register against the SHARED `router`
imported from `app.api.ws_protocol`. FastAPI walks the route
table at app startup, so the order of registration doesn't matter.
"""
from app.api.voice.corpora import (  # noqa: F401
    list_self_record_corpora,
)
from app.api.voice.eval_jobs import (  # noqa: F401
    get_eval_corpus_breakdown,
    get_run_held_out_eval,
    list_eval_jobs,
    post_run_finetune,
    post_run_held_out_eval,
)
from app.api.voice.rest import (  # noqa: F401
    get_voice_config,
    get_voice_eval_results,
    put_voice_config,
    voice_status,
)
# Shared types + helpers — re-exported for tests that import
# them from the old voice_config_api module path. New code
# should import directly from `app.api.voice._shared` (or
# from `app.api.voice.eval_jobs` / `corpora` for the call-site
# submodules).
from app.api.voice._shared import (  # noqa: F401
    DEFAULT_BASE_MODEL_PATH,
    DEFAULT_HALO_HOME,
    CORPUS_DIR_PREFIX,
    RunEvalRequest,
    RunFinetuneRequest,
    UNATTRIBUTED_KEY,
    _preflight_validate_manifest,
    _resolve_base_model_path,
    _resolve_halo_home,
    _resolve_train_corpus_dir,
    _run_orchestrator_thread,
)
# Sprint 46: `held_out_results_dir` was module-level in the
# pre-R4 monolith so tests could monkeypatch it. Re-export
# for the test patches that still target `voice_config_api`.
from app.voice.held_out_eval import held_out_results_dir  # noqa: F401


__all__ = [
    # REST endpoints (Sprint 32 P1.1)
    "voice_status",
    "get_voice_config",
    "get_voice_eval_results",
    "put_voice_config",
    "list_self_record_corpora",
    "post_run_held_out_eval",
    "get_run_held_out_eval",
    "post_run_finetune",
    "list_eval_jobs",
    "get_eval_corpus_breakdown",
    # Pydantic request models
    "RunEvalRequest",
    "RunFinetuneRequest",
    # Shared helpers
    "_resolve_halo_home",
    "_resolve_train_corpus_dir",
    "_resolve_base_model_path",
    "_preflight_validate_manifest",
    "_run_orchestrator_thread",
    # Constants
    "DEFAULT_HALO_HOME",
    "DEFAULT_BASE_MODEL_PATH",
    "CORPUS_DIR_PREFIX",
    "UNATTRIBUTED_KEY",
]

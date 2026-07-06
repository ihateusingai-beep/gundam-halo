"""Voice REST API — back-compat shim to `app.api.voice` subpackage.

Sprint 56 R4: this file used to be a 990-LoC monolith. It is
now a 50-line shim that re-exports every symbol from the
new `app.api.voice` subpackage.

All previous imports continue to work:

    from app.api.voice_config_api import voice_status
    from app.api.voice_config_api import get_voice_config
    from app.api.voice_config_api import _resolve_halo_home

The actual implementation moved to:
  - `app.api.voice.rest`       — 4 REST config endpoints
  - `app.api.voice.eval_jobs`  — held-out eval + fine-tune +
                                  list-jobs + corpus-breakdown
  - `app.api.voice.corpora`    — self-record corpora scan
  - `app.api.voice._shared`    — Pydantic models + path resolvers
                                  + preflight + background thread

This shim will be removed in a future sprint once all callers
update to import from `app.api.voice` directly.
"""
from app.api.voice import *  # noqa: F401, F403
from app.api.voice import (  # noqa: F401
    DEFAULT_BASE_MODEL_PATH,
    DEFAULT_HALO_HOME,
    RunEvalRequest,
    RunFinetuneRequest,
    UNATTRIBUTED_KEY,
    _preflight_validate_manifest,
    _resolve_base_model_path,
    _resolve_halo_home,
    _resolve_train_corpus_dir,
    _run_orchestrator_thread,
    get_eval_corpus_breakdown,
    get_run_held_out_eval,
    get_voice_config,
    get_voice_eval_results,
    held_out_results_dir,  # Sprint 46: test-monkeypatch target
    list_eval_jobs,
    list_self_record_corpora,
    post_run_finetune,
    post_run_held_out_eval,
    put_voice_config,
    voice_status,
)
# Re-export `get_store` for tests that import it from
# `voice_config_api` (the pre-R4 monolith had it as a top-level
# `from app.core.eval_jobs import get_store`).
from app.core.eval_jobs import get_store  # noqa: F401

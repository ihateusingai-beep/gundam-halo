"""Sprint 36 Tier 1 — `app.core.agent_context` workspace loader tests.

Verifies:
- `load_workspace(home)` returns the expected docs in the
  expected order (AGENTS.md before SOUL.md before USER.md etc.)
- `format_for_prompt()` joins docs into a single string with
  `## <filename>` headers
- `format_for_prompt()` skips BOOTSTRAP.md (one-shot wizard)
- `format_for_prompt()` truncates with a clear marker when
  over `max_chars`
- `ensure_workspace_seeded()` copies starter files into a
  fresh home; existing files are never overwritten
- `has_bootstrap()` correctly detects first-run
- Module-level cache returns the same object on second call
  but re-reads after the user edits a doc
- `reset_cache()` (test helper) clears both caches

The tests use a tmp_path fixture to avoid touching the real
`~/.gundam-halo/workspace/` and to avoid coupling to the
bundled starter content.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core.agent_context import (
    PROMPT_ORDER,
    WORKSPACE_DIR_NAME,
    WorkspaceDoc,
    ensure_workspace_seeded,
    format_for_prompt,
    has_bootstrap,
    load_workspace,
    reset_cache,
)


@pytest.fixture(autouse=True)
def _clear_module_cache():
    """Reset the module-level cache before AND after every test.

    The cache is shared across tests (module-level dict), so
    a missing reset causes test pollution.
    """
    reset_cache()
    yield
    reset_cache()


def _write_workspace(home: Path, *, with_bootstrap: bool = True) -> None:
    """Helper — populate the workspace dir with minimal stubs."""
    ws = home / WORKSPACE_DIR_NAME
    ws.mkdir(parents=True, exist_ok=True)
    for name in PROMPT_ORDER:
        (ws / name).write_text(f"# {name}\n\nstub body", encoding="utf-8")
    if with_bootstrap:
        (ws / "BOOTSTRAP.md").write_text(
            "# BOOTSTRAP.md\n\nwizard text", encoding="utf-8"
        )


def test_load_workspace_returns_docs_in_prompt_order(tmp_path: Path) -> None:
    """The docs come back in PROMPT_ORDER (AGENTS → SOUL → USER → ...).

    This order is the contract — the agent reads top-down and
    expects AGENTS.md first (master behaviour contract), then
    SOUL.md (personality), then USER.md (the human).
    """
    _write_workspace(tmp_path)
    docs = load_workspace(tmp_path)
    names = [d.name for d in docs]
    # AGENTS..HEARTBEAT follow PROMPT_ORDER exactly; BOOTSTRAP
    # is appended last (out of order, but the prompt formatter
    # drops it).
    expected = list(PROMPT_ORDER) + ["BOOTSTRAP.md"]
    assert names == expected
    # All WorkspaceDoc instances.
    assert all(isinstance(d, WorkspaceDoc) for d in docs)
    # Each doc carries the body + path.
    agents = docs[0]
    assert agents.name == "AGENTS.md"
    assert "stub body" in agents.body
    assert agents.path == tmp_path / WORKSPACE_DIR_NAME / "AGENTS.md"


def test_load_workspace_seeds_when_missing(tmp_path: Path) -> None:
    """First call to `load_workspace` on an empty home seeds the starter files."""
    assert not (tmp_path / WORKSPACE_DIR_NAME).exists()
    docs = load_workspace(tmp_path)
    # Starter files all present.
    for name in PROMPT_ORDER:
        assert (tmp_path / WORKSPACE_DIR_NAME / name).is_file()
    # BOOTSTRAP.md is also part of the starter set, so the
    # loader surfaces it for `has_bootstrap` detection.
    assert has_bootstrap(docs)


def test_load_workspace_does_not_overwrite_existing(tmp_path: Path) -> None:
    """If the user already edited AGENTS.md, we never overwrite."""
    _write_workspace(tmp_path)
    (tmp_path / WORKSPACE_DIR_NAME / "AGENTS.md").write_text(
        "# AGENTS.md\n\nUSER CUSTOMISED", encoding="utf-8"
    )
    load_workspace(tmp_path, force=True)
    agents = (tmp_path / WORKSPACE_DIR_NAME / "AGENTS.md").read_text(
        encoding="utf-8"
    )
    assert "USER CUSTOMISED" in agents
    assert "stub body" not in agents


def test_format_for_prompt_emits_headers_and_skips_bootstrap(
    tmp_path: Path,
) -> None:
    """`format_for_prompt` includes `## <filename>` headers and drops BOOTSTRAP.md."""
    _write_workspace(tmp_path)
    docs = load_workspace(tmp_path)
    out = format_for_prompt(docs)
    assert "## AGENTS.md" in out
    assert "## SOUL.md" in out
    assert "## USER.md" in out
    # BOOTSTRAP.md is filtered out — it's a one-shot wizard.
    assert "## BOOTSTRAP.md" not in out
    # Sections are separated by horizontal rules.
    assert "\n\n---\n\n" in out


def test_format_for_prompt_truncates_at_max_chars(tmp_path: Path) -> None:
    """When the joined body exceeds `max_chars`, the formatter truncates with a marker."""
    _write_workspace(tmp_path)
    docs = load_workspace(tmp_path)
    # Force a tiny cap to trigger truncation.
    out = format_for_prompt(docs, max_chars=50)
    assert len(out) < len(format_for_prompt(docs))
    assert "truncated" in out


def test_format_for_prompt_empty_when_no_docs() -> None:
    """Empty doc list → empty string (caller decides whether to inject anything)."""
    assert format_for_prompt([]) == ""


def test_has_bootstrap_detects_first_run(tmp_path: Path) -> None:
    """`has_bootstrap` returns True iff BOOTSTRAP.md was in the doc list."""
    _write_workspace(tmp_path, with_bootstrap=True)
    docs = load_workspace(tmp_path)
    assert has_bootstrap(docs) is True

    # Remove BOOTSTRAP.md and re-load.
    (tmp_path / WORKSPACE_DIR_NAME / "BOOTSTRAP.md").unlink()
    docs2 = load_workspace(tmp_path, force=True)
    assert has_bootstrap(docs2) is False


def test_load_workspace_caches_results(tmp_path: Path) -> None:
    """Second call returns the same cached list object."""
    _write_workspace(tmp_path)
    docs1 = load_workspace(tmp_path)
    docs2 = load_workspace(tmp_path)
    assert docs1 is docs2


def test_load_workspace_re_reads_on_file_edit(tmp_path: Path) -> None:
    """When the user edits a doc, the next call picks up the change via mtime."""
    _write_workspace(tmp_path)
    docs1 = load_workspace(tmp_path)
    assert "stub body" in docs1[0].body
    import time as _time

    _time.sleep(0.05)  # ensure mtime differs
    (tmp_path / WORKSPACE_DIR_NAME / "AGENTS.md").write_text(
        "# AGENTS.md\n\nUPDATED", encoding="utf-8"
    )
    docs2 = load_workspace(tmp_path)
    assert docs2 is not docs1
    assert "UPDATED" in docs2[0].body


def test_ensure_workspace_seeded_returns_true_on_first_seed(tmp_path: Path) -> None:
    """`ensure_workspace_seeded` reports True when it actually copied anything."""
    assert ensure_workspace_seeded(tmp_path) is True
    # Second call: nothing to copy → False.
    assert ensure_workspace_seeded(tmp_path) is False


def test_load_workspace_survives_unreadable_file(tmp_path: Path) -> None:
    """When one file is unreadable, the loader skips it (warns) and continues."""
    _write_workspace(tmp_path)
    # Make AGENTS.md unreadable by replacing it with a directory
    # of the same name. `is_file()` returns False on a dir,
    # so the loader skips it gracefully.
    target = tmp_path / WORKSPACE_DIR_NAME / "AGENTS.md"
    target.unlink()
    target.mkdir()
    docs = load_workspace(tmp_path, force=True)
    # AGENTS.md is skipped (it's a dir, not a file); the
    # remaining docs are still loaded.
    names = [d.name for d in docs]
    assert "AGENTS.md" not in names
    assert "SOUL.md" in names
    assert "USER.md" in names


def test_reset_cache_clears_both_caches(tmp_path: Path) -> None:
    """`reset_cache` clears docs and mtimes so the next call re-reads."""
    from app.core import agent_context as ac

    _write_workspace(tmp_path)
    docs1 = load_workspace(tmp_path)
    assert str(tmp_path) in ac._cache  # type: ignore[attr-defined]
    reset_cache()
    assert ac._cache == {}  # type: ignore[attr-defined]
    assert ac._cache_mtimes == {}  # type: ignore[attr-defined]
    # Next call re-loads; not the same object.
    docs2 = load_workspace(tmp_path)
    assert docs1 is not docs2
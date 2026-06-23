"""Skill metadata loader — enriches tool OpenAPI descriptions
from `~/.gundam-halo/skills/<tool>/SKILL.md` (Sprint 36 Tier 2).

Pattern borrowed from OpenClaw's
`extensions/<plugin>/skills/<skill>/SKILL.md`. Each skill has
a markdown file with a YAML-style frontmatter:

    ---
    name: file_read
    description: Use when you need to inspect a file's contents
    user-invocable: false
    ---

    # File Read

    ## Operating Loop
    ...
    ## Examples
    ...
    ## Red Lines
    ...

The frontmatter is parsed manually (no PyYAML dependency — the
schema is just `key: value` lines, and pulling in a full YAML
parser for 3 fields is overkill). The body (everything after
the second `---`) is appended to the tool's OpenAI-compatible
`description` field via `BaseTool.to_spec()`, so the LLM sees
the rich operating-loop + examples + red-lines context when
deciding how to call the tool.

Design rationale (per `docs/FEATURE-SPEC-SPRINT36.md` §Tier 2):
- 22+ tools × 1-3 sentence class-level `description` = thin
  prompt context for tool selection
- Adding SKILL.md bodies = 10-30x richer descriptions = better
  tool calling accuracy
- User can edit `~/.gundam-halo/skills/<name>/SKILL.md` to
  tune the LLM's understanding of any tool without editing
  Python source

Failure modes (all soft):
- Missing SKILL.md for a tool → no enrichment, falls back to
  class-level description
- Malformed frontmatter → load the body as plain markdown,
  log a warning
- Unknown frontmatter keys → ignored, only `name` /
  `description` / `user-invocable` are honoured
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

SKILLS_DIR_NAME = "skills"


@dataclass(frozen=True)
class SkillMetadata:
    """Parsed SKILL.md frontmatter + body.

    `name` mirrors the frontmatter `name:` line (sanity check
    vs the tool class's `name` attribute, which is the source
    of truth). `description` is the one-line frontmatter
    description (NOT the body — the body goes into
    `enriched_description`). `user_invocable` is the
    frontmatter boolean (reserved for future UI work — Tier 2
    just stores it). `body` is the markdown content after
    the closing `---`. `path` is the absolute file path.
    """

    name: str
    description: str
    user_invocable: bool
    body: str
    path: Path

    @property
    def enriched_description(self) -> str:
        """The class-level description (`description` field)
        combined with the SKILL.md body.

        Returns a single string suitable for the OpenAPI
        `function.description` field. The class-level
        description stays first (the LLM scans top-down), then
        the body follows for full operating-loop context.
        """
        parts: list[str] = []
        if self.description:
            parts.append(self.description)
        if self.body:
            parts.append(self.body.strip())
        return "\n\n".join(parts)


# Module-level cache, keyed by home path string. Mirrors the
# agent_context.py cache pattern.
_cache: Dict[str, Dict[str, SkillMetadata]] = {}
_cache_mtimes: Dict[str, float] = {}


def reset_cache() -> None:
    """Clear the module-level skill cache. Test-only."""
    _cache.clear()
    _cache_mtimes.clear()


def preload_cache(home: Path) -> None:
    """Populate the module-level cache for `home`.

    Called by `app.tools.builder.default_tools` at agent-init
    time so subsequent `to_spec()` calls are O(1). Idempotent
    — calling twice is a no-op.

    The cache stores the loaded `Dict[str, SkillMetadata]`;
    `to_spec()` looks up one tool's worth of metadata per call
    via `_get_skill_for_spec()` (a thin wrapper over the cache
    that adds the class-level-description fallback).
    """
    load_all_skills(home)


def _get_skill_for_spec(tool_name: str, fallback_description: str) -> str:
    """Look up one tool's enriched description for `to_spec()`.

    Returns the SKILL.md's `enriched_description` (frontmatter
    description + body) when the cache has an entry for
    `tool_name`; otherwise returns `fallback_description`
    unchanged. The fallback path means `to_spec()` is safe to
    call when no SKILL.md exists for a tool — it behaves
    identically to the pre-Sprint-36 implementation.
    """
    # Scan all cached homes for this tool. In practice
    # there's only one (single-process), but the helper is
    # written defensively so test fixtures that swap
    # `cfg.home` mid-process don't surprise the caller.
    for skills in _cache.values():
        skill = skills.get(tool_name)
        if skill is not None:
            return skill.enriched_description
    return fallback_description


def _skills_dir(home: Path) -> Path:
    return home / SKILLS_DIR_NAME


_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(?P<fm>.*?\n)---\s*\n(?P<body>.*)$",
    re.DOTALL,
)


def parse_skill_md(text: str, *, path: Optional[Path] = None) -> SkillMetadata:
    """Parse a SKILL.md text blob into a `SkillMetadata`.

    Args:
        text: Raw file content.
        path: Optional path for error messages.

    Returns:
        A `SkillMetadata` even on partial failure — the body
        is always populated (frontmatter may be missing); the
        frontmatter fields fall back to empty defaults so the
        caller can still use `enriched_description`.
    """
    name = ""
    description = ""
    user_invocable = False
    body = text

    m = _FRONTMATTER_RE.match(text)
    if not m:
        # No frontmatter — whole file is body.
        return SkillMetadata(
            name=name,
            description=description,
            user_invocable=user_invocable,
            body=body,
            path=path or Path("<unknown>"),
        )
    fm_text = m.group("fm")
    body = m.group("body")

    # Parse the frontmatter. The schema is intentionally
    # minimal — just `key: value` lines. No nested keys,
    # no lists, no quoting. Anything more complex is a sign
    # the SKILL.md author should simplify.
    for raw_line in fm_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            logger.warning(
                "SKILL.md frontmatter at %s: skipping malformed line %r",
                path, line,
            )
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key == "name":
            name = value
        elif key == "description":
            description = value
        elif key == "user-invocable":
            user_invocable = value.lower() in ("true", "yes", "1", "on")
        else:
            # Unknown frontmatter key — silently ignore. The
            # contract is name/description/user-invocable;
            # anything else is the author's free-form note.
            logger.debug(
                "SKILL.md frontmatter at %s: unknown key %r (ignored)",
                path, key,
            )

    return SkillMetadata(
        name=name,
        description=description,
        user_invocable=user_invocable,
        body=body,
        path=path or Path("<unknown>"),
    )


def load_skill(home: Path, tool_name: str) -> Optional[SkillMetadata]:
    """Load one tool's SKILL.md from `~/.gundam-halo/skills/<name>/SKILL.md`.

    Args:
        home: The config home path (typically `Config.home`).
        tool_name: The tool's registered name (e.g.
            `"file_read"`). Matches `ToolRegistry` keys.

    Returns:
        The parsed `SkillMetadata`, or `None` if no SKILL.md
        exists for the tool. (The runtime treats `None` as
        "no enrichment; use class-level description".)
    """
    cached = _cache.get(str(home))
    if cached is not None and tool_name in cached:
        return cached[tool_name]
    skill = _read_skill_file(home, tool_name)
    if skill is not None:
        _cache.setdefault(str(home), {})[tool_name] = skill
    return skill


def _read_skill_file(home: Path, tool_name: str) -> Optional[SkillMetadata]:
    """Read + parse one SKILL.md from disk. No caching."""
    path = _skills_dir(home) / tool_name / "SKILL.md"
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning("cannot read SKILL.md %s: %s", path, e)
        return None
    return parse_skill_md(text, path=path)


def load_all_skills(home: Path) -> Dict[str, SkillMetadata]:
    """Load every `~/.gundam-halo/skills/*/SKILL.md` once.

    Returns a dict keyed by tool name. Use this when you
    need to enrich a tool spec list (the runtime calls it
    once per agent init, not per tool).

    Tools that don't have a SKILL.md are simply absent from
    the dict — the caller falls back to class-level
    description.

    Freshness: the cache is keyed on home + max-mtime
    across all `SKILL.md` files. If the user edits a
    SKILL.md, the next `load_all_skills()` call detects
    the mtime change and re-reads. This mirrors the
    pattern in `app.core.agent_context` so the user can
    edit SKILL.md and see the effect on the next turn
    without restarting the backend.
    """
    cache_key = str(home)
    skills_dir = _skills_dir(home)
    if not skills_dir.is_dir():
        _cache[cache_key] = {}
        return {}

    # Freshness check (mirror of agent_context.load_workspace).
    max_mtime = 0.0
    for entry in skills_dir.iterdir():
        if not entry.is_dir():
            continue
        skill_md = entry / "SKILL.md"
        if skill_md.is_file():
            try:
                max_mtime = max(max_mtime, skill_md.stat().st_mtime)
            except OSError:
                pass
    cached = _cache.get(cache_key)
    if cached is not None and _cache_mtimes.get(cache_key) == max_mtime:
        return cached

    result: Dict[str, SkillMetadata] = {}
    for entry in sorted(skills_dir.iterdir()):
        if not entry.is_dir():
            continue
        skill = _read_skill_file(home, entry.name)
        if skill is not None:
            result[entry.name] = skill
    _cache[cache_key] = result
    _cache_mtimes[cache_key] = max_mtime
    return result


def ensure_skill_seeded(home: Path, tool_names: List[str]) -> int:
    """Seed `~/.gundam-halo/skills/<name>/SKILL.md` for tools
    that don't have one yet, copying from the bundled
    starter set in `app/data/skills/`.

    Args:
        home: The config home path.
        tool_names: The list of registered tool names
            (typically `ToolRegistry.keys()`).

    Returns:
        The number of starter files newly copied. 0 if
        everything was already present (or the bundle has
        no starter for a given tool).
    """
    from importlib import resources  # local — keep top-level lean

    copied = 0
    skills_dir = _skills_dir(home)
    try:
        skills_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.warning("ensure_skill_seeded: cannot create %s: %s", skills_dir, e)
        return 0
    for name in tool_names:
        target = skills_dir / name / "SKILL.md"
        if target.exists():
            continue
        try:
            starter = (
                resources.files("app.data.skills")
                .joinpath(name)
                .joinpath("SKILL.md")
                .read_text(encoding="utf-8")
            )
        except (FileNotFoundError, OSError):
            # No bundled starter for this tool — fine, the
            # class-level description carries it.
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(starter, encoding="utf-8")
            copied += 1
            logger.info("seeded skill SKILL.md: %s", target)
        except OSError as e:
            logger.warning("failed to seed %s: %s", target, e)
    return copied


__all__ = [
    "SKILLS_DIR_NAME",
    "SkillMetadata",
    "ensure_skill_seeded",
    "load_all_skills",
    "load_skill",
    "parse_skill_md",
    "preload_cache",
    "reset_cache",
]
"""Tool base class + spec helper.

A tool wraps a single capability (file read, shell exec, etc.) and exposes
both an OpenAI-compatible spec (so the LLM knows how to call it) and an
async `run` method (so the agent can invoke it).

Sprint 36 Tier 2: `to_spec()` enriches the class-level `description`
with the body of `~/.gundam-halo/skills/<name>/SKILL.md` when one
exists. The enrichment is opt-in — if the user hasn't created a
SKILL.md for this tool, the spec falls back to the class-level
description exactly as before. The cache is module-level in
`app.core.skill_metadata` and is populated by `default_tools()` at
agent-init time, so per-turn `to_spec()` calls are O(1).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseTool(ABC):
    """Abstract base for all Gundam Halo tools.

    Subclasses must define:
    - `name`: short identifier (e.g. "file_read")
    - `description`: when to use this tool (1-2 sentences, LLM reads this)
    - `to_spec()`: returns the OpenAI-compatible function spec
    - `run(**kwargs)`: async, returns the observation as a string
    """

    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema

    def to_spec(self) -> Dict[str, Any]:
        """Return the OpenAI-compatible function spec.

        Sprint 36 Tier 2 enrichment: looks up the tool's SKILL.md
        in the module-level skill cache (populated by
        `app.tools.builder.default_tools` before any agent
        instantiates a BaseTool). When the SKILL.md exists, the
        spec's `function.description` is replaced with the
        frontmatter description + body (operating loop /
        examples / red lines), giving the LLM 10-30x richer
        context for tool selection.

        When no SKILL.md exists, this method behaves exactly as
        before — pure class-level description, no I/O, no
        exception path. The enrichment is purely additive.
        """
        # Lazy import — skill_metadata imports app.core.config
        # which pulls in stdlib tomllib. We don't want that
        # cost at module import time of _stubs.py (which is
        # imported by every tool class).
        from app.core.skill_metadata import _get_skill_for_spec

        enriched_description = _get_skill_for_spec(self.name, self.description)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": enriched_description,
                "parameters": self.parameters,
            },
        }

    @abstractmethod
    async def run(self, **kwargs: Any) -> str:
        """Execute the tool. Return the observation as a string."""


__all__ = ["BaseTool"]

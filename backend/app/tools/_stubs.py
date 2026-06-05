"""Tool base class + spec helper.

A tool wraps a single capability (file read, shell exec, etc.) and exposes
both an OpenAI-compatible spec (so the LLM knows how to call it) and an
async `run` method (so the agent can invoke it).
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
        """Return the OpenAI-compatible function spec."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    @abstractmethod
    async def run(self, **kwargs: Any) -> str:
        """Execute the tool. Return the observation as a string."""


__all__ = ["BaseTool"]

"""Live2D trigger interface — M3.

The trigger is a thin client: the Tauri app subscribes to Live2D
trigger events over WebSocket, and the backend just publishes
"play this expression + this motion" commands. The Tauri app owns
the actual Live2D rendering (via pixi-live2d-display in the webview).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(slots=True)
class Live2DTrigger:
    """A command to play a Live2D expression + motion pair."""

    expression: str
    motion: str


class Live2DInterface(ABC):
    """Live2D trigger layer (M3)."""

    @abstractmethod
    async def trigger(self, expression: str, motion: str) -> Live2DTrigger:
        """Validate and emit a Live2D trigger."""
        ...

    @abstractmethod
    async def warmup(self) -> None:
        """Load model metadata."""
        ...


__all__ = ["Live2DInterface", "Live2DTrigger"]

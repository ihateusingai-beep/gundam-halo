"""Channel identity — bind a transport-level ID to a stable human name.

Right now this is mostly a Telegram-only concern (chat_id → display name),
but it's structured as a generic `ChannelIdentity` so we can add more
channels later (Discord, Slack, SMS, etc.) without rewriting callers.

The display name is *advisory*: the agent uses it in its system prompt
so it knows who it's talking to. The chat_id is the actual routing key;
the display name is for human-readability.

Resolution priority:
1. config.toml `channels.telegram.display_names[chat_id]` (most explicit)
2. The Telegram chat's own `first_name` / `title` from the update (transient)
3. The chat_id itself (last resort)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class ChannelIdentity:
    """Stable identity for a person on a specific channel."""

    channel: str            # "telegram", "discord", ...
    transport_id: str       # chat_id, user_id, etc.
    display_name: str       # human-readable name
    is_group: bool = False  # True for group chats, DMs are False

    @property
    def short_id(self) -> str:
        """A compact form for logs and UI: 'telegram:ken'."""
        return f"{self.channel}:{self.display_name.lower()}"


def resolve_telegram_identity(
    chat_id: str | int,
    *,
    config_display_names: dict[str, str] | None = None,
    update_first_name: str | None = None,
    update_username: str | None = None,
    update_chat_title: str | None = None,
    is_group: bool = False,
) -> ChannelIdentity:
    """Resolve a Telegram chat_id to a ChannelIdentity.

    Resolution priority (highest first):
    1. config_display_names[str(chat_id)]  — explicit user binding
    2. update_chat_title                    — group chat title
    3. update_first_name + update_username  — DM with profile data
    4. str(chat_id)                         — fallback to numeric ID

    Args:
        chat_id: Telegram chat id (int or string). Stringified for lookups.
        config_display_names: from `cfg.telegram.display_names`. May be None.
        update_first_name: from the `from` field in the update.
        update_username: from the `from` field in the update (e.g. "kcheng").
        update_chat_title: from the `chat.title` field in the update.
        is_group: True if this is a group / channel (not a DM).
    """
    chat_id_str = str(chat_id)

    # 1. Explicit user binding from config (highest priority)
    if config_display_names:
        explicit = config_display_names.get(chat_id_str)
        if explicit:
            return ChannelIdentity(
                channel="telegram",
                transport_id=chat_id_str,
                display_name=explicit,
                is_group=is_group,
            )

    # 2. Group chat title from the update
    if update_chat_title and is_group:
        return ChannelIdentity(
            channel="telegram",
            transport_id=chat_id_str,
            display_name=update_chat_title,
            is_group=True,
        )

    # 3. DM with profile data
    if update_first_name:
        full = update_first_name
        if update_username:
            full = f"{update_first_name} (@{update_username})"
        return ChannelIdentity(
            channel="telegram",
            transport_id=chat_id_str,
            display_name=full,
            is_group=False,
        )

    # 4. Fall back to chat_id
    return ChannelIdentity(
        channel="telegram",
        transport_id=chat_id_str,
        display_name=f"telegram:{chat_id_str}",
        is_group=is_group,
    )


# ---------------------------------------------------------------------------
# Convenience: a runtime cache so we don't re-resolve for the same chat
# (avoids spamming the logger with the same name every message)
# ---------------------------------------------------------------------------

_cache: dict[str, ChannelIdentity] = {}


def resolve_telegram_identity_cached(
    chat_id: str | int,
    **kwargs,
) -> ChannelIdentity:
    """Same as `resolve_telegram_identity` but with a per-chat_id cache."""
    chat_id_str = str(chat_id)
    cached = _cache.get(chat_id_str)
    # We only cache the "stable" entries (explicit name, group title, or
    # chat_id fallback). Entries that depend on transient Telegram update
    # data (first_name) are not cached — a user can change their name.
    explicit = (kwargs.get("config_display_names") or {}).get(chat_id_str)
    if cached is not None and (explicit or cached.is_group):
        return cached

    identity = resolve_telegram_identity(chat_id, **kwargs)
    # Only cache the stable ones
    if explicit or identity.is_group or identity.display_name == f"telegram:{chat_id_str}":
        _cache[chat_id_str] = identity
    return identity


def reset_identity_cache() -> None:
    """Clear the resolver cache (for tests and config reloads)."""
    _cache.clear()


__all__ = [
    "ChannelIdentity",
    "resolve_telegram_identity",
    "resolve_telegram_identity_cached",
    "reset_identity_cache",
]

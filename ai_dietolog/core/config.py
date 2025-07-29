from __future__ import annotations

"""Configuration utilities for the project."""

import json
import os
from pathlib import Path

__all__ = ["load_config", "openai_api_key"]


def load_config() -> dict:
    """Load configuration from ``config.json`` or environment variables."""
    cfg_path = Path(__file__).resolve().parent.parent.parent / "config.json"
    if cfg_path.exists():
        with cfg_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
        "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
    }


def openai_api_key() -> str:
    """Return the configured OpenAI API key, if any.

    The function first reads ``config.json`` via :func:`load_config`.
    If the key is missing or empty in the file, it falls back to the
    ``OPENAI_API_KEY`` environment variable.  This mirrors the behaviour
    used in ``telegram_bot.py`` where an empty value from ``config.json``
    should not override a valid environment variable.
    """
    cfg = load_config()
    return cfg.get("openai_api_key") or os.getenv("OPENAI_API_KEY", "")

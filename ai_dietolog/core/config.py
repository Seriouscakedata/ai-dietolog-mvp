from __future__ import annotations

"""Configuration utilities for the project."""

import json
import os
from pathlib import Path

__all__ = [
    "load_config",
    "openai_api_key",
    "gemini_api_key",
    "llm_provider",
    "agent_llm",
]


def load_config() -> dict:
    """Load configuration from ``config.json`` or environment variables."""
    cfg_path = Path(__file__).resolve().parent.parent.parent / "config.json"
    if cfg_path.exists():
        with cfg_path.open("r", encoding="utf-8") as f:
            data = []
            for line in f:
                l = line.strip()
                if l.startswith("#") or l.startswith("//"):
                    continue
                if "#" in line:
                    line = line.split("#", 1)[0]
                if "//" in line:
                    line = line.split("//", 1)[0]
                data.append(line)
            return json.loads("".join(data))
    return {
        "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
        "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
        "gemini_api_key": os.getenv("GEMINI_API_KEY", ""),
        "llm_provider": os.getenv("LLM_PROVIDER", "openai"),
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


def gemini_api_key() -> str:
    """Return the configured Gemini API key."""
    cfg = load_config()
    return cfg.get("gemini_api_key") or os.getenv("GEMINI_API_KEY", "")


def llm_provider() -> str:
    """Return the default LLM provider."""
    cfg = load_config()
    return cfg.get("llm_provider") or os.getenv("LLM_PROVIDER", "openai")


def agent_llm(name: str, cfg: dict | None = None) -> tuple[str, str]:
    """Return provider and model for the given agent."""
    cfg = cfg or load_config()
    agent_cfg = cfg.get("agents", {}).get(name, {})
    provider = agent_cfg.get("provider") or cfg.get("llm_provider", "openai")
    model = agent_cfg.get("model")
    if not model:
        model = "gpt-3.5-turbo" if provider == "openai" else "gemini-pro"
    return provider, model

"""Entry point for the AI Dietolog Telegram bot.

This module initialises the Telegram application, registers basic
commands and starts polling.  Only minimal scaffolding is provided here
to demonstrate how the bot could be structured.

To use this bot, set the environment variables ``TELEGRAM_BOT_TOKEN`` and
``OPENAI_API_KEY`` or populate ``config.json`` accordingly.  The
application will not perform any network requests until a valid token is
provided.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from telegram import Update
from telegram.ext import (Application, CommandHandler, ContextTypes)

from ..core import storage
from ..core.schema import Profile
from ..agents.profile_collector import build_profile


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_config() -> dict:
    """Load configuration from config.json or environment variables."""
    cfg_path = Path(__file__).resolve().parent.parent / "config.json"
    if cfg_path.exists():
        with cfg_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
        "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
    }


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Respond to /start with a welcome message."""
    await update.message.reply_text(
        "Добро пожаловать в AI‑диетолог! Используйте /setup_profile для настройки профиля."
    )


async def setup_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /setup_profile by creating a minimal profile.

    For demonstration purposes, this handler immediately constructs a profile
    using placeholder values.  In a real implementation the bot would
    interactively ask the user questions and collect responses.
    """
    user_id = update.effective_user.id
    # Example of building a profile with dummy data; replace with real input.
    profile = build_profile(
        gender="male",
        age=30,
        height_cm=180,
        weight_kg=80,
        activity_level="moderate",
        goal_type="maintain",
        target_change_kg=0,
        timeframe_days=0,
    )
    storage.save_profile(user_id, profile)
    await update.message.reply_text(
        f"Профиль создан. Целевая калорийность: {profile.norms.target_kcal} ккал."
    )


def main() -> None:
    """Main entry point.  Instantiate the bot and run polling."""
    cfg = load_config()
    token = cfg.get("telegram_bot_token") or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        # Do not crash if token is missing; simply log and exit.
        logger.warning("TELEGRAM_BOT_TOKEN is not set; bot will not start.")
        return
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("setup_profile", setup_profile))
    application.run_polling()


if __name__ == "__main__":
    main()

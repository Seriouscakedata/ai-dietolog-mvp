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

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from openai import AsyncOpenAI

from ..core import storage
from ..core.schema import Profile
from ..agents.profile_collector import build_profile


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Conversation states: collecting free-form profile and confirmation
(DESCRIPTION, CONFIRM) = range(2)


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
    """Respond to /start with a welcome message and inline buttons."""
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Настроить профиль", callback_data="setup_profile")]]
    )
    await update.message.reply_text(
        "Добро пожаловать в AI‑диетолог! Выберите действие:",
        reply_markup=keyboard,
    )

async def setup_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for the profile setup conversation."""
    if update.callback_query:
        await update.callback_query.answer()
    context.user_data.clear()
    await update.effective_message.reply_text(
        "Расскажите о себе: пол, возраст, рост, вес, цель и ограничения."
    )
    return DESCRIPTION


async def extract_profile(text: str, api_key: str) -> dict:
    """Use OpenAI to extract profile fields from free-form text."""
    client = AsyncOpenAI(api_key=api_key)
    system = (
        "You are a nutrition assistant. From the user's message, extract a JSON "
        "object with the following keys: gender (male/female), age, height_cm, "
        "weight_kg, activity_level (sedentary/moderate/high), goal_type "
        "(lose_weight/maintain/gain_weight), target_change_kg, timeframe_days, "
        "restrictions (list), preferences (list), medical (list)."
    )
    resp = await client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "system", "content": system}, {"role": "user", "content": text}],
        temperature=0,
    )
    content = resp.choices[0].message.content
    return json.loads(content)


def summarise_profile(data: dict) -> str:
    """Return a human-friendly summary of extracted data."""
    lines = [
        f"Пол: {data.get('gender')}",
        f"Возраст: {data.get('age')}",
        f"Рост: {data.get('height_cm')} см",
        f"Вес: {data.get('weight_kg')} кг",
        f"Цель: {data.get('goal_type')}, изменение: {data.get('target_change_kg')} кг за {data.get('timeframe_days')} дн.",
        f"Активность: {data.get('activity_level')}",
    ]
    if data.get("restrictions"):
        lines.append("Непереносимости: " + ", ".join(data["restrictions"]))
    if data.get("preferences"):
        lines.append("Предпочтения: " + ", ".join(data["preferences"]))
    if data.get("medical"):
        lines.append("Медицинские ограничения: " + ", ".join(data["medical"]))
    return "\n".join(lines)


async def handle_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cfg = load_config()
    api_key = cfg.get("openai_api_key") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        await update.message.reply_text("OpenAI API key не настроен")
        return ConversationHandler.END
    try:
        data = await extract_profile(update.message.text, api_key)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Profile extraction failed: %s", exc)
        await update.message.reply_text("Не удалось разобрать сообщение, попробуйте ещё раз")
        return DESCRIPTION
    context.user_data["profile"] = data
    summary = summarise_profile(data)
    await update.message.reply_text(summary + "\nВсе верно? (да/нет)")
    return CONFIRM


async def finish_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text.strip().lower().startswith("д"):
        data = context.user_data.get("profile")
        profile = build_profile(**data)
        storage.save_profile(update.effective_user.id, profile)
        await update.message.reply_text(
            f"Профиль создан. Целевая калорийность: {profile.norms.target_kcal} ккал."
        )
        return ConversationHandler.END
    await update.message.reply_text("Опишите данные заново:")
    return DESCRIPTION


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text("Создание профиля отменено.")
    return ConversationHandler.END




def main() -> None:
    """Main entry point.  Instantiate the bot and run polling."""
    cfg = load_config()
    token = cfg.get("telegram_bot_token") or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        # Do not crash if token is missing; simply log and exit.
        logger.warning("TELEGRAM_BOT_TOKEN is not set; bot will not start.")
        return
    application = Application.builder().token(token).build()
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("setup_profile", setup_profile),
            CallbackQueryHandler(setup_profile, pattern="^setup_profile$")
        ],
        states={
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_description)],
            CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, finish_profile)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)
    application.run_polling()


if __name__ == "__main__":
    main()

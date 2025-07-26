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

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from ..core import storage
from ..core.schema import Profile
from ..agents.profile_collector import build_profile


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Conversation states
(GENDER, AGE, HEIGHT, WEIGHT, GOAL, TARGET, TIMEFRAME, ACTIVITY, RESTRICTIONS,
 PREFERENCES, MEDICAL) = range(11)


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
    await update.effective_message.reply_text("Укажите ваш пол (male/female):")
    return GENDER


async def ask_age(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().lower()
    if text not in {"male", "female"}:
        await update.message.reply_text("Пожалуйста, введите male или female:")
        return GENDER
    context.user_data["gender"] = text
    await update.message.reply_text("Ваш возраст (число лет):")
    return AGE


async def ask_height(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        age = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("Возраст должен быть числом. Попробуйте ещё раз:")
        return AGE
    context.user_data["age"] = age
    await update.message.reply_text("Рост в сантиметрах:")
    return HEIGHT


async def ask_weight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        height = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("Введите рост числом в сантиметрах:")
        return HEIGHT
    context.user_data["height_cm"] = height
    await update.message.reply_text("Текущий вес в килограммах:")
    return WEIGHT


async def ask_goal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        weight = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("Вес должен быть числом. Попробуйте ещё раз:")
        return WEIGHT
    context.user_data["weight_kg"] = weight
    await update.message.reply_text(
        "Цель (lose_weight / maintain / gain_weight):"
    )
    return GOAL


async def ask_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().lower()
    if text not in {"lose_weight", "maintain", "gain_weight"}:
        await update.message.reply_text(
            "Введите lose_weight, maintain или gain_weight:"
        )
        return GOAL
    context.user_data["goal_type"] = text
    await update.message.reply_text("На сколько кг хотите изменить вес:")
    return TARGET


async def ask_timeframe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        target = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("Введите число (может быть отрицательным):")
        return TARGET
    context.user_data["target_change_kg"] = target
    await update.message.reply_text("За сколько дней планируете достичь цели:")
    return TIMEFRAME


async def ask_activity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        timeframe = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("Количество дней должно быть целым числом:")
        return TIMEFRAME
    context.user_data["timeframe_days"] = timeframe
    await update.message.reply_text(
        "Уровень активности (sedentary / moderate / high):"
    )
    return ACTIVITY


async def ask_restrictions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().lower()
    if text not in {"sedentary", "moderate", "high"}:
        await update.message.reply_text(
            "Введите sedentary, moderate или high:" 
        )
        return ACTIVITY
    context.user_data["activity_level"] = text
    await update.message.reply_text(
        "Непереносимости (через запятую, или 'нет'):" 
    )
    return RESTRICTIONS


async def ask_preferences(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text.lower() != "нет":
        context.user_data["restrictions"] = [t.strip() for t in text.split(",") if t.strip()]
    else:
        context.user_data["restrictions"] = []
    await update.message.reply_text(
        "Предпочтения/нежелательные продукты (через запятую, или 'нет'):"
    )
    return PREFERENCES


async def ask_medical(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text.lower() != "нет":
        context.user_data["preferences"] = [t.strip() for t in text.split(",") if t.strip()]
    else:
        context.user_data["preferences"] = []
    await update.message.reply_text(
        "Медицинские ограничения (через запятую, или 'нет'):"
    )
    return MEDICAL


async def finish_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text.lower() != "нет":
        context.user_data["medical"] = [t.strip() for t in text.split(",") if t.strip()]
    else:
        context.user_data["medical"] = []

    data = context.user_data
    profile = build_profile(
        gender=data["gender"],
        age=data["age"],
        height_cm=data["height_cm"],
        weight_kg=data["weight_kg"],
        activity_level=data["activity_level"],
        goal_type=data["goal_type"],
        target_change_kg=data["target_change_kg"],
        timeframe_days=data["timeframe_days"],
        restrictions=data.get("restrictions"),
        preferences=data.get("preferences"),
        medical=data.get("medical"),
    )
    storage.save_profile(update.effective_user.id, profile)
    await update.message.reply_text(
        f"Профиль создан. Целевая калорийность: {profile.norms.target_kcal} ккал."
    )
    return ConversationHandler.END


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
            GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_age)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_height)],
            HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_weight)],
            WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_goal)],
            GOAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_target)],
            TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_timeframe)],
            TIMEFRAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_activity)],
            ACTIVITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_restrictions)],
            RESTRICTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_preferences)],
            PREFERENCES: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_medical)],
            MEDICAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, finish_profile)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)
    application.run_polling()


if __name__ == "__main__":
    main()

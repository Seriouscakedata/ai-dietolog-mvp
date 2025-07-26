"""Telegram bot for AI Dietolog interactive profile setup.

This bot collects user profile information through a conversation and
creates a diet profile with personalized norms using compute_norms().

"""

from __future__ import annotations

import os
from typing import List

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
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
from ..agents.profile_collector import build_profile


# Conversation states
(
    GENDER_AGE_HEIGHT_WEIGHT,
    GOAL,
    ACTIVITY,
    RESTRICTIONS,
    PREFERENCES,
    MEDICAL,
    CONFIRM,
) = range(7)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message with an action button."""
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Настроить профиль", callback_data="setup_profile"
                )
            ]
        ]
    )
    await update.message.reply_text(
        "Добро пожаловать в AI ‑диетолог! Выберите действие:",
        reply_markup=keyboard,
    )


async def handle_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle inline keyboard button clicks."""
    query = update.callback_query
    await query.answer()
    if query.data == "setup_profile":
        # start the profile setup conversation
        return await setup_profile(update, context)
    return ConversationHandler.END


async def setup_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Initiate the profile setup conversation."""
    message = update.effective_message
    context.user_data.clear()
    await message.reply_text(
        "Укажите ваш пол (male/female), возраст (let), рост (cm) и вес (kg) через пробел.\n"
        "Пример: male 38 188 95.5"
    )
    return GENDER_AGE_HEIGHT_WEIGHT


async def collect_basic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collect gender, age, height and weight."""
    text = update.message.text.strip()
    parts = text.split()
    if len(parts) != 4:
        await update.message.reply_text(
            "Пожалуйста, укажите данные в формате: пол возраст рост вес (example: male 38 180 80)."
        )
        return GENDER_AGE_HEIGHT_WEIGHT
    gender_raw, age_str, height_str, weight_str = parts
    gender = gender_raw.lower()
    if gender.startswith("m"):
        gender = "male"
    elif gender.startswith("f"):
        gender = "female"
    else:
        await update.message.reply_text(
            "Пол должен быть 'male' или 'female'. Попробуйте ещё раз."
        )
        return GENDER_AGE_HEIGHT_WEIGHT
    try:
        age = int(age_str)
        height_cm = float(height_str)
        weight_kg = float(weight_str)
    except ValueError:
        await update.message.reply_text(
            "Возраст, рост и вес должны быть числами. Попробуйте ещё раз."
        )
        return GENDER_AGE_HEIGHT_WEIGHT

    context.user_data["gender"] = gender
    context.user_data["age"] = age
    context.user_data["height_cm"] = height_cm
    context.user_data["weight_kg"] = weight_kg

    await update.message.reply_text(
        "Укажите цель: lose, maintain или gain, затем изменение веса (kg) и срок (days).\n"
        "Пример: lose 5 30"
    )
    return GOAL


async def collect_goal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collect goal type, delta and timeframe."""
    text = update.message.text.strip()
    parts = text.split()
    if len(parts) != 3:
        await update.message.reply_text(
            "Пожалуйста, укажите цель, изменение и срок в формате: lose 5 30."
        )
        return GOAL
    goal_raw, delta_str, days_str = parts
    goal_raw = goal_raw.lower()
    if goal_raw not in {"lose", "maintain", "gain"}:
        await update.message.reply_text(
            "Цель должна быть: lose, maintain или gain."
        )
        return GOAL
    if goal_raw == "lose":
        goal_type = "lose_weight"
    elif goal_raw == "gain":
        goal_type = "gain_weight"
    else:
        goal_type = "maintain"
    try:
        delta = float(delta_str)
        days = int(days_str)
    except ValueError:
        await update.message.reply_text(
            "Изменение веса и срок должны быть числами."
        )
        return GOAL
    context.user_data["goal_type"] = goal_type
    context.user_data["target_change_kg"] = delta
    context.user_data["timeframe_days"] = days

    await update.message.reply_text(
        "Уровень активности: sedentary, moderate или high."
    )
    return ACTIVITY


async def collect_activity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collect activity level."""
    level = update.message.text.strip().lower()
    mapping = {
        "низкий": "sedentary",
        "sedentary": "sedentary",
        "умеренный": "moderate",
        "moderate": "moderate",
        "высокий": "high",
        "high": "high",
    }
    activity = mapping.get(level)
    if not activity:
        await update.message.reply_text(
            "Уровень активности должен быть: sedentary/\u043d\u0438\u0437\u043a\u0438\u0439, moderate/\u0443\u043c\u0435\u0440\u0435\u043d\u043d\u044b\u0439 или high/\u0432\u044b\u0441\u043e\u043a\u0438\u0439."
        )
        return ACTIVITY
    context.user_data["activity_level"] = activity
    await update.message.reply_text(
        "Есть ли непереносимости / аллергии? Если нет, напишите 'нет'."
    )
    return RESTRICTIONS


def _parse_optional_list(text: str) -> List[str]:
    """Parse a comma or space separated list of items, ignoring 'нет'."""
    if not text or text.lower().strip() in {"\u043d\u0435\u0442", "no"}:
        return []
    parts = [p.strip() for p in text.replace(";", ",").split(",")]
    if len(parts) == 1:
        parts = [p.strip() for p in text.split()]
    return [p for p in parts if p]


async def collect_restrictions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collect intolerances and allergies."""
    context.user_data["restrictions"] = _parse_optional_list(update.message.text)
    await update.message.reply_text(
        "Продукты, которые не любите или избегаете? Если нет, напишите 'нет'."
    )
    return PREFERENCES


async def collect_preferences(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collect disliked foods."""
    context.user_data["preferences"] = _parse_optional_list(update.message.text)
    await update.message.reply_text(
        "Хронические заболевания / медицинские ограничения? Если нет, напишите 'нет'."
    )
    return MEDICAL


async def collect_medical(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collect medical conditions and complete profile."""
    context.user_data["medical"] = _parse_optional_list(update.message.text)
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
        restrictions=data["restrictions"],
        preferences=data["preferences"],
        medical=data["medical"],
    )
    user_id = update.effective_user.id
    storage.save_profile(user_id, profile)
    await update.message.reply_text(
        f"\u041f\u0440\u043e\u0444\u0438\u043b\u044c \u0441\u043e\u0437\u0434\u0430\u043d. \u0412\u0430\u0448\u0430 \u0446\u0435\u043b\u0435\u0432\u0430\u044f \u043a\u0430\u043b\u043e\u0440\u0438\u0439\u043d\u043e\u0441\u0442\u044c: {profile.norms.target_kcal} \u043a\u043a\u0430\u043b."
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the conversation."""
    await update.effective_message.reply_text("\u0421\u043e\u0437\u0434\u0430\u043d\u0438\u0435 \u043f\u0440\u043e\u0444\u0438\u043b\u044f \u043e\u0442\u043c\u0435\u043d\u0435\u043d\u043e.")
    return ConversationHandler.END


def main() -> None:
    """Main entry point. Instantiate the bot and run polling."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("TELEGRAM_BOT_TOKEN is not set; bot will not start.")
        return
    application = Application.builder().token(token).build()
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("setup_profile", setup_profile),
            CallbackQueryHandler(handle_button_click, pattern="^setup_profile$")
        ],
        states={
            GENDER_AGE_HEIGHT_WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_basic)],
            GOAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_goal)],
            ACTIVITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_activity)],
            RESTRICTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_restrictions)],
            PREFERENCES: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_preferences)],
            MEDICAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_medical)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)
    application.run_polling()


if __name__ == "__main__":
    main()

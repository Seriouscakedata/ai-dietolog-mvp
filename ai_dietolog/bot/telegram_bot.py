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
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from openai import AsyncOpenAI

from ..core import storage
from ..agents.profile_collector import build_profile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Conversation states: mandatory questions, optional details and confirmation
(MANDATORY, OPTIONAL, CONFIRM) = range(3)


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


async def handle_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle inline keyboard button clicks."""
    query = update.callback_query
    await query.answer()
    if query.data == "setup_profile":
        return await setup_profile(update, context)
    return ConversationHandler.END


async def setup_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for the profile setup conversation."""
    if update.callback_query:
        await update.callback_query.answer()
    context.user_data.clear()
    await update.effective_message.reply_text(
        "\U0001F4DD Давайте составим профиль. \n"
        "Ответьте одним сообщением на вопросы:\n"
        "1\uFE0F\u20E3 Рост (см)\n"
        "2\uFE0F\u20E3 Вес (кг)\n"
        "3\uFE0F\u20E3 Возраст\n"
        "4\uFE0F\u20E3 Целевой вес\n"
        "5\uFE0F\u20E3 Уровень активности\n"
        "6\uFE0F\u20E3 Срок достижения цели (дни)"
    )
    return MANDATORY


async def _extract(text: str, api_key: str, system: str) -> dict:
    """Helper to call OpenAI and parse JSON."""
    client = AsyncOpenAI(api_key=api_key)
    resp = await client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "system", "content": system}, {"role": "user", "content": text}],
        temperature=0,
    )
    return json.loads(resp.choices[0].message.content)


async def extract_basic(text: str, api_key: str) -> dict:
    """Parse mandatory profile fields from user text."""
    system = (
        "You are a nutrition assistant. Extract JSON with keys: age, height_cm, "
        "weight_kg, target_weight_kg, activity_level (sedentary/moderate/high), "
        "timeframe_days, gender. Use numbers without units and null if missing."
    )
    return await _extract(text, api_key, system)


async def extract_optional(text: str, api_key: str) -> dict:
    """Parse optional profile fields from user text."""
    system = (
        "You are a nutrition assistant. Extract JSON with optional keys: gender, "
        "waist_cm, bust_cm, hips_cm, restrictions (list), preferences (list), "
        "medical (list). Use null or empty list if not mentioned."
    )
    return await _extract(text, api_key, system)


def summarise_profile(data: dict) -> str:
    """Return a human-friendly summary of extracted data."""
    lines = []
    if data.get("gender"):
        lines.append(f"Пол: {data['gender']}")
    lines.extend(
        [
            f"Возраст: {data.get('age')}",
            f"Рост: {data.get('height_cm')} см",
            f"Вес: {data.get('weight_kg')} кг",
            f"Целевой вес: {data.get('target_weight_kg')} кг",
            f"Активность: {data.get('activity_level')}",
            f"Срок: {data.get('timeframe_days')} дн.",
        ]
    )
    if data.get("waist_cm"):
        lines.append(f"Талия: {data['waist_cm']} см")
    if data.get("bust_cm"):
        lines.append(f"Грудь: {data['bust_cm']} см")
    if data.get("hips_cm"):
        lines.append(f"Бедра: {data['hips_cm']} см")
    if data.get("restrictions"):
        lines.append("Непереносимости: " + ", ".join(data["restrictions"]))
    if data.get("preferences"):
        lines.append("Предпочтения: " + ", ".join(data["preferences"]))
    if data.get("medical"):
        lines.append("Медицинские ограничения: " + ", ".join(data["medical"]))
    return "\n".join(lines)


async def _ai_explain(prompt: str, api_key: str) -> str:
    """Return a short explanation from the language model."""
    client = AsyncOpenAI(api_key=api_key)
    resp = await client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {
                "role": "system",
                "content": (
                    "Ты вежливый русскоязычный ассистент-диетолог. "
                    "Кратко поясни пользователю возникшую проблему."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.5,
    )
    return resp.choices[0].message.content.strip()


async def validate_mandatory(data: dict, api_key: str) -> str | None:
    """Return an error message if values look unrealistic.  Uses LLM for text."""
    required = [
        "age",
        "height_cm",
        "weight_kg",
        "target_weight_kg",
        "timeframe_days",
        "activity_level",
    ]
    missing = [f for f in required if data.get(f) is None]
    if missing:
        mapping = {
            "age": "возраст",
            "height_cm": "рост",
            "weight_kg": "вес",
            "target_weight_kg": "целевой вес",
            "timeframe_days": "срок",
            "activity_level": "уровень активности",
        }
        human = ", ".join(mapping[m] for m in missing)
        return await _ai_explain(f"Не удалось распознать: {human}.", api_key)
    try:
        age = int(data["age"])
        height = float(data["height_cm"])
        weight = float(data["weight_kg"])
        target = float(data["target_weight_kg"])
        timeframe = int(data["timeframe_days"])
    except (TypeError, ValueError):
        return await _ai_explain("Проверьте вводимые числа.", api_key)
    if not 100 <= height <= 250:
        return await _ai_explain("Рост выглядит нереалистично.", api_key)
    if not 30 <= weight <= 300:
        return await _ai_explain("Вес выглядит нереалистично.", api_key)
    if not 10 <= age <= 100:
        return await _ai_explain("Возраст выглядит нереалистично.", api_key)
    if not 30 <= target <= 300:
        return await _ai_explain("Целевой вес выглядит нереалистично.", api_key)
    if timeframe <= 0:
        return await _ai_explain("Срок должен быть больше нуля.", api_key)
    diff = abs(weight - target)
    max_weekly = 1.0
    weeks = timeframe / 7
    if weeks > 0 and diff / weeks > max_weekly:
        needed_weeks = diff / max_weekly
        min_days = int(needed_weeks * 7)
        prompt = (
            "Цель слишком быстрая. Безопасный темп — не более 1 кг в неделю. "
            f"Для выбранной цели потребуется не менее {min_days} дней."
        )
        return await _ai_explain(prompt, api_key)
    return None


async def collect_basic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cfg = load_config()
    api_key = cfg.get("openai_api_key") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        await update.message.reply_text("OpenAI API key не настроен")
        return ConversationHandler.END
    try:
        data = await extract_basic(update.message.text, api_key)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Mandatory extraction failed: %s", exc)
        await update.message.reply_text("Не удалось разобрать сообщение, попробуйте ещё раз")
        return MANDATORY
    error = await validate_mandatory(data, api_key)
    if error:
        await update.message.reply_text(error + " Попробуйте ещё раз")
        return MANDATORY
    context.user_data["mandatory"] = data
    await update.message.reply_text(
        "\U0001F4DD Теперь можете указать доп. информацию: пол, окружности, предпочтения или аллергию. Если ничего добавлять не хотите, напишите 'нет'."
    )
    return OPTIONAL


async def collect_optional(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cfg = load_config()
    api_key = cfg.get("openai_api_key") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        await update.message.reply_text("OpenAI API key не настроен")
        return ConversationHandler.END
    text = update.message.text.strip()
    if text.lower() == "нет":
        data = {}
    else:
        try:
            data = await extract_optional(text, api_key)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Optional extraction failed: %s", exc)
            await update.message.reply_text("Не удалось разобрать сообщение, попробуйте ещё раз")
            return OPTIONAL
    context.user_data["optional"] = data
    merged = {**context.user_data.get("mandatory", {}), **data}
    summary = summarise_profile(merged)
    context.user_data["profile"] = merged
    await update.message.reply_text(summary + "\nВсе верно? (да/нет)")
    return CONFIRM


async def finish_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text.strip().lower().startswith("д"):
        data = context.user_data.get("profile", {})
        gender = data.get("gender") or "female"
        target_change = float(data["weight_kg"]) - float(data["target_weight_kg"])
        goal_type = "maintain"
        if target_change > 0:
            goal_type = "lose_weight"
        elif target_change < 0:
            goal_type = "gain_weight"
        profile = build_profile(
            gender=gender,
            age=int(data["age"]),
            height_cm=float(data["height_cm"]),
            weight_kg=float(data["weight_kg"]),
            activity_level=data["activity_level"],
            goal_type=goal_type,
            target_change_kg=target_change,
            timeframe_days=int(data["timeframe_days"]),
            restrictions=data.get("restrictions"),
            preferences=data.get("preferences"),
            medical=data.get("medical"),
        )
        for key in ("waist_cm", "bust_cm", "hips_cm"):
            if data.get(key) is not None:
                profile.personal[key] = data[key]
        storage.save_profile(update.effective_user.id, profile)
        await update.message.reply_text(
            f"Профиль создан. Целевая калорийность: {profile.norms.target_kcal} ккал."
        )
        return ConversationHandler.END
    await update.message.reply_text("Опишите данные заново:")
    return MANDATORY


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text("Создание профиля отменено.")
    return ConversationHandler.END


def main() -> None:
    """Main entry point.  Instantiate the bot and run polling."""
    cfg = load_config()
    token = cfg.get("telegram_bot_token") or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN is not set; bot will not start.")
        return
    application = Application.builder().token(token).build()
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("setup_profile", setup_profile),
            CallbackQueryHandler(setup_profile, pattern="^setup_profile$")
        ],
        states={
            MANDATORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_basic)],
            OPTIONAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_optional)],
            CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, finish_profile)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_button_click))
    application.run_polling()


if __name__ == "__main__":
    main()

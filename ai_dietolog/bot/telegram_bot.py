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
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
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
from ..core.schema import Profile, Today, Meal, Total, ClosedDay, History, Counters
from ..agents.profile_collector import build_profile
from ..agents import profile_editor
from ..agents.intake import intake
from ..agents.contextual import analyze_context

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Conversation states for conversations
(MANDATORY, OPTIONAL, CONFIRM, EDIT, MEAL_TYPE, MEAL_DESC, SET_PERCENT) = range(7)


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
    if query.data == "setup_profile":
        return await setup_profile(update, context)
    if query.data == "edit_profile":
        return await start_edit_profile(update, context)
    await query.answer()
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


def summarise_profile_obj(profile: Profile) -> str:
    """Return a concise summary of a ``Profile`` object."""
    p = profile.personal
    g = profile.goals
    lines = [
        f"Пол: {p.get('gender')}",
        f"Возраст: {p.get('age')}",
        f"Рост: {p.get('height_cm')} см",
        f"Вес: {p.get('weight_kg')} кг",
        f"Активность: {p.get('activity_level')}",
    ]
    goal_type = g.get("type")
    target = g.get("target_change_kg")
    timeframe = g.get("timeframe_days")
    if goal_type == "lose_weight":
        goal_desc = f"снижение на {abs(target)} кг за {timeframe} дн."
    elif goal_type == "gain_weight":
        goal_desc = f"набор {abs(target)} кг за {timeframe} дн."
    else:
        goal_desc = "поддержание веса"
    lines.append("Цель: " + goal_desc)
    if profile.restrictions:
        lines.append("Ограничения: " + ", ".join(profile.restrictions))
    return "\n".join(lines)


def meal_card(meal: Meal) -> str:
    """Return short text describing a meal."""
    names = ", ".join(i.name for i in meal.items)
    t = meal.total
    prefix = "Черновик: " if meal.pending else ""
    return (
        f"{prefix}{meal.type}: {names}\n"
        f"К: {t.kcal} ккал, Б: {t.protein_g} г, Ж: {t.fat_g} г, У: {t.carbs_g} г"
    )


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


async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Send the current profile summary with an edit button."""
    profile = storage.load_profile(update.effective_user.id, Profile)
    if not profile.personal:
        await update.message.reply_text("Профиль не найден. Используйте /setup_profile.")
        return ConversationHandler.END
    text = summarise_profile_obj(profile)
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("\u270f\ufe0f Изменить профиль", callback_data="edit_profile")]]
    )
    await update.message.reply_text(text, reply_markup=keyboard)
    return ConversationHandler.END


async def start_edit_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask the user to describe profile changes."""
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("Опишите изменения в профиле:")
    return EDIT


async def apply_profile_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Update the profile via LLM and save it."""
    cfg = load_config()
    api_key = cfg.get("openai_api_key") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        await update.message.reply_text("OpenAI API key не настроен")
        return ConversationHandler.END
    profile = storage.load_profile(update.effective_user.id, Profile)
    try:
        updated_dict = await profile_editor.update_profile(
            profile.model_dump(), update.message.text, api_key
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Profile update failed: %s", exc)
        await update.message.reply_text("Не удалось обработать изменения.")
        return ConversationHandler.END
    try:
        new_profile = Profile.parse_obj(updated_dict)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Profile validation failed: %s", exc)
        await update.message.reply_text("Получены некорректные данные.")
        return ConversationHandler.END
    storage.save_profile(update.effective_user.id, new_profile)
    macros = new_profile.norms.macros
    await update.message.reply_text(
        "Профиль обновлён. "
        f"Целевая калорийность {new_profile.norms.target_kcal} ккал.\n"
        f"Б: {macros['protein_g']} г, Ж: {macros['fat_g']} г, У: {macros['carbs_g']} г"
    )
    return ConversationHandler.END


async def add_meal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start meal logging by asking for meal type."""
    keyboard = ReplyKeyboardMarkup(
        [["Завтрак", "Обед"], ["Ужин", "Перекус"]],
        one_time_keyboard=True,
        resize_keyboard=True,
    )
    await update.message.reply_text("Выберите тип приёма пищи:", reply_markup=keyboard)
    return MEAL_TYPE


async def receive_meal_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["meal_type"] = update.message.text.strip()
    await update.message.reply_text(
        "Пришлите фото, голосовое или текстовое описание блюда.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return MEAL_DESC


async def receive_meal_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    desc = update.message.caption or update.message.text or ""
    image_bytes = None
    if update.message.photo:
        file = await update.message.photo[-1].get_file()
        image_bytes = await file.download_as_bytearray()
    meal_type = context.user_data.get("meal_type", "Перекус")
    meal = await intake(image_bytes, desc, meal_type)
    storage.append_meal(update.effective_user.id, meal)
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✔ Подтвердить", callback_data=f"confirm:{meal.id}"),
                InlineKeyboardButton("✏\ufe0f Редактировать", callback_data=f"edit:{meal.id}"),
                InlineKeyboardButton("Ὕ1 Удалить", callback_data=f"delete:{meal.id}"),
            ]
        ]
    )
    await update.message.reply_text(meal_card(meal), reply_markup=keyboard)
    return ConversationHandler.END


async def confirm_meal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    meal_id = query.data.split(":", 1)[1]
    today = storage.load_today(update.effective_user.id)
    meal = next((m for m in today.meals if m.id == meal_id), None)
    if not meal:
        await query.message.reply_text("Запись не найдена")
        return
    if not meal.pending:
        await query.message.reply_text("Уже подтверждено")
        return
    profile = storage.load_profile(update.effective_user.id, Profile)
    cfg = load_config()
    result = await analyze_context(
        profile.norms.model_dump(), today.summary, meal.total, cfg
    )
    meal.pending = False
    today.summary = Total(**result.get("summary", {}))
    storage.save_today(update.effective_user.id, today)
    await query.message.edit_text(meal_card(meal))
    comment = result.get("context_comment")
    if comment:
        await query.message.reply_text(comment)


async def start_edit_meal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["edit_meal_id"] = query.data.split(":", 1)[1]
    await query.message.reply_text("Введите процент съеденного (1-100):")
    return SET_PERCENT


def _scale_total(total: Total, factor: float) -> Total:
    data = {k: int(round(getattr(total, k) * factor)) for k in total.model_fields}
    return Total(**data)


async def apply_percent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    try:
        percent = int(update.message.text)
    except ValueError:
        await update.message.reply_text("Введите число от 1 до 100")
        return SET_PERCENT
    if not 1 <= percent <= 100:
        await update.message.reply_text("Введите число от 1 до 100")
        return SET_PERCENT
    meal_id = context.user_data.get("edit_meal_id")
    today = storage.load_today(user_id)
    meal = next((m for m in today.meals if m.id == meal_id), None)
    if not meal:
        await update.message.reply_text("Запись не найдена")
        return ConversationHandler.END
    factor = percent / meal.percent_eaten
    old_total = meal.total
    meal.items = [i.scale(factor) for i in meal.items]
    meal.total = _scale_total(meal.total, factor)
    meal.percent_eaten = percent
    if not meal.pending:
        for field in today.summary.model_fields:
            value = getattr(today.summary, field) - getattr(old_total, field) + getattr(meal.total, field)
            setattr(today.summary, field, value)
    storage.save_today(user_id, today)
    await update.message.reply_text("Изменено")
    return ConversationHandler.END


async def delete_meal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    meal_id = query.data.split(":", 1)[1]
    user_id = update.effective_user.id
    today = storage.load_today(user_id)
    meal = next((m for m in today.meals if m.id == meal_id), None)
    if not meal:
        await query.message.reply_text("Запись не найдена")
        return
    if not meal.pending:
        for field in today.summary.model_fields:
            setattr(today.summary, field, getattr(today.summary, field) - getattr(meal.total, field))
    today.meals = [m for m in today.meals if m.id != meal_id]
    storage.save_today(user_id, today)
    await query.message.edit_text("Удалено")


async def close_day(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    today = storage.load_today(user_id)
    confirmed = [m for m in today.meals if not m.pending]
    if not confirmed:
        await update.message.reply_text("Нет подтверждённых приёмов пищи")
        return
    history = storage.read_json(storage.json_path(user_id, "history.json"), History)
    counters = storage.read_json(storage.json_path(user_id, "counters.json"), Counters)
    closed = ClosedDay(
        date=datetime.utcnow().date().isoformat(),
        summary=today.summary,
        meals=confirmed,
    )
    history.append_day(closed, max_days=30)
    counters.total_days_closed += 1
    storage.write_json(storage.json_path(user_id, "history.json"), history)
    storage.write_json(storage.json_path(user_id, "counters.json"), counters)
    storage.save_today(user_id, Today())
    await update.message.reply_text("День закрыт")


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a short AI-generated explanation of unexpected errors."""
    logger.exception("Unhandled error: %s", context.error)
    cfg = load_config()
    api_key = cfg.get("openai_api_key") or os.getenv("OPENAI_API_KEY")
    if isinstance(update, Update) and update.effective_message and api_key:
        try:
            msg = await _ai_explain("Произошла техническая ошибка", api_key)
            await update.effective_message.reply_text(msg)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to send error message: %s", exc)


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

    edit_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_edit_profile, pattern="^edit_profile$")],
        states={
            EDIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, apply_profile_edit)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    meal_conv = ConversationHandler(
        entry_points=[CommandHandler("add_meal", add_meal)],
        states={
            MEAL_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_meal_type)],
            MEAL_DESC: [MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, receive_meal_desc)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    edit_meal_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_edit_meal, pattern="^edit:")],
        states={
            SET_PERCENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, apply_percent)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    application.add_handler(edit_conv)
    application.add_handler(meal_conv)
    application.add_handler(edit_meal_conv)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("profile", show_profile))
    application.add_handler(CommandHandler("close_day", close_day))
    application.add_handler(CallbackQueryHandler(confirm_meal, pattern="^confirm:"))
    application.add_handler(CallbackQueryHandler(delete_meal, pattern="^delete:"))
    application.add_handler(CallbackQueryHandler(handle_button_click))
    application.add_error_handler(handle_error)
    application.run_polling()


if __name__ == "__main__":
    main()

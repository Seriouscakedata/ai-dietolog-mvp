from __future__ import annotations

import json
import logging
import os

from openai import AsyncOpenAI  # noqa: F401
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ConversationHandler, ContextTypes

from ...agents import profile_editor
from ...agents.profile_collector import build_profile
from ...core import storage
from ...core.config import agent_llm, load_config
from ...core.llm import ask_llm
from ...core.prompts import (
    EXTRACT_FIELD_ACTIVITY,
    EXTRACT_FIELD_NUMERIC,
    EXTRACT_BASIC,
    EXTRACT_OPTIONAL,
    AI_EXPLAIN,
)
from ...core.schema import Profile

logger = logging.getLogger(__name__)

# Conversation states for profile setup and editing
(MANDATORY, OPTIONAL, CONFIRM, EDIT) = range(4)

# Order of mandatory profile questions for step-by-step filling
MANDATORY_ORDER = [
    ("height_cm", "Укажите рост в сантиметрах:"),
    ("weight_kg", "Ваш текущий вес (кг):"),
    ("age", "Возраст:"),
    ("target_weight_kg", "Желаемый вес (кг):"),
    (
        "activity_level",
        "Уровень активности (sedentary/moderate/high):",
    ),
    ("timeframe_days", "За сколько дней хотите достичь цели?"),
]


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

async def ai_explain(prompt: str, api_key: str) -> str:
    """Return a short explanation from the language model."""
    cfg = {**load_config(), "openai_api_key": api_key}
    provider, model = agent_llm("ai_explain", cfg)
    messages = [
        {
            "role": "system",
            "content": (AI_EXPLAIN.render()),
        },
        {"role": "user", "content": prompt},
    ]
    if provider == "openai":
        client = AsyncOpenAI(api_key=api_key)
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.5,
        )
        content = resp.choices[0].message.content
    else:
        content = await ask_llm(
            messages,
            model=model,
            provider=provider,
            temperature=0.5,
            cfg=cfg,
        )
    return content.strip()


async def _extract(text: str, api_key: str, system: str) -> dict:
    """Helper to call a language model and parse JSON."""
    cfg = {**load_config(), "openai_api_key": api_key}
    provider, model = agent_llm("extract", cfg)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": text},
    ]
    if provider == "openai":
        client = AsyncOpenAI(api_key=api_key)
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0,
        )
        content = resp.choices[0].message.content
    else:
        content = await ask_llm(
            messages,
            model=model,
            provider=provider,
            temperature=0,
            cfg=cfg,
        )
    return json.loads(content)


async def extract_field(field: str, text: str, api_key: str) -> dict:
    """Extract a single profile field from ``text`` using OpenAI."""
    if field == "activity_level":
        system = EXTRACT_FIELD_ACTIVITY.render()
    else:
        system = EXTRACT_FIELD_NUMERIC.render(field=field)
    return await _extract(text, api_key, system)


async def extract_basic(text: str, api_key: str) -> dict:
    """Parse mandatory profile fields from user text."""
    system = EXTRACT_BASIC.render()
    return await _extract(text, api_key, system)


async def extract_optional(text: str, api_key: str) -> dict:
    """Parse optional profile fields from user text."""
    system = EXTRACT_OPTIONAL.render()
    return await _extract(text, api_key, system)


async def validate_mandatory(data: dict, api_key: str) -> str | None:
    """Return an error message if values look unrealistic."""
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
        return await ai_explain(f"Не удалось распознать: {human}.", api_key)
    try:
        age = int(data["age"])
        height = float(data["height_cm"])
        weight = float(data["weight_kg"])
        target = float(data["target_weight_kg"])
        timeframe = int(data["timeframe_days"])
    except (TypeError, ValueError):
        return await ai_explain("Проверьте вводимые числа.", api_key)
    if not 100 <= height <= 250:
        return await ai_explain("Рост выглядит нереалистично.", api_key)
    if not 30 <= weight <= 300:
        return await ai_explain("Вес выглядит нереалистично.", api_key)
    if not 10 <= age <= 100:
        return await ai_explain("Возраст выглядит нереалистично.", api_key)
    if not 30 <= target <= 300:
        return await ai_explain("Целевой вес выглядит нереалистично.", api_key)
    if timeframe <= 0:
        return await ai_explain("Срок должен быть больше нуля.", api_key)
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
        return await ai_explain(prompt, api_key)
    return None

async def setup_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for the profile setup conversation."""
    if update.callback_query:
        await update.callback_query.answer()
    context.user_data.clear()
    context.user_data["language"] = update.effective_user.language_code or "ru"
    context.user_data["mandatory"] = {}
    context.user_data["step"] = 0
    await update.effective_message.reply_text(
        "\U0001f4dd Давайте составим профиль. Ответьте на несколько вопросов."
    )
    await update.effective_message.reply_text(MANDATORY_ORDER[0][1])
    return MANDATORY


async def collect_basic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cfg = load_config()
    api_key = cfg.get("openai_api_key") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        await update.message.reply_text("OpenAI API key не настроен")
        return ConversationHandler.END
    step = context.user_data.get("step", 0)
    field, _prompt = MANDATORY_ORDER[step]
    try:
        data = await extract_field(field, update.message.text, api_key)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Field extraction failed: %s", exc)
        await update.message.reply_text("Не удалось разобрать, попробуйте ещё раз")
        return MANDATORY
    value = data.get(field)
    if value is None:
        await update.message.reply_text("Не удалось распознать ответ, повторите")
        return MANDATORY
    context.user_data["mandatory"][field] = value
    step += 1
    if step < len(MANDATORY_ORDER):
        context.user_data["step"] = step
        await update.message.reply_text(MANDATORY_ORDER[step][1])
        return MANDATORY
    error = await validate_mandatory(context.user_data["mandatory"], api_key)
    if error:
        await update.message.reply_text(error + " Попробуйте заново")
        context.user_data["mandatory"] = {}
        context.user_data["step"] = 0
        await update.message.reply_text(MANDATORY_ORDER[0][1])
        return MANDATORY
    await update.message.reply_text(
        "\U0001f4dd Теперь можете указать доп. информацию: пол, окружности, предпочтения или аллергию. Если ничего добавлять не хотите, напишите 'нет'."
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
            await update.message.reply_text(
                "Не удалось разобрать сообщение, попробуйте ещё раз"
            )
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
        cfg = load_config()
        profile = await build_profile(
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
            cfg=cfg,
            language=context.user_data.get("language", "ru"),
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
    profile = storage.load_profile(update.effective_user.id, Profile)
    if not profile.personal:
        await update.message.reply_text(
            "Профиль не найден. Используйте /setup_profile."
        )
        return ConversationHandler.END
    text = summarise_profile_obj(profile)
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "\u270f\ufe0f Изменить профиль", callback_data="edit_profile"
                )
            ]
        ]
    )
    await update.message.reply_text(text, reply_markup=keyboard)
    return ConversationHandler.END


async def start_edit_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("Опишите изменения в профиле:")
    return EDIT


async def apply_profile_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cfg = load_config()
    api_key = cfg.get("openai_api_key") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        await update.message.reply_text("OpenAI API key не настроен")
        return ConversationHandler.END
    profile = storage.load_profile(update.effective_user.id, Profile)
    try:
        updated_dict = await profile_editor.update_profile(
            profile.model_dump(),
            update.message.text,
            api_key,
            language=context.user_data.get("language", "ru"),
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

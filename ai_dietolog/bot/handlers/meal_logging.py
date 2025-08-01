from __future__ import annotations

import logging
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.error import TimedOut
from telegram.ext import ConversationHandler, ContextTypes

from ...agents.contextual import analyze_context
from ...agents.intake import intake
from ...agents.meal_editor import edit_meal
from ...core import storage
from ...core.config import load_config
from ...core.schema import Meal, Profile, Total, Today
from .daily_review import format_stats

logger = logging.getLogger(__name__)

comment_conv: ConversationHandler | None = None

# Conversation states for meal logging and editing
(MEAL_TYPE, MEAL_DESC, SET_PERCENT, SET_COMMENT) = range(4)


def meal_card(meal: Meal) -> str:
    """Return short text describing a meal."""
    names = ", ".join(i.name for i in meal.items)
    t = meal.total
    prefix = "Черновик: " if meal.pending else ""
    return (
        f"{prefix}{meal.type}: {names}\n"
        f"К: {t.kcal} ккал, Б: {t.protein_g} г, Ж: {t.fat_g} г, У: {t.carbs_g} г"
    )


def meal_breakdown(meal: Meal) -> str:
    """Return a detailed breakdown of a meal."""
    lines = [f"{meal.type}:"]
    for it in meal.items:
        part = f"- {it.name}"
        if it.weight_g:
            part += f" {it.weight_g} г"
        part += (
            f" ({it.kcal} ккал, Б:{it.protein_g} г, Ж:{it.fat_g} г, У:{it.carbs_g} г)"
        )
        lines.append(part)
    t = meal.total
    lines.append(
        f"Итого: {t.kcal} ккал, Б:{t.protein_g} г, Ж:{t.fat_g} г, У:{t.carbs_g} г"
    )
    if meal.comment:
        lines.append(f"Комментарий: {meal.comment}")
    prefix = "Черновик: " if meal.pending else ""
    return prefix + "\n".join(lines)


def _end_comment_conv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Terminate the comment conversation if it's active."""
    global comment_conv
    if comment_conv is None:
        return
    try:
        key = comment_conv._get_key(update)
        if key in comment_conv._conversations:
            comment_conv._update_state(ConversationHandler.END, key)
    except Exception:  # noqa: BLE001
        pass
    context.user_data.pop("comment_meal_id", None)
    context.user_data.pop("comment_message", None)


def _scale_total(total: Total, factor: float) -> Total:
    data = {k: int(round(getattr(total, k) * factor)) for k in total.model_fields}
    return Total(**data)

async def add_meal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start meal logging by asking for meal type."""
    _end_comment_conv(update, context)
    context.user_data["language"] = update.effective_user.language_code or "ru"
    keyboard = ReplyKeyboardMarkup(
        [["Завтрак", "Обед"], ["Ужин", "Перекус"]],
        one_time_keyboard=True,
        resize_keyboard=True,
    )
    await update.message.reply_text("Выберите тип приёма пищи:", reply_markup=keyboard)
    return MEAL_TYPE


async def receive_meal_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["meal_type"] = update.message.text.strip()
    history = context.user_data.setdefault("history", [])
    history.append(update.message.text.strip())
    del history[:-20]
    await update.message.reply_text(
        "Пришлите фото, голосовое или текстовое описание блюда.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return MEAL_DESC


async def receive_meal_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    history = context.user_data.setdefault("history", [])
    desc = update.message.caption if update.message.caption else update.message.text
    if desc:
        history.append(desc)
        del history[:-20]
    image_bytes = None
    file_id = None
    if update.message.photo:
        photo = update.message.photo[-1]
        try:
            file = await photo.get_file()
            image_bytes = await file.download_as_bytearray()
            file_id = photo.file_id
        except TimedOut:
            await update.message.reply_text(
                "Не удалось загрузить фото, попробуйте ещё раз."
            )
            return MEAL_DESC
    meal_type = context.user_data.get("meal_type", "Перекус")
    meal = await intake(
        image_bytes,
        desc,
        meal_type,
        language=context.user_data.get("language", "ru"),
        history=context.user_data.get("history"),
    )
    meal.user_desc = desc
    meal.image_file_id = file_id
    storage.append_meal(update.effective_user.id, meal)
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✔ Подтвердить", callback_data=f"confirm:{meal.id}"
                ),
                InlineKeyboardButton(
                    "✍️ Комментарии", callback_data=f"comment:{meal.id}"
                ),
                InlineKeyboardButton("🗑 Удалить", callback_data=f"delete:{meal.id}"),
            ]
        ]
    )
    text = meal_breakdown(meal)
    if meal.clarification:
        text += f"\n\n❓ {meal.clarification}"
    if file_id:
        await update.message.reply_photo(
            photo=file_id, caption=text, reply_markup=keyboard
        )
    else:
        await update.message.reply_text(text, reply_markup=keyboard)
    return ConversationHandler.END


async def confirm_meal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    _end_comment_conv(update, context)
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
        profile.norms.model_dump(),
        today.summary,
        meal.total,
        cfg,
        language=context.user_data.get("language", "ru"),
        history=context.user_data.get("history"),
    )
    meal.pending = False
    today.summary = Total(**result.get("summary", {}))
    comment = result.get("context_comment")
    if comment:
        meal.comment = f"{meal.comment or ''} {comment}".strip()
        history = context.user_data.setdefault("history", [])
        history.append(comment)
        del history[:-20]
    storage.save_today(update.effective_user.id, today)
    if query.message.photo:
        await query.message.edit_caption(meal_card(meal))
    else:
        await query.message.edit_text(meal_card(meal))
    stats = format_stats(profile.norms, today.summary, comment)
    await query.message.reply_text(stats, parse_mode="Markdown")


async def start_edit_meal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _end_comment_conv(update, context)
    context.user_data["edit_meal_id"] = query.data.split(":", 1)[1]
    await query.message.reply_text("Введите процент съеденного (1-100):")
    return SET_PERCENT


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
            value = (
                getattr(today.summary, field)
                - getattr(old_total, field)
                + getattr(meal.total, field)
            )
            setattr(today.summary, field, value)
    storage.save_today(user_id, today)
    await update.message.reply_text("Изменено")
    return ConversationHandler.END


async def start_comment_meal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _end_comment_conv(update, context)
    context.user_data["comment_meal_id"] = query.data.split(":", 1)[1]
    context.user_data["comment_message"] = (
        query.message.chat_id,
        query.message.message_id,
    )
    await query.message.reply_text("Напишите комментарий к блюду:")
    return SET_COMMENT


async def apply_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    meal_id = context.user_data.get("comment_meal_id")
    comment = update.message.text.strip()
    history = context.user_data.setdefault("history", [])
    if comment:
        history.append(comment)
        del history[:-20]
    today = storage.load_today(user_id)
    meal = next((m for m in today.meals if m.id == meal_id), None)
    if not meal:
        await update.message.reply_text("Запись не найдена")
        return ConversationHandler.END
    old_total = meal.total
    meal.comment = f"{meal.comment or ''} {comment}".strip()
    user_desc = f"{meal.user_desc} {comment}".strip()
    updated = await edit_meal(
        meal,
        comment,
        language=context.user_data.get("language", "ru"),
        history=context.user_data.get("history"),
    )
    meal.user_desc = user_desc
    meal.clarification = updated.clarification
    meal.items = updated.items
    meal.total = updated.total
    if not meal.pending:
        for field in today.summary.model_fields:
            value = (
                getattr(today.summary, field)
                - getattr(old_total, field)
                + getattr(meal.total, field)
            )
            setattr(today.summary, field, value)
    storage.save_today(user_id, today)
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✍\ufe0f Комментарии", callback_data=f"comment:{meal.id}"
                ),
                InlineKeyboardButton("🗑 Удалить", callback_data=f"delete:{meal.id}"),
            ]
        ]
    )
    text = meal_breakdown(meal)
    if meal.clarification:
        text += f"\n\n❓ {meal.clarification}"
    chat_id, msg_id = context.user_data.get(
        "comment_message",
        (update.effective_chat.id, update.effective_message.message_id),
    )
    if meal.image_file_id:
        await context.bot.edit_message_caption(
            chat_id=chat_id, message_id=msg_id, caption=text, reply_markup=keyboard
        )
    else:
        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=msg_id, text=text, reply_markup=keyboard
        )
    _end_comment_conv(update, context)
    return ConversationHandler.END


async def delete_meal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    _end_comment_conv(update, context)
    meal_id = query.data.split(":", 1)[1]
    user_id = update.effective_user.id
    today = storage.load_today(user_id)
    meal = next((m for m in today.meals if m.id == meal_id), None)
    if not meal:
        await query.message.reply_text("Запись не найдена")
        return
    if not meal.pending:
        for field in today.summary.model_fields:
            setattr(
                today.summary,
                field,
                getattr(today.summary, field) - getattr(meal.total, field),
            )
    today.meals = [m for m in today.meals if m.id != meal_id]
    storage.save_today(user_id, today)
    if query.message.photo:
        await query.message.edit_caption("Удалено")
    else:
        await query.message.edit_text("Удалено")

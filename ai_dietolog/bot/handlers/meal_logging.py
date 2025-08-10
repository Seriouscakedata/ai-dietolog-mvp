from __future__ import annotations

import asyncio
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
    logger.info(
        "Process: add_meal | Agent: meal_logging | User: %s | Action: request meal type",
        update.effective_user.id,
    )
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
    meal_type = update.message.text.strip()
    logger.info(
        "Process: receive_meal_type | Agent: meal_logging | User: %s | Meal type: %s",
        update.effective_user.id,
        meal_type,
    )
    context.user_data["meal_type"] = meal_type
    history = context.user_data.setdefault("history", [])
    history.append(meal_type)
    del history[:-20]
    await update.message.reply_text(
        "Пришлите фото, голосовое или текстовое описание блюда.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return MEAL_DESC


async def receive_meal_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    history = context.user_data.setdefault("history", [])
    desc = update.message.caption if update.message.caption else update.message.text
    logger.info(
        "Process: receive_meal_desc | Agent: meal_logging | User: %s | Description received",
        update.effective_user.id,
    )
    if desc:
        history.append(desc)
        del history[:-20]
    image_bytes = None
    file_id = None
    if update.message.photo:
        photo = update.message.photo[-1]
        photo_id = getattr(photo, "file_id", "<no-id>")
        logger.info(
            "Process: receive_meal_desc | Agent: meal_logging | User: %s | Photo received: %s",
            update.effective_user.id,
            photo_id,
        )
        try:
            file = await photo.get_file()
            image_bytes = await file.download_as_bytearray()
            file_id = photo_id
            logger.info(
                "Process: receive_meal_desc | Agent: meal_logging | User: %s | Photo downloaded: %s",
                update.effective_user.id,
                file_id,
            )
        except TimedOut:
            await update.message.reply_text(
                "Не удалось загрузить фото, попробуйте ещё раз."
            )
            return MEAL_DESC
    else:
        logger.info(
            "Process: receive_meal_desc | Agent: meal_logging | User: %s | No photo provided",
            update.effective_user.id,
        )
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
    if hasattr(context, "user_data"):
        context.user_data.setdefault("meals", {})[meal.id] = meal
    logger.info(
        "Process: receive_meal_desc | Agent: meal_logging | User: %s | Meal recognised: %s | Total: %s",
        update.effective_user.id,
        [i.name for i in meal.items],
        meal.total.model_dump(),
    )
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
    logger.info(
        "Process: confirm_meal | Agent: meal_logging | User: %s",
        update.effective_user.id,
    )
    query = update.callback_query
    # Answer the callback in the background so we can persist the meal
    # before yielding control back to the event loop.  This prevents a
    # race where the user immediately finishes the day and the confirmation
    # has not yet been written to ``today.json``.
    asyncio.create_task(query.answer())
    _end_comment_conv(update, context)
    meal_id = query.data.split(":", 1)[1]
    user_id = update.effective_user.id
    today = storage.load_today(user_id)
    meal = next((m for m in today.meals if m.id == meal_id), None)
    if not meal:
        meal = getattr(context, "user_data", {}).get("meals", {}).get(meal_id)
        if not meal:
            logger.warning(
                "Meal %s not found for user %s", meal_id, update.effective_user.id
            )
            await query.message.reply_text("Запись не найдена")
            return
        logger.debug("Using in-memory meal %s for confirmation", meal_id)
        # Persist the meal immediately so that subsequent reads load it from
        # ``today.json``.  This avoids situations where the in-memory object
        # is appended to a transient ``Today`` instance that was never written
        # to disk, leaving ``today.json`` empty and causing ``finish_day`` to
        # miss the confirmed meal.
        storage.append_meal(user_id, meal)
        today = storage.load_today(user_id)
        logger.debug("Appended in-memory meal %s to today's log", meal_id)
    logger.info("Confirming meal %s for user %s", meal_id, user_id)
    if not meal.pending:
        await query.message.reply_text("Уже подтверждено")
        return

    # Immediately mark the meal as confirmed and persist the change before
    # calling the (potentially slow) ``analyze_context`` LLM.  This avoids a
    # race where the user finishes the day while confirmation is still in
    # progress and the meal has not yet been saved to ``today.json``.
    # Capture the day summary before confirming the meal so that
    # ``analyze_context`` receives the pre-meal totals.  The LLM then
    # returns updated totals for the whole day, which we merge back into
    # ``today.summary`` after analysis.  Without this, the totals would be
    # counted twice because we would send the already-updated summary.
    previous_summary = today.summary.model_copy()

    today.confirm_meal(meal.id)
    storage.save_today(user_id, today)
    logger.info(
        "Meal %s persisted for user %s | path=%s | summary=%s",
        meal_id,
        user_id,
        storage.today_path(user_id),
        today.summary.model_dump(),
    )

    profile = storage.load_profile(user_id, Profile)
    cfg = load_config()
    result = await analyze_context(
        profile.norms.model_dump(),
        previous_summary,
        meal.total,
        cfg,
        language=context.user_data.get("language", "ru"),
        history=context.user_data.get("history"),
    )

    comment = result.get("context_comment")
    if comment:
        meal.comment = f"{meal.comment or ''} {comment}".strip()
        history = context.user_data.setdefault("history", [])
        history.append(comment)
        del history[:-20]
    if "summary" in result and result["summary"]:
        # Merge the new summary with the existing one instead of
        # replacing it outright.  ``analyze_context`` may return an
        # empty or partial summary, and constructing ``Total`` from an
        # empty dict would reset all fields to zero, effectively erasing
        # previously confirmed meal totals.
        today.summary = today.summary.model_copy(update=result["summary"])

    # Persist updates from context analysis so that subsequent commands such
    # as ``finish_day`` can see the latest meal list and summary.
    storage.save_today(user_id, today)
    logger.info(
        "Analysis updates saved for meal %s | user %s | path=%s | summary=%s",
        meal_id,
        user_id,
        storage.today_path(user_id),
        today.summary.model_dump(),
    )

    if hasattr(context, "user_data"):
        context.user_data.get("meals", {}).pop(meal_id, None)
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
    logger.info(
        "Process: apply_percent | Agent: meal_logging | User: %s | Meal: %s saved to %s",
        user_id,
        meal_id,
        storage.today_path(user_id),
    )
    await update.message.reply_text("Изменено")
    return ConversationHandler.END


async def start_comment_meal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _end_comment_conv(update, context)
    meal_id = query.data.split(":", 1)[1]
    logger.info(
        "Process: start_comment_meal | Agent: meal_logging | User: %s | Meal: %s",
        update.effective_user.id,
        meal_id,
    )
    context.user_data["comment_meal_id"] = meal_id
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
    logger.info(
        "Process: apply_comment | Agent: meal_logging | User: %s | Meal: %s | Comment: %s",
        user_id,
        meal_id,
        comment or "<empty>",
    )
    history = context.user_data.setdefault("history", [])
    if comment:
        history.append(comment)
        del history[:-20]
    today = storage.load_today(user_id)
    meal = next((m for m in today.meals if m.id == meal_id), None)
    if not meal:
        meal = getattr(context, "user_data", {}).get("meals", {}).get(meal_id)
        if meal:
            today.append_meal(meal)
            logger.debug(
                "Process: apply_comment | Agent: meal_logging | User: %s | Appended in-memory meal %s",
                user_id,
                meal_id,
            )
        else:
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
    logger.info(
        "Process: apply_comment | Agent: meal_logging | User: %s | Meal: %s saved to %s",
        user_id,
        meal_id,
        storage.today_path(user_id),
    )
    # Always offer delete and comment actions.  If the meal is still pending,
    # keep the "confirm" button so the user can finalise it after editing.
    buttons = [
        InlineKeyboardButton("✍\ufe0f Комментарии", callback_data=f"comment:{meal.id}"),
        InlineKeyboardButton("🗑 Удалить", callback_data=f"delete:{meal.id}"),
    ]
    if meal.pending:
        buttons.insert(
            0, InlineKeyboardButton("✔ Подтвердить", callback_data=f"confirm:{meal.id}")
        )
    keyboard = InlineKeyboardMarkup([buttons])
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
        logger.warning("Attempted delete of missing meal %s for user %s", meal_id, user_id)
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
    if hasattr(context, "user_data"):
        context.user_data.get("meals", {}).pop(meal_id, None)
    logger.info(
        "Process: delete_meal | Agent: meal_logging | User: %s | Meal: %s removed from %s",
        user_id,
        meal_id,
        storage.today_path(user_id),
    )
    if query.message.photo:
        await query.message.edit_caption("Удалено")
    else:
        await query.message.edit_text("Удалено")

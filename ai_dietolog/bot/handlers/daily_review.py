from __future__ import annotations

import logging
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from ...agents.daily_review import analyze_day as analyze_day_summary
from ...core import storage
from ...core.config import load_config
from ...core.schema import (
    Counters,
    HistoryMeal,
    HistoryMealEntry,
    MealBrief,
    Norms,
    Profile,
    Today,
    Total,
)

logger = logging.getLogger(__name__)


def format_stats(norms: Norms, summary: Total, comment: str | None = None) -> str:
    """Return daily progress report in Markdown with emojis."""

    def line(emoji: str, label: str, value: int, target: int) -> str:
        if target:
            percent = int(round(value / target * 100))
            return f"{emoji} {label}: {value} / {target} ({percent}%)"
        return f"{emoji} {label}: {value}"

    lines = [
        "\U0001f37d *Статистика дня*",
        line("\U0001f525", "Калории", summary.kcal, norms.target_kcal),
        line(
            "\U0001f357", "Белки", summary.protein_g, norms.macros.get("protein_g", 0)
        ),
        line("\U0001f951", "Жиры", summary.fat_g, norms.macros.get("fat_g", 0)),
        line("\U0001f35e", "Углеводы", summary.carbs_g, norms.macros.get("carbs_g", 0)),
    ]
    if comment:
        lines.append("")
        lines.append(comment)
    return "\n".join(lines)


async def finish_day(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Summarise the day and ask to start a new one."""
    user_id = update.effective_user.id
    logger.info(
        "Process: finish_day | Agent: daily_review | Action: summarising day for user %s",
        user_id,
    )
    today = storage.load_today(user_id)
    today_path = storage.today_path(user_id)
    pending = sum(m.pending for m in today.meals)
    logger.info(
        "Loaded Today state for user %s from %s | meals=%d | pending=%d | summary=%s",
        user_id,
        today_path,
        len(today.meals),
        pending,
        today.summary.model_dump(),
    )
    logger.debug(
        "Meal details for user %s: %s",
        user_id,
        [
            {
                "type": m.type,
                "pending": m.pending,
                "total": m.total.model_dump(),
            }
            for m in today.meals
        ],
    )
    confirmed = [m for m in today.meals if not m.pending]
    logger.info("User %s has %d confirmed meals", user_id, len(confirmed))
    if not confirmed:
        has_summary = any(
            getattr(today.summary, field) for field in today.summary.model_fields
        )
        if has_summary:
            logger.warning(
                "Process: finish_day | Agent: daily_review | No confirmed meals for user %s, "
                "but summary totals present; assuming meals confirmed",
                user_id,
            )

            confirmed = today.meals
            for meal in confirmed:
                meal.pending = False
            storage.save_today(user_id, today)
            logger.info(
                "Process: finish_day | Agent: daily_review | All meals auto-confirmed and saved to %s",
                today_path,
            )

        else:
            logger.warning(
                "Process: finish_day | Agent: daily_review | No confirmed meals for user %s",
                user_id,
            )

            await update.message.reply_text("Нет подтверждённых приёмов пищи")
            return
    profile = storage.load_profile(user_id, Profile)
    cfg = load_config()
    meal_lines = []
    briefs = []
    for idx, meal in enumerate(confirmed, 1):
        t = meal.total
        meal_lines.append(
            f"{idx}. *{meal.type}* - {t.kcal} ккал, Б:{t.protein_g} г, "
            f"Ж:{t.fat_g} г, У:{t.carbs_g} г"
        )
        meal_name = (
            ", ".join(it.name for it in meal.items) if meal.items else meal.user_desc
        )
        briefs.append(
            MealBrief(
                type=meal.type,
                name=meal_name,
                **t.model_dump(),
            )
        )
    stats = format_stats(profile.norms, today.summary)
    try:
        comment_text = await analyze_day_summary(
            profile.norms.model_dump(),
            today.summary,
            briefs,
            cfg,
            language=context.user_data.get("language", "ru"),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Day analysis failed: %s", exc)
        comment_text = ""
    text = "\U0001f4c5 *Итоги дня*\n" + "\n".join(meal_lines) + "\n\n" + stats
    if comment_text:
        text += "\n\n" + comment_text
    await update.message.reply_text(text, parse_mode="Markdown")
    logger.info(
        "Process: finish_day | Agent: daily_review | Summary sent to user %s",
        user_id,
    )

    entry = HistoryMealEntry(
        date=datetime.utcnow().date().isoformat(),
        num_meals=len(confirmed),
        meals=briefs,
        comment=comment_text,
    )
    context.user_data["history_entry"] = entry
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Да", callback_data="finish_yes"),
                InlineKeyboardButton("Нет", callback_data="finish_no"),
            ]
        ]
    )
    await update.message.reply_text("Начать новый день?", reply_markup=keyboard)
    logger.info(
        "Process: finish_day | Agent: daily_review | Prompted user %s to start new day",
        user_id,
    )


async def confirm_finish_day(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle confirmation to start a new day."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    logger.info(
        "Process: confirm_finish_day | Agent: daily_review | User: %s | Decision: %s",
        user_id,
        query.data,
    )
    if query.data == "finish_yes":
        logger.info(
            "Process: confirm_finish_day | Agent: daily_review | Action: closing day for user %s",
            user_id,
        )
        entry: HistoryMealEntry | None = context.user_data.get("history_entry")
        if entry:
            history_path = storage.json_path(user_id, "history_meal.json")
            history = storage.read_json(history_path, HistoryMeal)
            history.append_day(entry, max_days=60)
            storage.write_json(history_path, history)
            logger.info(
                "Process: confirm_finish_day | Agent: daily_review | History updated at %s",
                history_path,
            )
        counters_path = storage.json_path(user_id, "counters.json")
        counters = storage.read_json(counters_path, Counters)
        counters.total_days_closed += 1
        storage.write_json(counters_path, counters)
        logger.info(
            "Process: confirm_finish_day | Agent: daily_review | Counters updated at %s",
            counters_path,
        )
        today_path = storage.today_path(user_id)
        storage.save_today(user_id, Today())
        logger.info(
            "Process: confirm_finish_day | Agent: daily_review | Cleared today's data at %s",
            today_path,
        )
        await query.message.edit_text("День завершён. Начинаем новый!")
    else:
        logger.info(
            "Process: confirm_finish_day | Agent: daily_review | Action: cancelled for user %s",
            user_id,
        )
        await query.message.edit_text("Отменено")
    context.user_data.pop("history_entry", None)

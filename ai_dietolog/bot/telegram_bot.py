"""Entry point for the AI Dietolog Telegram bot.

This module initialises the Telegram application, registers basic
commands and starts polling.  Specialized logic for profile setup,
meal logging and daily review lives in ``ai_dietolog.bot.handlers``.

To use this bot, set the environment variables ``TELEGRAM_BOT_TOKEN`` and
``OPENAI_API_KEY`` or populate ``config.json`` accordingly.  The
application will not perform any network requests until a valid token is
provided.
"""

from __future__ import annotations

import logging
import os
import warnings

from colorama import Fore, Style
from colorama import init as colorama_init
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

from telegram.warnings import PTBUserWarning

from .handlers import daily_review, meal_logging, profile_setup
from ..core.config import load_config
from ..core.llm import check_llm_connectivity

logger = logging.getLogger(__name__)

warnings.filterwarnings("ignore", category=PTBUserWarning)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Respond to /start with a welcome message and inline buttons."""
    context.user_data["language"] = update.effective_user.language_code or "ru"
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Настроить профиль", callback_data="setup_profile")]]
    )
    await update.message.reply_text(
        "Добро пожаловать в AI‑диетолог! Выберите действие:",
        reply_markup=keyboard,
    )


async def handle_button_click(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Handle inline keyboard button clicks."""
    query = update.callback_query
    if query.data == "setup_profile":
        return await profile_setup.setup_profile(update, context)
    if query.data == "edit_profile":
        return await profile_setup.start_edit_profile(update, context)
    await query.answer()
    return ConversationHandler.END


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a short AI-generated explanation of unexpected errors."""
    logger.exception("Unhandled error: %s", context.error)
    cfg = load_config()
    api_key = cfg.get("openai_api_key") or os.getenv("OPENAI_API_KEY")
    if isinstance(update, Update) and update.effective_message and api_key:
        try:
            msg = await profile_setup.ai_explain("Произошла техническая ошибка", api_key)
            await update.effective_message.reply_text(msg)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to send error message: %s", exc)


def main() -> None:
    """Main entry point.  Instantiate the bot and run polling."""
    colorama_init()
    cfg = load_config()

    statuses = check_llm_connectivity(cfg)
    openai_msg = (
        f"{Fore.GREEN}connected{Style.RESET_ALL}"
        if statuses.get("openai")
        else f"{Fore.RED}unavailable{Style.RESET_ALL}"
    )
    gemini_msg = (
        f"{Fore.GREEN}connected{Style.RESET_ALL}"
        if statuses.get("gemini")
        else f"{Fore.RED}unavailable{Style.RESET_ALL}"
    )
    logger.info("OpenAI LLM: %s", openai_msg)
    logger.info("Google LLM: %s", gemini_msg)

    token = cfg.get("telegram_bot_token") or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN is not set; bot will not start.")
        return
    application = Application.builder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("setup_profile", profile_setup.setup_profile),
            CallbackQueryHandler(profile_setup.setup_profile, pattern="^setup_profile$"),
        ],
        states={
            profile_setup.MANDATORY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, profile_setup.collect_basic)
            ],
            profile_setup.OPTIONAL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, profile_setup.collect_optional)
            ],
            profile_setup.CONFIRM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, profile_setup.finish_profile)
            ],
        },
        fallbacks=[CommandHandler("cancel", profile_setup.cancel)],
    )

    edit_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(profile_setup.start_edit_profile, pattern="^edit_profile$")],
        states={
            profile_setup.EDIT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, profile_setup.apply_profile_edit)
            ],
        },
        fallbacks=[CommandHandler("cancel", profile_setup.cancel)],
    )

    meal_conv = ConversationHandler(
        entry_points=[CommandHandler("add_meal", meal_logging.add_meal)],
        states={
            meal_logging.MEAL_TYPE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, meal_logging.receive_meal_type)
            ],
            meal_logging.MEAL_DESC: [
                MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, meal_logging.receive_meal_desc)
            ],
            meal_logging.SET_COMMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, meal_logging.apply_comment)
            ],
        },
        fallbacks=[CommandHandler("cancel", profile_setup.cancel)],
    )

    edit_meal_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(meal_logging.start_edit_meal, pattern="^edit:")],
        states={
            meal_logging.SET_PERCENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, meal_logging.apply_percent)
            ],
        },
        fallbacks=[CommandHandler("cancel", profile_setup.cancel)],
    )

    meal_logging.comment_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(meal_logging.start_comment_meal, pattern="^comment:")],
        states={
            meal_logging.SET_COMMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, meal_logging.apply_comment)
            ],
        },
        fallbacks=[CommandHandler("cancel", profile_setup.cancel)],
        allow_reentry=True,
    )

    application.add_handler(conv_handler)
    application.add_handler(edit_conv)
    application.add_handler(meal_conv)
    application.add_handler(edit_meal_conv)
    application.add_handler(meal_logging.comment_conv)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("profile", profile_setup.show_profile))
    application.add_handler(CommandHandler("finish_day", daily_review.finish_day))
    application.add_handler(CallbackQueryHandler(meal_logging.confirm_meal, pattern="^confirm:"))
    application.add_handler(CallbackQueryHandler(meal_logging.delete_meal, pattern="^delete:"))
    application.add_handler(
        CallbackQueryHandler(daily_review.confirm_finish_day, pattern="^finish_(yes|no)$")
    )
    application.add_handler(CallbackQueryHandler(handle_button_click))
    application.add_error_handler(handle_error)
    application.run_polling()


if __name__ == "__main__":
    main()

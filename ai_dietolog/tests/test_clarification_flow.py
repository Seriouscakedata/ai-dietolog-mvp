import asyncio
from types import SimpleNamespace
from datetime import datetime

import ai_dietolog.bot.handlers.meal_logging as bot
from ai_dietolog.core.schema import Item, Meal, Total, Today
from ai_dietolog.core import storage


def test_receive_meal_asks_for_clarification(monkeypatch):
    meal = Meal(
        id="1",
        type="breakfast",
        items=[Item(name="pie", kcal=100)],
        total=Total(kcal=100),
        timestamp=datetime.utcnow(),
        clarification="Начинка? (опционально)",
    )
    meal.user_desc = "pie"
    meal.image_file_id = None

    async def fake_intake(image, user_text, meal_type, *, language="ru", history=None):
        return meal

    monkeypatch.setattr(bot, "intake", fake_intake)
    monkeypatch.setattr(storage, "append_meal", lambda uid, m: None)

    class DummyMsg:
        def __init__(self):
            self.chat_id = 2
            self.message_id = 3

    class DummyBot:
        async def reply_text(self, text, reply_markup=None):
            return DummyMsg()

        async def reply_photo(self, photo, caption, reply_markup=None):
            return DummyMsg()

    update = SimpleNamespace(
        message=SimpleNamespace(
            caption=None,
            text="text",
            photo=None,
            reply_text=DummyBot().reply_text,
            reply_photo=DummyBot().reply_photo,
        ),
        effective_user=SimpleNamespace(id=1),
    )
    context = SimpleNamespace(user_data={})

    res = asyncio.run(bot.receive_meal_desc(update, context))
    from telegram.ext import ConversationHandler
    assert res == ConversationHandler.END
    assert "comment_meal_id" not in context.user_data
    assert "comment_message" not in context.user_data


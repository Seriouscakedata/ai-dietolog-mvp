import asyncio
from types import SimpleNamespace
from datetime import datetime

import ai_dietolog.bot.telegram_bot as bot
from ai_dietolog.core.schema import Item, Meal, Total, Today
from ai_dietolog.core import storage


def test_apply_comment_without_image(monkeypatch):
    meal = Meal(
        id="1",
        type="breakfast",
        items=[Item(name="apple", kcal=50)],
        total=Total(kcal=50),
        timestamp=datetime.utcnow(),
    )
    meal.user_desc = "apple"
    meal.image_file_id = "file123"
    today = Today(meals=[meal])
    monkeypatch.setattr(storage, "load_today", lambda uid: today)
    monkeypatch.setattr(storage, "save_today", lambda uid, t: None)

    async def fake_intake(image, user_text, meal_type, *, language="ru", history=None):
        assert image is None
        return meal

    monkeypatch.setattr(bot, "intake", fake_intake)

    class DummyBot:
        async def get_file(self, file_id):
            raise AssertionError("get_file should not be called")

        async def edit_message_caption(self, **kwargs):
            pass

        async def edit_message_text(self, **kwargs):
            pass

    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1),
        effective_chat=SimpleNamespace(id=2),
        effective_message=SimpleNamespace(message_id=3),
        message=SimpleNamespace(text="extra", reply_text=lambda *a, **k: None),
    )
    context = SimpleNamespace(
        bot=DummyBot(),
        user_data={"comment_meal_id": "1"},
    )

    res = asyncio.run(bot.apply_comment(update, context))
    assert res == bot.SET_COMMENT

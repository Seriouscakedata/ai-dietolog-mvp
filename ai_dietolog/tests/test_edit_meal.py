import asyncio
from types import SimpleNamespace
from datetime import datetime

import ai_dietolog.bot.telegram_bot as bot
from ai_dietolog.core.schema import Item, Meal, Total, Today
from ai_dietolog.core import storage


def test_apply_comment_preserves_item_count(monkeypatch):
    meal = Meal(
        id="1",
        type="breakfast",
        items=[Item(name="pie", kcal=100)],
        total=Total(kcal=100),
        timestamp=datetime.utcnow(),
    )
    meal.user_desc = "pie"
    today = Today(meals=[meal])
    monkeypatch.setattr(storage, "load_today", lambda uid: today)
    monkeypatch.setattr(storage, "save_today", lambda uid, t: None)

    async def fake_edit(existing_meal, comment, *, language="ru", history=None):
        # Return a meal with an extra item which should be ignored
        new_item = Item(name="coffee", kcal=20)
        updated = existing_meal.copy()
        updated.items = existing_meal.items + [new_item]
        updated.total = Total(kcal=120)
        return updated

    monkeypatch.setattr(bot, "edit_meal", fake_edit)

    class DummyBot:
        async def edit_message_text(self, **kwargs):
            pass

        async def edit_message_caption(self, **kwargs):
            pass

    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1),
        effective_chat=SimpleNamespace(id=2),
        effective_message=SimpleNamespace(message_id=3),
        message=SimpleNamespace(text="with coffee", reply_text=lambda *a, **k: None),
    )
    context = SimpleNamespace(
        bot=DummyBot(),
        user_data={"comment_meal_id": "1"},
    )

    res = asyncio.run(bot.apply_comment(update, context))
    assert res == bot.SET_COMMENT
    assert len(today.meals[0].items) == 1
    assert today.meals[0].total.kcal == 100

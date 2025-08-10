import asyncio
from types import SimpleNamespace
from datetime import datetime

import ai_dietolog.bot.handlers.meal_logging as bot
from ai_dietolog.core.schema import Item, Meal, Total
from ai_dietolog.core import storage


def test_apply_comment_persists_in_memory_meal(tmp_path, monkeypatch):
    meal = Meal(
        id="1",
        type="breakfast",
        items=[Item(name="bread", kcal=80)],
        total=Total(kcal=80),
        timestamp=datetime.utcnow(),
    )
    meal.user_desc = "bread"

    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    storage.DATA_DIR.mkdir(parents=True, exist_ok=True)

    async def fake_edit(existing_meal, comment, *, language="ru", history=None):
        assert comment == "note"
        return existing_meal

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
        message=SimpleNamespace(text="note", reply_text=lambda *a, **k: None),
    )
    context = SimpleNamespace(
        bot=DummyBot(),
        user_data={"comment_meal_id": "1", "meals": {"1": meal}},
    )

    res = asyncio.run(bot.apply_comment(update, context))
    from telegram.ext import ConversationHandler
    assert res == ConversationHandler.END

    loaded = storage.load_today(1)
    assert len(loaded.meals) == 1
    assert loaded.meals[0].comment == "note"

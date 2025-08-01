import asyncio
from types import SimpleNamespace
from datetime import datetime

import ai_dietolog.bot.handlers.meal_logging as bot
from ai_dietolog.core.schema import Item, Meal, Total, Today
from ai_dietolog.core import storage


def test_delete_meal_photo(monkeypatch):
    meal = Meal(
        id="1",
        type="breakfast",
        items=[Item(name="apple", kcal=50)],
        total=Total(kcal=50),
        timestamp=datetime.utcnow(),
        image_file_id="file123",
    )
    today = Today(meals=[meal], summary=Total(kcal=50))
    monkeypatch.setattr(storage, "load_today", lambda uid: today)
    monkeypatch.setattr(storage, "save_today", lambda uid, t: None)

    edits = {}

    class DummyMessage:
        photo = [object()]

        async def edit_caption(self, text):
            edits["caption"] = text

        async def edit_text(self, text):
            edits["text"] = text

        async def reply_text(self, *a, **k):
            pass

    class DummyQuery:
        data = "delete:1"
        message = DummyMessage()

        async def answer(self, *a, **k):
            pass

    update = SimpleNamespace(callback_query=DummyQuery(), effective_user=SimpleNamespace(id=1))
    context = SimpleNamespace()

    asyncio.run(bot.delete_meal(update, context))

    assert edits.get("caption") == "Удалено"
    assert "text" not in edits
    assert len(today.meals) == 0

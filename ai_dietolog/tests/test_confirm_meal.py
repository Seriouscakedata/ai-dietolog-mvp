from types import SimpleNamespace
from datetime import datetime
import asyncio

import ai_dietolog.bot.handlers.meal_logging as bot
from ai_dietolog.core import storage
from ai_dietolog.core.schema import Item, Meal, Total, Today, Profile


def test_confirm_meal_updates_summary(monkeypatch):
    meal = Meal(
        id="1",
        type="breakfast",
        items=[Item(name="apple", kcal=50)],
        total=Total(kcal=50),
        timestamp=datetime.utcnow(),
    )
    today = Today(meals=[meal], summary=Total())

    monkeypatch.setattr(storage, "load_today", lambda uid: today)
    monkeypatch.setattr(storage, "save_today", lambda uid, t: None)
    monkeypatch.setattr(storage, "load_profile", lambda uid, cls: Profile())
    monkeypatch.setattr(bot, "load_config", lambda: {})

    async def fake_analyze_context(*args, **kwargs):
        return {}

    monkeypatch.setattr(bot, "analyze_context", fake_analyze_context)

    class DummyMsg:
        photo = None
        async def edit_text(self, *a, **k):
            pass
        async def reply_text(self, *a, **k):
            pass
        async def edit_caption(self, *a, **k):
            pass

    class DummyQuery:
        data = "confirm:1"
        message = DummyMsg()
        async def answer(self):
            pass

    update = SimpleNamespace(callback_query=DummyQuery(), effective_user=SimpleNamespace(id=1))
    context = SimpleNamespace(user_data={})

    asyncio.run(bot.confirm_meal(update, context))

    assert today.meals[0].pending is False
    assert today.summary.kcal == 50


def test_confirm_meal_empty_summary_does_not_reset(monkeypatch):
    meal = Meal(
        id="1",
        type="breakfast",
        items=[Item(name="apple", kcal=50)],
        total=Total(kcal=50),
        timestamp=datetime.utcnow(),
    )
    today = Today(meals=[meal], summary=Total())

    monkeypatch.setattr(storage, "load_today", lambda uid: today)
    monkeypatch.setattr(storage, "save_today", lambda uid, t: None)
    monkeypatch.setattr(storage, "load_profile", lambda uid, cls: Profile())
    monkeypatch.setattr(bot, "load_config", lambda: {})

    async def fake_analyze_context(*args, **kwargs):
        return {"summary": {}}

    monkeypatch.setattr(bot, "analyze_context", fake_analyze_context)

    class DummyMsg:
        photo = None

        async def edit_text(self, *a, **k):
            pass

        async def reply_text(self, *a, **k):
            pass

        async def edit_caption(self, *a, **k):
            pass

    class DummyQuery:
        data = "confirm:1"
        message = DummyMsg()

        async def answer(self):
            pass

    update = SimpleNamespace(callback_query=DummyQuery(), effective_user=SimpleNamespace(id=1))
    context = SimpleNamespace(user_data={})

    asyncio.run(bot.confirm_meal(update, context))

    assert today.summary.kcal == 50


def test_confirm_meal_persists_analysis_updates(tmp_path, monkeypatch):
    meal = Meal(
        id="1",
        type="breakfast",
        items=[Item(name="apple", kcal=50)],
        total=Total(kcal=50),
        timestamp=datetime.utcnow(),
    )
    # Save initial pending meal to temporary storage
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    storage.save_today(1, Today(meals=[meal], summary=Total()))

    monkeypatch.setattr(storage, "load_profile", lambda uid, cls: Profile())
    monkeypatch.setattr(bot, "load_config", lambda: {})

    async def fake_analyze_context(*args, **kwargs):
        return {"summary": {"kcal": 200}}

    monkeypatch.setattr(bot, "analyze_context", fake_analyze_context)

    class DummyMsg:
        photo = None

        async def edit_text(self, *a, **k):
            pass

        async def reply_text(self, *a, **k):
            pass

        async def edit_caption(self, *a, **k):
            pass

    class DummyQuery:
        data = "confirm:1"
        message = DummyMsg()

        async def answer(self):
            pass

    update = SimpleNamespace(callback_query=DummyQuery(), effective_user=SimpleNamespace(id=1))
    context = SimpleNamespace(user_data={})

    asyncio.run(bot.confirm_meal(update, context))

    loaded = storage.load_today(1)
    assert loaded.summary.kcal == 200
    assert len(loaded.meals) == 1
    assert loaded.meals[0].pending is False

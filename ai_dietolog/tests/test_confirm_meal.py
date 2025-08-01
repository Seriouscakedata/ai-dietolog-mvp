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


def test_confirm_meal_saves_before_analysis(monkeypatch):
    meal = Meal(
        id="1",
        type="breakfast",
        items=[Item(name="apple", kcal=50)],
        total=Total(kcal=50),
        timestamp=datetime.utcnow(),
    )
    today = Today(meals=[meal], summary=Total())

    monkeypatch.setattr(storage, "load_today", lambda uid: today)

    saved: list[Today] = []

    def fake_save(uid, t):
        # store a deep copy to inspect later
        saved.append(t.model_copy(deep=True))

    monkeypatch.setattr(storage, "save_today", fake_save)
    monkeypatch.setattr(storage, "load_profile", lambda uid, cls: Profile())
    monkeypatch.setattr(bot, "load_config", lambda: {})

    event = asyncio.Event()

    async def slow_analyze_context(*args, **kwargs):
        await event.wait()
        return {}

    monkeypatch.setattr(bot, "analyze_context", slow_analyze_context)

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
            await event.wait()

    update = SimpleNamespace(callback_query=DummyQuery(), effective_user=SimpleNamespace(id=1))
    context = SimpleNamespace(user_data={})

    async def run_and_signal():
        task = asyncio.create_task(bot.confirm_meal(update, context))
        await asyncio.sleep(0.1)
        # The save should have happened even though both query.answer and
        # analyze_context are waiting on the event.
        assert len(saved) == 1
        assert saved[0].meals[0].pending is False
        assert saved[0].summary.kcal == 50
        event.set()
        await task

    asyncio.run(run_and_signal())

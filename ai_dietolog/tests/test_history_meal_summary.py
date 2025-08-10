import asyncio
from types import SimpleNamespace
from datetime import datetime

from ai_dietolog.core import storage
from ai_dietolog.core.schema import Item, Meal, Today, Total, Profile, HistoryMeal
from ai_dietolog.bot.handlers import daily_review


def test_finish_day_writes_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    user_id = 1
    meal = Meal(
        id="1",
        type="Breakfast",
        items=[Item(name="apple", kcal=50)],
        total=Total(kcal=50),
        pending=False,
        timestamp=datetime.utcnow(),
    )
    storage.save_today(user_id, Today(meals=[meal], summary=Total(kcal=50)))

    monkeypatch.setattr(storage, "load_profile", lambda uid, cls: Profile())
    monkeypatch.setattr(daily_review, "load_config", lambda: {})

    async def fake_analyze(*args, **kwargs):
        return ""

    monkeypatch.setattr(daily_review, "analyze_day_summary", fake_analyze)

    class DummyMsg:
        async def reply_text(self, *a, **k):
            pass

        async def edit_text(self, *a, **k):
            pass

    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        message=DummyMsg(),
    )
    context = SimpleNamespace(user_data={})

    asyncio.run(daily_review.finish_day(update, context))

    class DummyQuery:
        data = "finish_yes"
        message = DummyMsg()

        async def answer(self):
            pass

    asyncio.run(
        daily_review.confirm_finish_day(
            SimpleNamespace(callback_query=DummyQuery(), effective_user=SimpleNamespace(id=user_id)),
            context,
        )
    )

    history = storage.read_json(
        storage.json_path(user_id, "history_meal.json"), HistoryMeal
    )
    assert history.days[0].summary.kcal == 50


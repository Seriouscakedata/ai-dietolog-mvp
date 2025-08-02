import asyncio
from types import SimpleNamespace
from datetime import datetime

import pytest

from ai_dietolog.core import storage
from ai_dietolog.core.schema import Item, Meal, Today, Total, Profile
from ai_dietolog.bot.handlers import daily_review


def test_finish_day_reads_confirmed_meals(tmp_path, monkeypatch):
    # Use temporary directory for storage
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    user_id = 1
    meal = Meal(
        id="1",
        type="Завтрак",
        items=[Item(name="egg", kcal=100)],
        total=Total(kcal=100),
        pending=False,
        timestamp=datetime.utcnow(),
    )
    storage.save_today(user_id, Today(meals=[meal], summary=Total(kcal=100)))

    # Stub external dependencies
    monkeypatch.setattr(storage, "load_profile", lambda uid, cls: Profile())
    monkeypatch.setattr(daily_review, "load_config", lambda: {})

    async def fake_analyze_day(*args, **kwargs):
        return ""

    monkeypatch.setattr(daily_review, "analyze_day_summary", fake_analyze_day)

    messages = []

    class DummyMsg:
        async def reply_text(self, text, **kwargs):
            messages.append(text)

    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        message=DummyMsg(),
    )
    context = SimpleNamespace(user_data={})

    asyncio.run(daily_review.finish_day(update, context))

    # The first reply should not indicate absence of confirmed meals
    assert messages
    assert all("Нет подтверждённых" not in m for m in messages)

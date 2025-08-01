import asyncio
from types import SimpleNamespace
from datetime import datetime

import ai_dietolog.bot.handlers.meal_logging as bot
from ai_dietolog.core.schema import Item, Meal, Total, Today
from ai_dietolog.core import storage
from ai_dietolog.agents import meal_editor as editor


def test_apply_comment_updates_items(monkeypatch):
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
    from telegram.ext import ConversationHandler
    assert res == ConversationHandler.END
    assert len(today.meals[0].items) == 2
    assert today.meals[0].total.kcal == 120


def test_apply_comment_updates_summary(monkeypatch):
    meal = Meal(
        id="1",
        type="breakfast",
        items=[Item(name="pie", kcal=100, protein_g=10)],
        total=Total(kcal=100, protein_g=10),
        timestamp=datetime.utcnow(),
        pending=False,
    )
    today = Today(meals=[meal], summary=Total(kcal=100, protein_g=10))
    monkeypatch.setattr(storage, "load_today", lambda uid: today)
    monkeypatch.setattr(storage, "save_today", lambda uid, t: None)

    async def fake_edit(existing_meal, comment, *, language="ru", history=None):
        updated = existing_meal.model_copy()
        updated.items = [Item(name="pie+cream", kcal=150, protein_g=12)]
        updated.total = Total(kcal=150, protein_g=12)
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
        message=SimpleNamespace(text="cream", reply_text=lambda *a, **k: None),
    )
    context = SimpleNamespace(
        bot=DummyBot(),
        user_data={"comment_meal_id": "1"},
    )

    res = asyncio.run(bot.apply_comment(update, context))
    from telegram.ext import ConversationHandler
    assert res == ConversationHandler.END
    assert today.summary.kcal == 150
    assert today.summary.protein_g == 12


def _fake_client(response_text: str):
    async def fake_create(*args, **kwargs):
        class Message:
            def __init__(self, content):
                self.content = response_text

        class Choice:
            def __init__(self):
                self.message = Message(response_text)

        class Resp:
            def __init__(self):
                self.choices = [Choice()]

        return Resp()

    class FakeClient:
        def __init__(self):
            self.chat = type(
                "Chat", (), {"completions": type("Comp", (), {"create": fake_create})()}
            )()

    return FakeClient()


def test_edit_meal_extracts_json(monkeypatch):
    existing = Meal(
        id="1",
        type="snack",
        items=[Item(name="cake", kcal=100)],
        total=Total(kcal=100),
        timestamp=datetime.utcnow(),
    )
    resp_text = "Here is the update:\n{\"items\": [{\"name\": \"cake\", \"kcal\": 110}], \"total\": {\"kcal\": 110}}"
    monkeypatch.setattr(editor, "AsyncOpenAI", lambda *a, **k: _fake_client(resp_text))
    updated = asyncio.run(editor.edit_meal(existing, "extra"))
    assert updated.total.kcal == 110

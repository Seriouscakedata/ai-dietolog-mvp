import asyncio
from types import SimpleNamespace
from datetime import datetime

import ai_dietolog.bot.handlers.meal_logging as bot
from ai_dietolog.core.schema import Item, Meal, Total, Today
from ai_dietolog.core import storage


def test_apply_comment_keeps_confirm_button(tmp_path, monkeypatch):
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
    storage.save_today(1, Today(meals=[meal], summary=Total()))

    async def fake_edit(existing_meal, comment, *, language="ru", history=None):
        return existing_meal

    monkeypatch.setattr(bot, "edit_meal", fake_edit)

    captured = {}

    class DummyBot:
        async def edit_message_text(self, **kwargs):
            captured["markup"] = kwargs.get("reply_markup")

        async def edit_message_caption(self, **kwargs):
            captured["markup"] = kwargs.get("reply_markup")

    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1),
        effective_chat=SimpleNamespace(id=2),
        effective_message=SimpleNamespace(message_id=3),
        message=SimpleNamespace(text="note", reply_text=lambda *a, **k: None),
    )
    context = SimpleNamespace(
        bot=DummyBot(),
        user_data={"comment_meal_id": "1"},
    )

    res = asyncio.run(bot.apply_comment(update, context))
    from telegram.ext import ConversationHandler

    assert res == ConversationHandler.END
    buttons = captured["markup"].inline_keyboard[0]
    assert any(b.callback_data == "confirm:1" for b in buttons)


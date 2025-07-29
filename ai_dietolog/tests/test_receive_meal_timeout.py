import asyncio
from types import SimpleNamespace

import ai_dietolog.bot.telegram_bot as bot


def test_receive_meal_timeout(monkeypatch):
    class DummyPhoto:
        async def get_file(self):
            from telegram.error import TimedOut
            raise TimedOut("timeout")

    class DummyBot:
        def __init__(self):
            self.messages = []

        async def reply_text(self, text, reply_markup=None):
            self.messages.append(text)
            return SimpleNamespace()

        async def reply_photo(self, photo, caption, reply_markup=None):
            return SimpleNamespace()

    dummy = DummyBot()
    update = SimpleNamespace(
        message=SimpleNamespace(
            caption=None,
            text="desc",
            photo=[DummyPhoto()],
            reply_text=dummy.reply_text,
            reply_photo=dummy.reply_photo,
        ),
        effective_user=SimpleNamespace(id=1),
    )
    context = SimpleNamespace(user_data={})

    res = asyncio.run(bot.receive_meal_desc(update, context))
    assert res == bot.MEAL_DESC
    assert dummy.messages

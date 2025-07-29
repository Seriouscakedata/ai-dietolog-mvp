import asyncio
import json

from ai_dietolog.agents import intake as intake_module


def test_optional_clarification(monkeypatch):
    resp = {
        "items": [{"name": "pie", "kcal": 100}],
        "total": {"kcal": 100},
        "clarification": "Что за начинка у пирожка? (опционально)",
    }
    meal_json = json.dumps(resp)

    async def fake_create(*args, **kwargs):
        class Message:
            def __init__(self, content):
                self.content = meal_json

        class Choice:
            def __init__(self):
                self.message = Message(meal_json)

        class Resp:
            def __init__(self):
                self.choices = [Choice()]

        return Resp()

    class FakeClient:
        def __init__(self):
            self.chat = type(
                "Chat", (), {"completions": type("Comp", (), {"create": fake_create})()}
            )()

    monkeypatch.setattr(intake_module, "AsyncOpenAI", lambda *a, **k: FakeClient())

    meal = asyncio.run(
        intake_module.intake(image=None, user_text="pie", meal_type="breakfast")
    )

    assert meal.clarification == "Что за начинка у пирожка? (опционально)"
    assert meal.items[0].name == "pie"

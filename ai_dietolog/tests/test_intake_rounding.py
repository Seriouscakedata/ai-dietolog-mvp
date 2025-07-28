import asyncio
import json

from ai_dietolog.agents import intake as intake_module


def test_fractional_macros_rounding(monkeypatch):
    meal_resp = {
        "items": [
            {"name": "apple", "kcal": 50.5, "protein_g": 0.4, "fat_g": 0.5},
        ],
        "total": {"kcal": 50.5, "protein_g": 0.4, "fat_g": 0.5},
    }
    meal_json = json.dumps(meal_resp)

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
            self.chat = type("Chat", (), {"completions": type("Comp", (), {"create": fake_create})()})()

    monkeypatch.setattr(intake_module, "AsyncOpenAI", lambda: FakeClient())

    meal = asyncio.run(intake_module.intake(image=None, user_text="apple", meal_type="breakfast"))

    assert meal.items[0].kcal == int(round(50.5))
    assert meal.items[0].protein_g == int(round(0.4))
    assert meal.items[0].fat_g == int(round(0.5))
    assert meal.total.kcal == int(round(50.5))
    assert meal.total.protein_g == int(round(0.4))
    assert meal.total.fat_g == int(round(0.5))

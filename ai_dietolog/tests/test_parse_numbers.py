import asyncio
import json

from ai_dietolog.agents import intake as intake_module
from ai_dietolog.agents import meal_editor as editor_module
from ai_dietolog.core.schema import Item, Meal, Total


def _fake_client(response_json: str):
    async def fake_create(*args, **kwargs):
        class Message:
            def __init__(self, content):
                self.content = response_json

        class Choice:
            def __init__(self):
                self.message = Message(response_json)

        class Resp:
            def __init__(self):
                self.choices = [Choice()]

        return Resp()

    class FakeClient:
        def __init__(self):
            self.chat = type(
                "Chat",
                (),
                {"completions": type("Comp", (), {"create": fake_create})()},
            )()

    return FakeClient()


def test_intake_units(monkeypatch):
    resp = {
        "items": [{"name": "cake", "kcal": "150 ккал", "protein_g": "5 г"}],
        "total": {"kcal": "150 ккал", "protein_g": "5 г"},
    }
    meal_json = json.dumps(resp, ensure_ascii=False)
    monkeypatch.setattr(intake_module, "AsyncOpenAI", lambda *a, **k: _fake_client(meal_json))

    meal = asyncio.run(
        intake_module.intake(image=None, user_text="cake", meal_type="snack")
    )

    assert meal.total.kcal == 150
    assert meal.total.protein_g == 5


def test_edit_meal_units(monkeypatch):
    existing = Meal(
        id="1",
        type="snack",
        items=[Item(name="cake", kcal=100)],
        total=Total(kcal=100),
        timestamp=__import__("datetime").datetime.utcnow(),
    )
    resp = {
        "items": [{"name": "cake", "kcal": "120 ккал"}],
        "total": {"kcal": "120 ккал"},
    }
    meal_json = json.dumps(resp, ensure_ascii=False)
    monkeypatch.setattr(editor_module, "AsyncOpenAI", lambda *a, **k: _fake_client(meal_json))

    updated = asyncio.run(editor_module.edit_meal(existing, "more"))

    assert updated.total.kcal == 120


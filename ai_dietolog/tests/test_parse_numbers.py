import asyncio
import asyncio
import json

from ai_dietolog.agents import intake as intake_module
from ai_dietolog.agents import meal_editor as editor_module
from ai_dietolog.core.schema import Item, Meal, Total


def test_intake_units(monkeypatch):
    resp = {
        "items": [{"name": "cake", "kcal": "150 ккал", "protein_g": "5 г"}],
        "total": {"kcal": "150 ккал", "protein_g": "5 г"},
    }
    meal_json = json.dumps(resp, ensure_ascii=False)

    async def fake_ask_llm(*args, **kwargs):
        return meal_json

    monkeypatch.setattr(intake_module, "ask_llm", fake_ask_llm)

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

    async def fake_ask_llm(*args, **kwargs):
        return meal_json

    monkeypatch.setattr(editor_module, "ask_llm", fake_ask_llm)

    updated = asyncio.run(editor_module.edit_meal(existing, "more"))

    assert updated.total.kcal == 120


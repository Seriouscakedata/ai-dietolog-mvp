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

    async def fake_ask_llm(*args, **kwargs):
        return meal_json

    monkeypatch.setattr(intake_module, "ask_llm", fake_ask_llm)

    meal = asyncio.run(
        intake_module.intake(image=None, user_text="apple", meal_type="breakfast")
    )
    assert meal.clarification is None

    assert meal.items[0].kcal == int(round(50.5))
    assert meal.items[0].protein_g == int(round(0.4))
    assert meal.items[0].fat_g == int(round(0.5))
    assert meal.total.kcal == int(round(50.5))
    assert meal.total.protein_g == int(round(0.4))
    assert meal.total.fat_g == int(round(0.5))

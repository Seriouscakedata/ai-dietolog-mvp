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

    async def fake_ask_llm(*args, **kwargs):
        return meal_json

    monkeypatch.setattr(intake_module, "ask_llm", fake_ask_llm)

    meal = asyncio.run(
        intake_module.intake(image=None, user_text="pie", meal_type="breakfast")
    )

    assert meal.clarification == "Что за начинка у пирожка? (опционально)"
    assert meal.items[0].name == "pie"

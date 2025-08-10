import asyncio
from ai_dietolog.agents import daily_review
from ai_dietolog.core.schema import Total, MealBrief


def test_daily_review_format(monkeypatch):
    resp_text = "- comment1\n- comment2\n- comment3\n- comment4\n- comment5"

    async def fake_ask_llm(*args, **kwargs):
        return resp_text

    monkeypatch.setattr(daily_review, "ask_llm", fake_ask_llm)

    norms = {"target_kcal": 2000}
    summary = Total(kcal=2100)
    meals = [MealBrief(type="breakfast", name="egg", kcal=300)]
    result = asyncio.run(daily_review.analyze_day(norms, summary, meals, cfg={}))
    assert result.startswith("-")

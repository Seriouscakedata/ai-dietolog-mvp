import asyncio
from ai_dietolog.agents import daily_review
from ai_dietolog.core.schema import Total, MealBrief


def test_daily_review_format(monkeypatch):
    resp_text = "- comment1\n- comment2\n- comment3\n- comment4\n- comment5"

    async def fake_create(*args, **kwargs):
        class Message:
            def __init__(self, content):
                self.content = resp_text

        class Choice:
            def __init__(self):
                self.message = Message(resp_text)

        class Resp:
            def __init__(self):
                self.choices = [Choice()]

        return Resp()

    class FakeClient:
        def __init__(self):
            self.chat = type("Chat", (), {"completions": type("Comp", (), {"create": fake_create})()})()

    monkeypatch.setattr(daily_review, "AsyncOpenAI", lambda api_key=None: FakeClient())

    norms = {"target_kcal": 2000}
    summary = Total(kcal=2100)
    meals = [MealBrief(type="breakfast", name="egg", kcal=300)]
    result = asyncio.run(daily_review.analyze_day(norms, summary, meals, cfg={}))
    assert result.startswith("-")

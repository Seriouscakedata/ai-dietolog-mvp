from __future__ import annotations

"""Context analysis agent."""

import json
from openai import AsyncOpenAI

from ..core.prompts import CONTEXT_ANALYSIS
from ..core.schema import Total


async def analyze_context(
    profile_norms: dict,
    day_summary: Total,
    new_meal_total: Total,
    cfg: dict,
    *,
    language: str = "ru",
) -> dict:
    """Return updated summary and comment for the new meal."""
    client = AsyncOpenAI(api_key=cfg.get("openai_api_key"))
    system = CONTEXT_ANALYSIS.render(
        norms=json.dumps(profile_norms, ensure_ascii=False),
        day_summary=json.dumps(day_summary.model_dump(), ensure_ascii=False),
        new_meal=json.dumps(new_meal_total.model_dump(), ensure_ascii=False),
        language=language,
    )
    resp = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": system}],
        temperature=0.3,
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)

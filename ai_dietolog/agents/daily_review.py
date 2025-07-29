from __future__ import annotations

"""Agent for analysing the entire day's intake."""

import json
from typing import Optional, Sequence

from openai import AsyncOpenAI

from ..core.config import openai_api_key

from ..core.prompts import DAY_ANALYSIS
from ..core.schema import MealBrief, Total


async def analyze_day(
    profile_norms: dict,
    summary: Total,
    meals: Sequence[MealBrief],
    cfg: dict,
    *,
    language: str = "ru",
    history: Optional[list[str]] = None,
) -> str:
    """Return bullet point comments about the day."""

    client = AsyncOpenAI(api_key=cfg.get("openai_api_key") or openai_api_key())
    system = DAY_ANALYSIS.render(
        norms=json.dumps(profile_norms, ensure_ascii=False),
        summary=json.dumps(summary.model_dump(), ensure_ascii=False),
        meals=json.dumps([m.model_dump() for m in meals], ensure_ascii=False),
        language=language,
    )
    messages = []
    if history:
        hist_text = "\n".join(history[-20:])
        messages.append(
            {
                "role": "system",
                "content": (
                    "Previous conversation with the user (for context only, do not answer these):\n"
                    f"{hist_text}\n--- End of previous messages ---"
                ),
            }
        )
    messages.append({"role": "system", "content": system})
    resp = await client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.3,
    )
    return resp.choices[0].message.content.strip()

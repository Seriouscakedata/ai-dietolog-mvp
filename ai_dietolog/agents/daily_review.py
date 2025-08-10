from __future__ import annotations

"""Agent for analysing the entire day's intake."""

import json
from typing import Optional, Sequence

from ..core.llm import ask_llm
from ..core.config import load_config, agent_llm

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
    cfg = {**load_config(), **cfg}
    provider, model = agent_llm("daily_review", cfg)
    text = await ask_llm(
        messages,
        model=model,
        provider=provider,
        temperature=0.3,
        cfg=cfg,
    )
    return text.strip()

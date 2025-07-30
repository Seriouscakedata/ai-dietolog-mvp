from __future__ import annotations

"""Context analysis agent."""

import json
from typing import Optional
from ..core.llm import ask_llm
from openai import AsyncOpenAI  # noqa: F401
from ..core.config import openai_api_key, load_config, agent_llm

from ..core.prompts import CONTEXT_ANALYSIS
from ..core.schema import Total


async def analyze_context(
    profile_norms: dict,
    day_summary: Total,
    new_meal_total: Total,
    cfg: dict,
    *,
    language: str = "ru",
    history: Optional[list[str]] = None,
) -> dict:
    """Return updated summary and comment for the new meal."""
    system = CONTEXT_ANALYSIS.render(
        norms=json.dumps(profile_norms, ensure_ascii=False),
        day_summary=json.dumps(day_summary.model_dump(), ensure_ascii=False),
        new_meal=json.dumps(new_meal_total.model_dump(), ensure_ascii=False),
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
    provider, model = agent_llm("contextual", cfg)
    if provider == "openai":
        client = AsyncOpenAI(api_key=cfg.get("openai_api_key") or openai_api_key())
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content
    else:
        content = await ask_llm(
            messages,
            model=model,
            provider=provider,
            temperature=0.3,
            response_format={"type": "json_object"},
            cfg=cfg,
        )
    return json.loads(content)

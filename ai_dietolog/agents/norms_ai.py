from __future__ import annotations

"""Helper for computing nutrition norms via OpenAI."""

import json
from typing import Optional

from openai import AsyncOpenAI

from ..core.prompts import AI_NORMS
from ..core.schema import Norms


async def compute_norms_llm(profile_data: dict, cfg: dict, *, language: str = "ru") -> Norms:
    """Return ``Norms`` calculated by a language model."""
    client = AsyncOpenAI(api_key=cfg.get("openai_api_key"))
    system = AI_NORMS.render(
        profile=json.dumps(profile_data, ensure_ascii=False),
        language=language,
    )
    resp = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": system}],
        temperature=0,
    )
    content = resp.choices[0].message.content.strip()
    data = json.loads(content)
    return Norms(**data)

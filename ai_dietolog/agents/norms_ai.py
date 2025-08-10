from __future__ import annotations

"""Helper for computing nutrition norms via OpenAI."""

import json
from typing import Optional

from ..core.llm import ask_llm
from ..core.config import load_config, agent_llm

from ..core.prompts import AI_NORMS
from ..core.schema import Norms


async def compute_norms_llm(
    profile_data: dict,
    cfg: dict,
    *,
    language: str = "ru",
) -> Norms:
    """Return ``Norms`` calculated by a language model."""
    cfg = {**load_config(), **cfg}
    provider, model = agent_llm("norms_ai", cfg)
    system = AI_NORMS.render(
        profile=json.dumps(profile_data, ensure_ascii=False),
        language=language,
    )
    messages = [{"role": "system", "content": system}]
    text = await ask_llm(
        messages,
        model=model,
        provider=provider,
        temperature=0,
        cfg=cfg,
    )
    data = json.loads(text)
    return Norms(**data)

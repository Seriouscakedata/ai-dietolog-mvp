from __future__ import annotations

"""Agent for updating an existing profile via OpenAI."""

import json
import logging

from ..core.llm import ask_llm
from ..core.config import load_config, agent_llm
from ..core.prompts import PROFILE_TO_JSON

logger = logging.getLogger(__name__)


async def update_profile(
    existing_profile: dict,
    user_request: str,
    api_key: str,
    *,
    language: str = "ru",
) -> dict:
    """Merge ``user_request`` into ``existing_profile`` using GPT-4o.

    The language model receives the current profile JSON and should return
    only an updated JSON object. The returned value is parsed and returned
    as a Python ``dict``.
    """
    system = PROFILE_TO_JSON.render(
        profile=json.dumps(existing_profile, ensure_ascii=False),
        language=language,
    )
    cfg = {**load_config(), "openai_api_key": api_key}
    provider, model = agent_llm("profile_editor", cfg)
    content = await ask_llm(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user_request},
        ],
        model=model,
        provider=provider,
        temperature=0,
        cfg=cfg,
    )
    content = content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:  # noqa: BLE001
        logger.error("Failed to parse profile JSON: %s", content)
        raise ValueError("invalid JSON") from exc


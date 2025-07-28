from __future__ import annotations

"""Agent for updating an existing profile via OpenAI."""

import json
import logging

from openai import AsyncOpenAI

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
    client = AsyncOpenAI(api_key=api_key)
    resp = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user_request}],
        temperature=0,
    )
    content = resp.choices[0].message.content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:  # noqa: BLE001
        logger.error("Failed to parse profile JSON: %s", content)
        raise ValueError("invalid JSON") from exc


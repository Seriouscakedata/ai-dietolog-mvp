from __future__ import annotations

"""Agent for refining an existing meal based on a user comment."""

import json
import logging
from typing import Optional

from ..core.llm import ask_llm
from openai import AsyncOpenAI  # noqa: F401
from ..core.config import openai_api_key, load_config, agent_llm
from pydantic import ValidationError

from ..core.prompts import UPDATE_MEAL_JSON
from ..core.schema import Item, Meal, Total
from ..core.utils import parse_int, parse_json_block

logger = logging.getLogger(__name__)


async def edit_meal(
    existing_meal: Meal,
    comment: str,
    *,
    language: str = "ru",
    history: Optional[list[str]] = None,
) -> Meal:
    """Return an updated ``Meal`` incorporating ``comment``.

    The language model receives the current meal JSON and the user comment.
    It should return JSON with the same number of items, adjusting names or
    nutrition if needed. If parsing fails or the number of items differs from
    the original, the original meal object is returned.
    """
    system = UPDATE_MEAL_JSON.render(
        meal=json.dumps(existing_meal.model_dump(mode="json"), ensure_ascii=False),
        user_desc=existing_meal.user_desc,
        comment=comment,
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
    messages.append({"role": "user", "content": comment})
    cfg = load_config()
    provider, model = agent_llm("meal_editor", cfg)
    if provider == "openai":
        client = AsyncOpenAI(api_key=cfg.get("openai_api_key") or openai_api_key())
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content
    else:
        content = await ask_llm(
            messages,
            model=model,
            provider=provider,
            temperature=0,
            response_format={"type": "json_object"},
            cfg=cfg,
        )
    try:
        data = parse_json_block(content)
    except json.JSONDecodeError as exc:  # noqa: BLE001
        logger.exception("Failed to parse meal update: %s; content=%r", exc, content)
        return existing_meal

    items_raw = data.get("items", [])
    total_raw = data.get("total", {})

    for it in items_raw:
        if "calories" in it and "kcal" not in it:
            it["kcal"] = it.pop("calories")
    if "calories" in total_raw and "kcal" not in total_raw:
        total_raw["kcal"] = total_raw.pop("calories")

    for item in items_raw:
        for key in [
            "kcal",
            "protein_g",
            "fat_g",
            "carbs_g",
            "sugar_g",
            "fiber_g",
        ]:
            val = parse_int(item.get(key))
            if val is not None:
                item[key] = val
    for key in [
        "kcal",
        "protein_g",
        "fat_g",
        "carbs_g",
        "sugar_g",
        "fiber_g",
    ]:
        val = parse_int(total_raw.get(key))
        if val is not None:
            total_raw[key] = val

    try:
        items = [Item(**it) for it in items_raw]
        total = Total(**total_raw)
    except ValidationError as exc:  # noqa: BLE001
        logger.exception("Invalid meal update structure: %s", exc)
        return existing_meal

    if len(items) != len(existing_meal.items):
        logger.info(
            "Meal item count changed from %d to %d",
            len(existing_meal.items),
            len(items),
        )

    return existing_meal.copy(update={
        "items": items,
        "total": total,
        "clarification": data.get("clarification"),
    })

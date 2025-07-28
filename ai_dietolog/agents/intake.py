from __future__ import annotations

"""Meal intake agent."""

import json
import logging
import base64
from datetime import datetime
from uuid import uuid4
from typing import Optional

from openai import AsyncOpenAI
from pydantic import ValidationError

from ..core.prompts import MEAL_JSON
from ..core.schema import Item, Meal, Total


async def intake(
    image: Optional[bytes],
    user_text: str,
    meal_type: str,
    *,
    language: str = "ru",
    history: Optional[list[str]] = None,
) -> Meal:
    """Analyse ``user_text`` describing a meal and return a ``Meal`` object."""
    client = AsyncOpenAI()
    system = MEAL_JSON.render(
        meal_type=meal_type,
        user_desc=user_text,
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
    if image is not None:
        b64 = base64.b64encode(image).decode()
        image_url = f"data:image/jpeg;base64,{b64}"
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text or ""},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }
        )
    else:
        messages.append({"role": "user", "content": user_text})

    resp = await client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0,
        response_format={"type": "json_object"},
    )
    data = json.loads(resp.choices[0].message.content)

    items_raw = data.get("items", [])
    norm_items = []
    for it in items_raw:
        if "calories" in it and "kcal" not in it:
            it["kcal"] = it.pop("calories")
        norm_items.append(it)

    total_raw = data.get("total", {})
    if "calories" in total_raw and "kcal" not in total_raw:
        total_raw["kcal"] = total_raw.pop("calories")

    for item in norm_items:
        for key in [
            "kcal",
            "protein_g",
            "fat_g",
            "carbs_g",
            "sugar_g",
            "fiber_g",
        ]:
            val = item.get(key)
            if isinstance(val, float):
                item[key] = int(round(val))
    for key in [
        "kcal",
        "protein_g",
        "fat_g",
        "carbs_g",
        "sugar_g",
        "fiber_g",
    ]:
        val = total_raw.get(key)
        if isinstance(val, float):
            total_raw[key] = int(round(val))

    try:
        items = [Item(**item) for item in norm_items]
        total = Total(**total_raw)
    except ValidationError as exc:
        logging.exception("Invalid meal data: %s", exc)
        raise ValueError("Не удалось распознать блюдо, попробуйте ещё") from exc
    meal = Meal(
        id=str(uuid4()),
        type=meal_type,
        items=items,
        total=total,
        pending=True,
        timestamp=datetime.utcnow(),
        percent_eaten=100,
    )
    return meal

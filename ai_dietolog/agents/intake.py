from __future__ import annotations

"""Meal intake agent."""

import json
import logging
from datetime import datetime
from uuid import uuid4
from typing import Optional

from openai import AsyncOpenAI
from pydantic import ValidationError

from ..core.prompts import MEAL_JSON
from ..core.schema import Item, Meal, Total


async def intake(image: Optional[bytes], user_text: str, meal_type: str) -> Meal:
    """Analyse ``user_text`` describing a meal and return a ``Meal`` object."""
    client = AsyncOpenAI()
    system = MEAL_JSON.render(meal_type=meal_type, user_desc=user_text)
    resp = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": system}],
        temperature=0,
        response_format={"type": "json_object"},
    )
    data = json.loads(resp.choices[0].message.content)

    items_raw = data.get("items", [])
    norm_items = []
    for it in items_raw:
        if "calories" in it and "kcal" not in it:
            it["kcal"] = it.pop("calories")
        it.setdefault("protein_g", 0)
        it.setdefault("fat_g", 0)
        it.setdefault("carbs_g", 0)
        it.setdefault("sugar_g", 0)
        it.setdefault("fiber_g", 0)
        norm_items.append(it)

    total_raw = data.get("total", {})
    if "calories" in total_raw and "kcal" not in total_raw:
        total_raw["kcal"] = total_raw.pop("calories")
    for key in ("protein_g", "fat_g", "carbs_g", "sugar_g", "fiber_g"):
        total_raw.setdefault(key, 0)

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

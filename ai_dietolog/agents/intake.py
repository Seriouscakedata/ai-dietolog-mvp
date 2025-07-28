from __future__ import annotations

"""Meal intake agent."""

import json
from datetime import datetime
from uuid import uuid4
from typing import Optional

from openai import AsyncOpenAI

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
    items = [Item(**item) for item in data.get("items", [])]
    total = Total(**data.get("total", {}))
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

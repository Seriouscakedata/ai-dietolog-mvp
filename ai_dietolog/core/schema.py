"""Pydantic models for persistent data structures.

These models define the schema of the JSON files stored in ``data/<user_id>``.
They also provide helper methods for scaling meals and updating totals.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, validator


class Item(BaseModel):
    name: str
    weight_g: Optional[int] = None
    kcal: int
    protein_g: Optional[int] = None
    fat_g: Optional[int] = None
    carbs_g: Optional[int] = None
    sugar_g: Optional[int] = None
    fiber_g: Optional[int] = None

    def scale(self, factor: float) -> "Item":
        """Return a new ``Item`` scaled by the given factor.

        Only numeric nutritional fields are scaled; the name remains the
        same.  We ensure all numeric values stay integers.
        """
        data = self.model_dump()
        scaled: Dict[str, Any] = {}
        for key, value in data.items():
            if key == "name":
                scaled[key] = value
                continue
            if value is None:
                scaled[key] = None
            else:
                scaled[key] = int(round(value * factor))
        return Item(**scaled)


class Total(BaseModel):
    kcal: int = 0
    protein_g: int = 0
    fat_g: int = 0
    carbs_g: int = 0
    sugar_g: int = 0
    fiber_g: int = 0

    def __iadd__(self, other: "Total") -> "Total":
        """In-place addition of totals.

        Adds each numeric attribute from ``other`` to ``self`` and
        returns ``self``.
        """
        for field in self.model_fields:
            setattr(self, field, getattr(self, field) + getattr(other, field))
        return self


class Meal(BaseModel):
    id: str
    type: str
    items: List[Item]
    total: Total
    pending: bool = True
    timestamp: datetime
    percent_eaten: int = 100
    user_desc: str = ""
    image_file_id: Optional[str] = None
    comment: Optional[str] = None
    clarification: Optional[str] = None

    @validator("percent_eaten")
    def check_percent(cls, v: int) -> int:
        if not 0 < v <= 100:
            raise ValueError("percent_eaten must be between 1 and 100")
        return v


class Today(BaseModel):
    meals: List[Meal] = Field(default_factory=list)
    summary: Total = Field(default_factory=Total)
    day_closed: bool = False
    last_updated: Optional[datetime] = None

    def append_meal(self, meal: Meal) -> None:
        """Add a meal to today's meals and update the last_updated timestamp.

        The meal is appended regardless of the ``pending`` status; summary
        should be updated separately only for confirmed meals.
        """
        self.meals.append(meal)
        self.last_updated = meal.timestamp

    def confirm_meal(self, meal_id: str) -> None:
        """Mark a meal as confirmed and update the summary totals.

        If the meal is already confirmed or does not exist, this method
        silently does nothing.
        """
        for meal in self.meals:
            if meal.id == meal_id and meal.pending:
                meal.pending = False
                self.summary += meal.total
                self.last_updated = meal.timestamp
                break


class ClosedDay(BaseModel):
    date: str
    summary: Total
    meals: List[Meal]


class History(BaseModel):
    days: List[ClosedDay] = Field(default_factory=list)

    def append_day(self, day: ClosedDay, max_days: int = 30) -> None:
        """Append a closed day and enforce history length.

        If the number of days exceeds ``max_days``, the oldest day is
        discarded.
        """
        self.days.append(day)
        if len(self.days) > max_days:
            del self.days[0]


class MealBrief(BaseModel):
    """Simplified information about one meal for history."""

    type: str = ""
    name: str = ""
    kcal: int = 0
    protein_g: int = 0
    fat_g: int = 0
    carbs_g: int = 0
    sugar_g: int = 0
    fiber_g: int = 0


class HistoryMealEntry(BaseModel):
    """Concise record of a closed day."""

    date: str
    num_meals: int
    meals: List[MealBrief]
    comment: str = ""


class HistoryMeal(BaseModel):
    days: List[HistoryMealEntry] = Field(default_factory=list)

    def append_day(self, day: HistoryMealEntry, max_days: int = 30) -> None:
        """Append an entry and truncate to ``max_days`` elements."""
        self.days.append(day)
        if len(self.days) > max_days:
            del self.days[0]


class Counters(BaseModel):
    total_days_closed: int = 0
    metrics: Dict[str, Any] = Field(
        default_factory=lambda: {
            "last_metrics_day_index": 0,
            "metrics_interval_days": 30,
        }
    )


class Norms(BaseModel):
    BMR_kcal: int
    TDEE_kcal: int
    target_kcal: int
    macros: Dict[str, int]
    fiber_min_g: int
    water_min_ml: int


class MetricsCfg(BaseModel):
    last_metrics_day_index: int = 0
    metrics_interval_days: int = 30


class Profile(BaseModel):
    personal: Dict[str, Any] = Field(default_factory=dict)
    goals: Dict[str, Any] = Field(default_factory=dict)
    restrictions: List[str] = Field(default_factory=list)
    preferences: List[str] = Field(default_factory=list)
    medical: List[str] = Field(default_factory=list)
    norms: Norms = Field(default_factory=Norms)
    metrics: MetricsCfg = Field(default_factory=MetricsCfg)

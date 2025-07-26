"""Core nutritional calculations.

This module contains formulas for estimating basal metabolic rate (BMR), total
daily energy expenditure (TDEE) and macronutrient targets based on a
user's personal characteristics and goals.  Values returned from these
functions are purely indicative and should not replace professional advice.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict


class NormsDict(TypedDict):
    BMR_kcal: int
    TDEE_kcal: int
    target_kcal: int
    macros: dict[str, int]
    fiber_min_g: int
    water_min_ml: int


def compute_bmr(gender: Literal["male", "female"], age: int, height_cm: float, weight_kg: float) -> float:
    """Compute basal metabolic rate using the Mifflin–St Jeor equation.

    Args:
        gender: "male" or "female".
        age: Age in years.
        height_cm: Height in centimetres.
        weight_kg: Weight in kilograms.

    Returns:
        Estimated BMR in kilocalories per day.
    """
    if gender not in ("male", "female"):
        raise ValueError(f"Unsupported gender: {gender}")
    bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age
    if gender == "male":
        bmr += 5
    else:
        bmr -= 161
    return bmr


def activity_factor(level: Literal["sedentary", "moderate", "high"]) -> float:
    """Return the multiplier for TDEE based on activity level.

    According to the specification:

    - sedentary:   1.2
    - moderate:    1.45
    - high:        1.7

    Args:
        level: Level of physical activity.

    Returns:
        A float multiplier.
    """
    factors = {
        "sedentary": 1.2,
        "moderate": 1.45,
        "high": 1.7,
    }
    try:
        return factors[level]
    except KeyError:
        raise ValueError(f"Unknown activity level: {level}")


def target_calories(tdee: float, goal_type: Literal["lose_weight", "maintain", "gain_weight"]) -> float:
    """Adjust TDEE based on the user's goal.

    The offsets are taken from the specification: minus 500 kcal to lose
    weight, no change to maintain, plus 300 kcal to gain.
    """
    match goal_type:
        case "lose_weight":
            return tdee - 500
        case "maintain":
            return tdee
        case "gain_weight":
            return tdee + 300
        case _:
            raise ValueError(f"Unknown goal type: {goal_type}")


def compute_macros(weight_kg: float, target_kcal: float) -> dict[str, int]:
    """Compute default macronutrient targets.

    Protein: 1.6 g per kg body mass.
    Fat: 30% of target calories divided by 9.
    Carbs: Remainder of calories after protein and fat (4 kcal/g).

    Args:
        weight_kg: Body weight in kilograms.
        target_kcal: Target caloric intake.

    Returns:
        Dict with keys ``protein_g``, ``fat_g`` and ``carbs_g``.
    """
    protein_g = int(round(1.6 * weight_kg))
    fat_g = int(round(0.3 * target_kcal / 9))
    # Remaining calories go to carbohydrates (1 g = 4 kcal)
    remaining_kcal = target_kcal - (protein_g * 4 + fat_g * 9)
    carbs_g = int(round(max(remaining_kcal, 0) / 4))
    return {
        "protein_g": protein_g,
        "fat_g": fat_g,
        "carbs_g": carbs_g,
    }


def compute_norms(
    *,
    gender: Literal["male", "female"],
    age: int,
    height_cm: float,
    weight_kg: float,
    activity_level: Literal["sedentary", "moderate", "high"],
    goal_type: Literal["lose_weight", "maintain", "gain_weight"],
    target_change_kg: float | None = None,
    timeframe_days: int | None = None,
) -> NormsDict:
    """Compute all nutritional norms for a user.

    This convenience function wraps BMR, TDEE and macronutrient
    calculations.  It also adds fixed recommendations for fibre and water.

    Args:
        gender: "male" or "female".
        age: Age in years.
        height_cm: Height in centimetres.
        weight_kg: Weight in kilograms.
        activity_level: Level of physical activity.
        goal_type: Desired outcome (lose_weight/maintain/gain_weight).
        target_change_kg: Desired weight change (optional, unused here).
        timeframe_days: Time frame in days for the goal (optional, unused).

    Returns:
        A dictionary with caloric and macronutrient targets.
    """
    bmr = compute_bmr(gender, age, height_cm, weight_kg)
    tdee = bmr * activity_factor(activity_level)
    target = target_calories(tdee, goal_type)
    macros = compute_macros(weight_kg, target)
    # Fibre and water minimums: 25 g fibre, 30 ml water per kg body weight
    water_min_ml = int(weight_kg * 30)
    return {
        "BMR_kcal": int(round(bmr)),
        "TDEE_kcal": int(round(tdee)),
        "target_kcal": int(round(target)),
        "macros": macros,
        "fiber_min_g": 25,
        "water_min_ml": water_min_ml,
    }

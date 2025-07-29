"""ProfileCollector agent.

This module defines a helper to construct a user's nutrition profile from
their answers.  It does not include any Telegram-specific logic; instead
it expects already parsed data and returns a pydantic ``Profile`` object.

The collector uses formulas from ``core.logic`` to compute basal and
total energy expenditure, as well as macronutrient targets.  It also
initialises the metrics configuration.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..core import logic
from ..core.schema import MetricsCfg, Norms, Profile
from .norms_ai import compute_norms_llm


async def build_profile(
    *,
    gender: str,
    age: int,
    height_cm: float,
    weight_kg: float,
    activity_level: str,
    goal_type: str,
    target_change_kg: float,
    timeframe_days: int,
    restrictions: Optional[List[str]] = None,
    preferences: Optional[List[str]] = None,
    medical: Optional[List[str]] = None,
    metrics_interval_days: Optional[int] = None,
    cfg: Optional[Dict[str, Any]] = None,
    language: str = "ru",
) -> Profile:
    """Construct a ``Profile`` from questionnaire answers.

    Args:
        gender: "male" or "female".
        age: Age in years.
        height_cm: Height in centimetres.
        weight_kg: Weight in kilograms.
        activity_level: Activity level string (sedentary/moderate/high).
        goal_type: Goal type string (lose_weight/maintain/gain_weight).
        target_change_kg: Desired weight change in kilograms.
        timeframe_days: Desired timeframe in days for reaching the goal.
        restrictions: List of dietary restrictions (can be empty or None).
        preferences: List of food dislikes (can be empty or None).
        medical: List of medical conditions (can be empty or None).
        metrics_interval_days: Optional override for metrics logging interval.
        cfg: Optional configuration dict. When it contains ``use_llm_norms`` set
            to true, nutritional norms are computed via OpenAI.
        language: Language for AI responses if LLM is used.

    Returns:
        A fully populated ``Profile`` instance.
    """
    profile_data = {
        "gender": gender,
        "age": age,
        "height_cm": height_cm,
        "weight_kg": weight_kg,
        "activity_level": activity_level,
        "goal_type": goal_type,
        "target_change_kg": target_change_kg,
        "timeframe_days": timeframe_days,
        "restrictions": restrictions or [],
        "preferences": preferences or [],
        "medical": medical or [],
    }
    if cfg and cfg.get("use_llm_norms"):
        norms = await compute_norms_llm(profile_data, cfg, language=language)
    else:
        norms_dict = logic.compute_norms(
            gender=gender,
            age=age,
            height_cm=height_cm,
            weight_kg=weight_kg,
            activity_level=activity_level,
            goal_type=goal_type,
            target_change_kg=target_change_kg,
            timeframe_days=timeframe_days,
        )
        norms = Norms(**norms_dict)
    metrics_cfg = MetricsCfg()
    if metrics_interval_days is not None:
        metrics_cfg.metrics_interval_days = metrics_interval_days
    profile = Profile(
        personal={
            "gender": gender,
            "age": age,
            "height_cm": height_cm,
            "weight_kg": weight_kg,
            "activity_level": activity_level,
        },
        goals={
            "type": goal_type,
            "target_change_kg": target_change_kg,
            "timeframe_days": timeframe_days,
        },
        restrictions=restrictions or [],
        preferences=preferences or [],
        medical=medical or [],
        norms=norms,
        metrics=metrics_cfg,
    )
    return profile


async def recompute_profile_norms(
    profile: Profile,
    cfg: Optional[Dict[str, Any]] = None,
    *,
    language: str = "ru",
) -> None:
    """Recalculate and update norms for ``profile`` in-place."""
    profile_data = {
        **profile.personal,
        **profile.goals,
        "restrictions": profile.restrictions,
        "preferences": profile.preferences,
        "medical": profile.medical,
    }
    if cfg and cfg.get("use_llm_norms"):
        norms = await compute_norms_llm(profile_data, cfg, language=language)
    else:
        norms_dict = logic.compute_norms(
            gender=profile.personal.get("gender", "female"),
            age=profile.personal.get("age"),
            height_cm=profile.personal.get("height_cm"),
            weight_kg=profile.personal.get("weight_kg"),
            activity_level=profile.personal.get("activity_level"),
            goal_type=profile.goals.get("type"),
            target_change_kg=profile.goals.get("target_change_kg"),
            timeframe_days=profile.goals.get("timeframe_days"),
        )
        norms = Norms(**norms_dict)
    profile.norms = norms

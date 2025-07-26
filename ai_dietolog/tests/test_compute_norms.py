"""Unit tests for nutritional formulas."""

import pytest

from ai_dietolog.core.logic import compute_norms


def test_compute_norms_range():
    """ensure compute_norms yields reasonable values for a male losing weight"""
    norms = compute_norms(
        gender="male",
        age=40,
        height_cm=180,
        weight_kg=90,
        activity_level="moderate",
        goal_type="lose_weight",
        target_change_kg=5,
        timeframe_days=30,
    )
    assert 1600 < norms["BMR_kcal"] < 2200
    assert norms["target_kcal"] < norms["TDEE_kcal"]

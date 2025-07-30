from __future__ import annotations

"""Load prompt templates from ``prompts.yaml`` for all agents."""

from importlib import resources
from typing import Dict

import yaml
from jinja2 import Template


def _load_prompts() -> dict:
    """Return dictionary of prompt definitions from YAML."""
    with resources.files(__package__).joinpath("prompts.yaml").open(
        "r", encoding="utf-8"
    ) as fh:
        return yaml.safe_load(fh)


_data = _load_prompts()

# Dictionaries with descriptions and compiled templates
DESCRIPTIONS: Dict[str, str] = {}
TEMPLATES: Dict[str, Template] = {}

for _name, _info in _data.items():
    DESCRIPTIONS[_name] = _info.get("description", "")
    TEMPLATES[_name] = Template(_info["template"])

# Backwards compatibility constants used across the codebase
PROFILE_TO_JSON = TEMPLATES["profile_to_json"]
MEAL_JSON = TEMPLATES["meal_json"]
UPDATE_MEAL_JSON = TEMPLATES["update_meal_json"]
CONTEXT_ANALYSIS = TEMPLATES["context_analysis"]
DAY_ANALYSIS = TEMPLATES["day_analysis"]
AI_NORMS = TEMPLATES["ai_norms"]
AI_EXPLAIN = TEMPLATES["ai_explain"]
EXTRACT_FIELD_ACTIVITY = TEMPLATES["extract_field_activity"]
EXTRACT_FIELD_NUMERIC = TEMPLATES["extract_field_numeric"]
EXTRACT_BASIC = TEMPLATES["extract_basic"]
EXTRACT_OPTIONAL = TEMPLATES["extract_optional"]

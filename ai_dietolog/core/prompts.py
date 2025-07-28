from __future__ import annotations

"""Prompt templates for OpenAI requests."""

from jinja2 import Template

# Prompt for profile editing
PROFILE_TO_JSON = Template(
    "You are a nutrition assistant.\n"
    "Below is the user's current profile JSON:\n"
    "{{ profile }}\n\n"
    "Update this profile according to the user's request and reply ONLY with\n"
    "the updated JSON that matches the Profile schema without any extra\n"
    "explanations. Any human-readable text must be in {{ language }}."
)

# Template for meal recognition
MEAL_JSON = Template(
    "You are a nutrition assistant. Meal type: {{ meal_type }}.\n"
    "User description: {{ user_desc }}. Use the attached image and text to\n"
    "identify all food items and determine the dish name if it is obvious.\n"
    "Do not guess typical foods based only on the\n"
    "meal type. Estimate weight in grams and macronutrients if not provided.\n"
    "Return JSON with keys 'items' and 'total' only. Each element in 'items'\n"
    "and the 'total' object MUST contain the keys name, weight_g, kcal,\n"
    "protein_g, fat_g, carbs_g, sugar_g and fiber_g. Use the key 'kcal' and\n"
    "never 'calories'. Any item names or other human-readable text must be in\n"
    "{{ language }}."
)

# Template for contextual analysis after добавления блюда
CONTEXT_ANALYSIS = Template(
    "You analyse the food diary.\n"
    "User norms: {{ norms }}.\n"
    "Current day summary: {{ day_summary }}.\n"
    "New meal: {{ new_meal }}.\n"
    "Return JSON with 'summary' (updated totals) and 'context_comment'. The\n"
    "comment must be in {{ language }}."
)

# Template for end-of-day analysis
DAY_ANALYSIS = Template(
    "You are a nutrition assistant.\n"
    "User norms: {{ norms }}.\n"
    "Day totals: {{ summary }}.\n"
    "Meals: {{ meals }}.\n"
    "Provide at least 5 short comments in {{ language }} about this day's intake.\n"
    "Focus on potential issues like excess sugar, lack of fibre or low calories.\n"
    "Do NOT give recommendations. Format each comment on a new line starting with '-'."
)

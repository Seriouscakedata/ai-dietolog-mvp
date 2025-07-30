from __future__ import annotations

"""Unified interface for language model calls."""

import base64
import os
from typing import Any, Iterable, Mapping, Optional

from openai import AsyncOpenAI
import google.generativeai as genai
from google.generativeai.types import content_types

from .config import load_config, openai_api_key, gemini_api_key

__all__ = ["ask_llm"]


def _to_gemini_messages(messages: Iterable[Mapping[str, Any]]) -> list[dict]:
    """Convert OpenAI-style messages to Gemini format."""
    converted: list[dict] = []
    for m in messages:
        content = m.get("content")
        parts = []
        if isinstance(content, list):
            for part in content:
                if part.get("type") == "text":
                    parts.append(part.get("text", ""))
                elif part.get("type") == "image_url":
                    url = part.get("image_url", {}).get("url", "")
                    if url.startswith("data:image"):
                        header, b64_data = url.split(",", 1)
                        mime = header.split(";")[0].split(":")[1]
                        data = base64.b64decode(b64_data)
                        parts.append({"inline_data": {"mime_type": mime, "data": data}})
        elif content is not None:
            parts.append(content)
        converted.append({"role": m.get("role", "user"), "parts": parts})
    return converted


async def ask_llm(
    messages: list[dict],
    *,
    model: str,
    provider: str | None = None,
    temperature: float = 0.0,
    response_format: dict | None = None,
    cfg: Optional[dict] = None,
) -> str:
    """Send ``messages`` to the selected LLM and return the text response."""
    cfg = cfg or load_config()
    provider = provider or cfg.get("llm_provider", "openai")

    if provider == "openai":
        api_key = cfg.get("openai_api_key") or openai_api_key()
        client = AsyncOpenAI(api_key=api_key)
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format
        resp = await client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content

    if provider == "gemini":
        api_key = cfg.get("gemini_api_key") or gemini_api_key()
        genai.configure(api_key=api_key)
        gem_model = genai.GenerativeModel(model or "gemini-pro")
        g_messages = _to_gemini_messages(messages)
        resp = await gem_model.generate_content_async(
            g_messages,
            generation_config={"temperature": temperature},
        )
        return resp.text

    raise ValueError(f"Unknown LLM provider: {provider}")

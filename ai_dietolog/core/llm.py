from __future__ import annotations

"""Unified interface for language model calls."""

import base64
import os
from typing import Any, Iterable, Mapping, Optional

from openai import AsyncOpenAI, OpenAI

from .config import gemini_api_key, load_config, openai_api_key

__all__ = ["ask_llm", "check_llm_connectivity"]


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


def check_llm_connectivity(cfg: Optional[dict] = None) -> dict[str, bool]:
    """Check connectivity to configured LLM providers.

    Returns a mapping ``{"openai": bool, "gemini": bool}`` indicating
    whether a simple request to each provider succeeded.  The function
    attempts to list available models using the provided API keys.
    """

    cfg = cfg or load_config()
    statuses = {"openai": False, "gemini": False}

    openai_key = cfg.get("openai_api_key") or openai_api_key()
    if openai_key:
        try:
            OpenAI(api_key=openai_key).models.list()
            statuses["openai"] = True
        except Exception:
            pass

    gemini_key = cfg.get("gemini_api_key") or gemini_api_key()
    if gemini_key:
        try:
            import google.generativeai as genai  # type: ignore

            genai.configure(api_key=gemini_key)
            genai.list_models()
            statuses["gemini"] = True
        except Exception:
            pass

    return statuses


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
        try:
            import google.generativeai as genai  # type: ignore
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "google-generativeai package is required for Gemini provider"
            ) from exc

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

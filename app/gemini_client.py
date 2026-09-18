"""Thin wrapper around the Gemini API (Google AI Studio, free tier).

Kept separate from the pipeline stages so classify.py / extract.py can
share one client and one structured-JSON-output convention.
"""

from __future__ import annotations

from google import genai

from app.config import settings

_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        if not settings.gemini_api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set — copy .env.example to .env and fill it in."
            )
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client

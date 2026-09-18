"""Test-suite guards.

The rule layer defers to Gemini below CONFIDENCE_FLOOR. Without this fixture
the suite would start making real (billable, rate-limited, non-deterministic)
API calls the moment GEMINI_API_KEY is present in .env. Tests cover the
deterministic layer only; the Gemini path is exercised manually.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def no_gemini_calls(monkeypatch):
    """Force the Gemini fallback to be a no-op for every test."""
    monkeypatch.setattr(
        "app.pipeline.classify.classify_with_gemini",
        lambda email: None,
    )

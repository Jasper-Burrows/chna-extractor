"""Opt-in synthetic live check; excluded by its approval gate in normal CI."""

from __future__ import annotations

import os

import pytest

from chna_extractor.config import Settings
from chna_extractor.costs import estimate_cost
from chna_extractor.extractors import OpenAIExtractor
from chna_extractor.pdf import inspect_and_extract


@pytest.mark.live
@pytest.mark.asyncio
async def test_synthetic_openai_extraction_with_explicit_approval() -> None:
    if os.environ.get("CHNA_LIVE_TEST_APPROVED", "").casefold() != "true":
        pytest.skip("set CHNA_LIVE_TEST_APPROVED=true after reviewing `chna estimate`")
    settings = Settings()
    if not settings.live_available:
        pytest.skip("a newly issued CHNA_OPENAI_API_KEY is required")
    content = inspect_and_extract(settings.fixture_path, settings)
    preflight = estimate_cost(content, settings)
    print(preflight.model_dump_json(indent=2))
    assert preflight.worst_case_cost_usd <= settings.total_budget_usd
    records, usage, _ = await OpenAIExtractor(settings).extract(content, settings.fixture_path.name)
    assert records
    assert usage.api_calls in {1, 2}

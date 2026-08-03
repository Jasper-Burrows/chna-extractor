"""Transparent preflight and realized cost calculations."""

from __future__ import annotations

import math

from chna_extractor.config import Settings
from chna_extractor.models import CostEstimate, UsageSummary
from chna_extractor.pdf import PdfContent

DEFAULT_OUTPUT_TOKENS = 2_500
EXPECTED_EXTRACTION_API_CALLS = 1
MAX_EXTRACTION_API_CALLS = 2


def estimate_cost(content: PdfContent, settings: Settings) -> CostEstimate:
    input_tokens = math.ceil(content.character_count / 4) + 1_000
    output_tokens = DEFAULT_OUTPUT_TOKENS
    per_call_cost = _cost_usd(input_tokens, 0, output_tokens, settings)
    return CostEstimate(
        page_count=content.page_count,
        character_count=content.character_count,
        estimated_input_tokens=input_tokens,
        estimated_output_tokens=output_tokens,
        expected_api_calls=EXPECTED_EXTRACTION_API_CALLS,
        worst_case_api_calls=MAX_EXTRACTION_API_CALLS,
        estimated_cost_usd=_round_up_usd(per_call_cost),
        worst_case_cost_usd=_round_up_usd(per_call_cost * MAX_EXTRACTION_API_CALLS),
        model=settings.openai_model,
        assumptions=[
            (
                "Input tokens are estimated at four extracted characters per token "
                "plus prompt overhead."
            ),
            f"Output allowance is {DEFAULT_OUTPUT_TOKENS:,} tokens.",
            "One Responses call is expected; one schema-correction call is the hard maximum.",
            "No cached-input discount is assumed in the preflight estimate.",
            "Actual provider billing can differ from this conservative estimate.",
        ],
    )


def _round_up_usd(value: float) -> float:
    """Never understate a reservation due to display precision."""
    return math.ceil(value * 1_000_000) / 1_000_000


def usage_summary(
    *,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    model: str,
    api_calls: int,
    settings: Settings,
) -> UsageSummary:
    return UsageSummary(
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        estimated_cost_usd=round(
            _cost_usd(input_tokens, cached_input_tokens, output_tokens, settings), 6
        ),
        model=model,
        api_calls=api_calls,
    )


def _cost_usd(
    input_tokens: int, cached_input_tokens: int, output_tokens: int, settings: Settings
) -> float:
    uncached = max(0, input_tokens - cached_input_tokens)
    return (
        uncached * settings.input_cost_per_million
        + cached_input_tokens * settings.cached_input_cost_per_million
        + output_tokens * settings.output_cost_per_million
    ) / 1_000_000


def merge_usage(primary: UsageSummary, additional: UsageSummary | None) -> UsageSummary:
    if additional is None:
        return primary
    model = (
        primary.model
        if primary.model == additional.model
        else f"{primary.model} + {additional.model}"
    )
    return UsageSummary(
        input_tokens=primary.input_tokens + additional.input_tokens,
        cached_input_tokens=primary.cached_input_tokens + additional.cached_input_tokens,
        output_tokens=primary.output_tokens + additional.output_tokens,
        latency_ms=primary.latency_ms + additional.latency_ms,
        estimated_cost_usd=round(primary.estimated_cost_usd + additional.estimated_cost_usd, 6),
        model=model,
        api_calls=primary.api_calls + additional.api_calls,
    )

"""Pricing registry and cost calculation (D-39).

Prices are verified from the provider's published pricing page, never typed from memory, and carry a
version and verification date. The catalogue is intentionally EMPTY until a model is chosen and its
price is verified; an unknown price yields an unknown (NULL) cost, never 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.ai.types import Usage


@dataclass(frozen=True, slots=True)
class PriceEntry:
    provider: str
    provider_model_id: str
    pricing_version: str
    input_per_million: Decimal | None
    output_per_million: Decimal | None
    currency: str
    source_url: str
    verified_on: date


PRICES: tuple[PriceEntry, ...] = ()


def find_price(provider: str, provider_model_id: str) -> PriceEntry | None:
    matches = [
        p for p in PRICES if p.provider == provider and p.provider_model_id == provider_model_id
    ]
    return max(matches, key=lambda p: p.verified_on) if matches else None


def estimate_cost(price: PriceEntry | None, usage: Usage) -> Decimal | None:
    """Cost in `price.currency`, or None when the price or either token count is unknown."""
    if (
        price is None
        or price.input_per_million is None
        or price.output_per_million is None
        or usage.input_tokens is None
        or usage.output_tokens is None
    ):
        return None
    million = Decimal(1_000_000)
    return (
        Decimal(usage.input_tokens) * price.input_per_million
        + Decimal(usage.output_tokens) * price.output_per_million
    ) / million

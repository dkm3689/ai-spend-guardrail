from __future__ import annotations

# (input_per_million, output_per_million) in USD
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-8":              (15.0,  75.0),
    "claude-opus-4-7":              (15.0,  75.0),
    "claude-sonnet-5":              (3.0,   15.0),
    "claude-sonnet-4-5":            (3.0,   15.0),
    "claude-haiku-4-5":             (0.80,  4.0),
    "claude-haiku-4-5-20251001":    (0.80,  4.0),
}

# Downgrade target for visible-downgrade mode
MODEL_DOWNGRADE_MAP: dict[str, str] = {
    "claude-opus-4-8":   "claude-haiku-4-5-20251001",
    "claude-opus-4-7":   "claude-haiku-4-5-20251001",
    "claude-sonnet-5":   "claude-haiku-4-5-20251001",
    "claude-sonnet-4-5": "claude-haiku-4-5-20251001",
}

_DEFAULT_PRICING = (3.0, 15.0)  # Sonnet-tier fallback for unknown models


def _get_pricing(model: str) -> tuple[float, float]:
    if model in MODEL_PRICING:
        return MODEL_PRICING[model]
    for key, price in MODEL_PRICING.items():
        if model.startswith(key):
            return price
    return _DEFAULT_PRICING


def compute_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    input_price, output_price = _get_pricing(model)
    return (input_tokens / 1_000_000) * input_price + (output_tokens / 1_000_000) * output_price


def get_downgrade_model(model: str) -> str | None:
    if model in MODEL_DOWNGRADE_MAP:
        return MODEL_DOWNGRADE_MAP[model]
    for key, target in MODEL_DOWNGRADE_MAP.items():
        if model.startswith(key):
            return target
    return None

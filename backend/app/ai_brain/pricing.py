"""Versioned, explicitly supplied pricing; calculations never authorize a call."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_UP


@dataclass(frozen=True)
class Pricing:
    model_id: str
    version: str
    effective_at: datetime
    input_per_million: Decimal
    output_per_million: Decimal

    def __post_init__(self):
        if not self.model_id.strip() or not self.version.strip() or self.effective_at.utcoffset() is None:
            raise ValueError('Model, version and timezone-aware effective date are required')
        for amount in (self.input_per_million, self.output_per_million):
            if not isinstance(amount, Decimal) or not amount.is_finite() or amount < 0:
                raise ValueError('Rates must be nonnegative finite Decimal values')

    def ceiling(self, input_tokens: int, output_tokens: int, attempts: int = 1) -> Decimal:
        if any(type(value) is not int or value < 0 for value in (input_tokens, output_tokens)) or type(attempts) is not int or not 1 <= attempts <= 10:
            raise ValueError('Invalid token limits or attempts')
        cost = (self.input_per_million * input_tokens + self.output_per_million * output_tokens) * attempts / Decimal(1_000_000)
        return cost.quantize(Decimal('0.000001'), rounding=ROUND_UP)

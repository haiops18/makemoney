"""Provider contract and isolated test double. No network capability is exposed."""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int

    def __post_init__(self):
        if self.input_tokens < 0 or self.output_tokens < 0:
            raise ValueError('Token usage cannot be negative')


@dataclass(frozen=True)
class ProviderResult:
    payload: object
    usage: Usage
    provider_request_id: str | None = None


class ResearchProvider(Protocol):
    def generate(self, *, objective: str, max_output_tokens: int) -> ProviderResult: ...


class MockProvider:
    """Explicitly injected test double; never registered for production execution."""
    def __init__(self, result: ProviderResult):
        self.result = result
        self.calls = 0

    def generate(self, *, objective: str, max_output_tokens: int) -> ProviderResult:
        if not objective.strip() or not 1 <= max_output_tokens <= 100000:
            raise ValueError('Invalid invocation limits')
        self.calls += 1
        return self.result

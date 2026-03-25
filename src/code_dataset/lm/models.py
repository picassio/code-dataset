"""Model definitions for code-dataset.

Provides model metadata (context windows, max tokens) used by LM classes
to set appropriate defaults.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ModelCost:
    """Cost per million tokens in USD."""

    input: float = 0.0
    output: float = 0.0
    cache_read: float = 0.0
    cache_write: float = 0.0


@dataclass
class ModelInfo:
    """Model metadata."""

    id: str
    name: str
    provider: str
    context_window: int = 128000
    max_tokens: int = 8192
    cost: ModelCost = field(default_factory=ModelCost)

    @property
    def short_id(self) -> str:
        """Model ID without provider prefix."""
        return self.id.split("/", 1)[-1] if "/" in self.id else self.id


MODELS: list[ModelInfo] = [
    # Anthropic
    ModelInfo(
        id="anthropic/claude-3-5-haiku-20241022",
        name="Claude Haiku 3.5",
        provider="anthropic",
        context_window=200000,
        max_tokens=8192,
        cost=ModelCost(input=0.8, output=4),
    ),
    ModelInfo(
        id="anthropic/claude-3-5-sonnet-20241022",
        name="Claude Sonnet 3.5 v2",
        provider="anthropic",
        context_window=200000,
        max_tokens=8192,
        cost=ModelCost(input=3, output=15),
    ),
    ModelInfo(
        id="anthropic/claude-3-7-sonnet-20250219",
        name="Claude Sonnet 3.7",
        provider="anthropic",
        context_window=200000,
        max_tokens=64000,
        cost=ModelCost(input=3, output=15),
    ),
    ModelInfo(
        id="anthropic/claude-sonnet-4-20250514",
        name="Claude Sonnet 4",
        provider="anthropic",
        context_window=200000,
        max_tokens=64000,
        cost=ModelCost(input=3, output=15),
    ),
    ModelInfo(
        id="anthropic/claude-opus-4-20250514",
        name="Claude Opus 4",
        provider="anthropic",
        context_window=200000,
        max_tokens=32000,
        cost=ModelCost(input=15, output=75),
    ),
    # Google
    ModelInfo(
        id="google/gemini-2.0-flash",
        name="Gemini 2.0 Flash",
        provider="google",
        context_window=1048576,
        max_tokens=8192,
        cost=ModelCost(input=0.1, output=0.4),
    ),
    ModelInfo(
        id="google/gemini-2.5-pro",
        name="Gemini 2.5 Pro",
        provider="google",
        context_window=1048576,
        max_tokens=65536,
        cost=ModelCost(input=1.25, output=10),
    ),
    ModelInfo(
        id="google/gemini-2.5-flash",
        name="Gemini 2.5 Flash",
        provider="google",
        context_window=1048576,
        max_tokens=65536,
        cost=ModelCost(input=0.15, output=0.6),
    ),
    # OpenAI
    ModelInfo(
        id="openai/gpt-4o",
        name="GPT-4o",
        provider="openai",
        context_window=128000,
        max_tokens=16384,
        cost=ModelCost(input=2.5, output=10),
    ),
    ModelInfo(
        id="openai/gpt-4o-mini",
        name="GPT-4o Mini",
        provider="openai",
        context_window=128000,
        max_tokens=16384,
        cost=ModelCost(input=0.15, output=0.6),
    ),
    ModelInfo(
        id="openai/o3-mini",
        name="o3-mini",
        provider="openai",
        context_window=200000,
        max_tokens=100000,
        cost=ModelCost(input=1.1, output=4.4),
    ),
]

_MODEL_BY_ID: dict[str, ModelInfo] = {m.id: m for m in MODELS}
_MODEL_BY_SHORT_ID: dict[str, ModelInfo] = {m.short_id: m for m in MODELS}


def find_model(model_id: str) -> ModelInfo | None:
    """Find model info by full or short ID.

    Args:
        model_id: Full ID (e.g., "anthropic/claude-sonnet-4-20250514")
                  or short ID (e.g., "claude-sonnet-4-20250514")

    Returns:
        ModelInfo if found, None otherwise.
    """
    return _MODEL_BY_ID.get(model_id) or _MODEL_BY_SHORT_ID.get(model_id)


def list_models(provider: str | None = None) -> list[ModelInfo]:
    """List all models, optionally filtered by provider."""
    if provider:
        return [m for m in MODELS if m.provider == provider]
    return MODELS.copy()

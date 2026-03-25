"""LM factory — creates DSPy LMs using our own OAuth system.

NEVER uses LiteLLM. Supports:
- Anthropic (AnthropicOAuthLM) — OAuth tokens and API keys
- Google (GoogleOAuthLM) — Cloud Code Assist OAuth
- OpenAI (dspy.LM) — standard API key
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

import dspy

if TYPE_CHECKING:
    from ..config import Config

logger = logging.getLogger(__name__)


def create_lm(config: Config) -> dspy.LM:
    """Create a DSPy-compatible LM from configuration.

    Reads provider/model from config.yaml, secrets from .env or OAuth credentials.

    Args:
        config: Application configuration.

    Returns:
        A configured DSPy LM instance.

    Raises:
        ValueError: If the provider is unknown or credentials are missing.
    """
    provider = config.llm_provider
    model = config.llm_model
    temperature = config.llm_temperature
    max_tokens = config.llm_max_tokens
    num_retries = config.llm_num_retries

    if provider == "anthropic":
        return _create_anthropic_lm(model, temperature, max_tokens, num_retries)
    elif provider == "google":
        return _create_google_lm(model, temperature, max_tokens, num_retries)
    elif provider == "openai":
        return _create_openai_lm(model, temperature, max_tokens)
    else:
        raise ValueError(f"Unknown LLM provider: {provider!r}. Supported: anthropic, google, openai")


def _create_anthropic_lm(
    model: str,
    temperature: float,
    max_tokens: int,
    num_retries: int,
) -> dspy.LM:
    """Create an Anthropic LM with OAuth or API key support."""
    from .anthropic_lm import AnthropicOAuthLM, get_anthropic_api_key

    api_key = get_anthropic_api_key()
    if not api_key:
        raise ValueError(
            "No Anthropic API key found. Either:\n"
            "  1. Set ANTHROPIC_API_KEY in .env\n"
            "  2. Run 'code-dataset auth login anthropic' for OAuth"
        )

    return AnthropicOAuthLM(
        model=model,
        auth_token=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        num_retries=num_retries,
    )


def _create_google_lm(
    model: str,
    temperature: float,
    max_tokens: int,
    num_retries: int,
) -> dspy.LM:
    """Create a Google Gemini LM with OAuth."""
    from .google_lm import GoogleOAuthLM

    return GoogleOAuthLM(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        num_retries=num_retries,
    )


def _create_openai_lm(
    model: str,
    temperature: float,
    max_tokens: int,
) -> dspy.LM:
    """Create an OpenAI LM using standard API key."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set in .env or environment")

    return dspy.LM(
        f"openai/{model}",
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
    )

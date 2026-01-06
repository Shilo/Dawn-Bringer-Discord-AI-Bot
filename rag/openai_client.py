"""OpenAI client utilities for the RAG system."""

from openai import OpenAI
from configs import Config

# Lazy-loaded OpenAI client singleton
_client = None


def _get_client():
    """Get or create the OpenAI client singleton."""
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


class AdaptedUsage:
    """Adapt Responses API usage to match expected Chat Completions API format."""

    def __init__(self, responses_usage):
        if responses_usage is None:
            self.prompt_tokens = 0
            self.completion_tokens = 0
            self.total_tokens = 0
            return

        self.prompt_tokens = getattr(responses_usage, "input_tokens", 0)
        self.completion_tokens = getattr(responses_usage, "output_tokens", 0)

        # Prefer the API-provided total_tokens when available
        self.total_tokens = getattr(
            responses_usage, "total_tokens", self.prompt_tokens + self.completion_tokens
        )


def is_gpt_5_model() -> bool:
    """Check if the current model is GPT-5."""
    return Config.MODEL.startswith("gpt-5")


def get_usage(response) -> object:
    """Adapt Responses API usage to match expected Chat Completions API format.

    Args:
        response: OpenAI response object with usage attribute

    Returns:
        Adapted usage object with prompt_tokens, completion_tokens, total_tokens attributes
    """
    return AdaptedUsage(getattr(response, "usage", None))


def prompt_openai(messages: list, max_tokens_to_use: int) -> tuple[str, object]:
    """Prompt OpenAI using Responses API for all models.

    Args:
        messages: List of message dicts (system + user + context)
        max_tokens_to_use: Maximum output tokens

    Returns:
        Tuple of (response_text, usage_object)
    """
    kwargs = dict(
        model=Config.MODEL,
        input=messages,  # Pass full conversation: system + user (+ context)
        max_output_tokens=max_tokens_to_use,
    )

    # Only include GPT-5 specific parameters for reasoning models
    if is_gpt_5_model():
        kwargs["reasoning"] = {"effort": Config.GPT5_EFFORT}
        kwargs["text"] = {"verbosity": Config.GPT5_VERBOSITY}
        # No temperature for GPT-5 reasoning models
    else:
        # For models that support it, include temperature
        kwargs["temperature"] = Config.TEMPERATURE

    response = _get_client().responses.create(**kwargs)
    response_text = response.output_text  # Use the simple output_text property
    usage = get_usage(response)

    return response_text, usage

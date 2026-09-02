class LLMError(Exception):
    """Base exception for LLM-related errors."""

class LLMConfigError(LLMError):
    """Raised when LLM configuration is invalid."""

class LLMResponseError(LLMError):
    """Raised when LLM response cannot be parsed as JSON after retries."""

class LLMNotConfiguredError(LLMError):
    """Raised when auto-grill methods are called but no LLM client is injected."""

from __future__ import annotations
import json
import logging
import re
from typing import Protocol, runtime_checkable
from cui.llm.errors import LLMResponseError

logger = logging.getLogger(__name__)

@runtime_checkable
class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str: ...
    def complete_json(self, system: str, user: str, retries: int = 2) -> dict: ...


def _strip_markdown_fences(raw: str) -> str:
    raw = raw.strip()
    m = re.search(r"```\w*\n(.*?)\n```", raw, re.DOTALL)
    if m:
        return m.group(1).strip()
    return raw


def _complete_json_with_retry(client: LLMClient, system: str, user: str, retries: int) -> dict:
    last_raw = ""
    for attempt in range(retries + 1):
        last_raw = client.complete(system, user)
        cleaned = _strip_markdown_fences(last_raw)
        try:
            result = json.loads(cleaned)
            if isinstance(result, dict):
                return result
            return {"data": result}
        except json.JSONDecodeError:
            logger.warning("JSON parse failed (attempt %d/%d): %s...", attempt + 1, retries + 1, cleaned[:200])
            if attempt == retries:
                raise LLMResponseError(f"Failed to parse JSON after {retries + 1} attempts. Last response: {last_raw[:500]}")
    raise LLMResponseError("Retry loop exhausted")


class OpenAIClient:
    def __init__(self, api_key: str, model: str, base_url: str | None = None) -> None:
        from openai import OpenAI
        kwargs: dict = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)
        self._model = model

    def complete(self, system: str, user: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.1,
        )
        return response.choices[0].message.content or ""

    def complete_json(self, system: str, user: str, retries: int = 2) -> dict:
        return _complete_json_with_retry(self, system, user, retries)


class AnthropicClient:
    def __init__(self, api_key: str, model: str, base_url: str | None = None) -> None:
        from anthropic import Anthropic
        self._client = Anthropic(api_key=api_key, base_url=base_url) if base_url else Anthropic(api_key=api_key)
        self._model = model

    def complete(self, system: str, user: str) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        if response.stop_reason == "refusal":
            raise LLMResponseError("Anthropic refused the challenge request")
        text = next((block.text for block in response.content if block.type == "text"), None)
        if not text:
            raise LLMResponseError(f"Anthropic returned no text (stop_reason={response.stop_reason})")
        return text

    def complete_json(self, system: str, user: str, retries: int = 2) -> dict:
        schema = {"type": "object", "properties": {"attack_surface": {"type": "string"}, "why_it_matters": {"type": "string"}, "self_check_method": {"type": "string"}, "uncertainty": {"type": "string"}}, "required": ["attack_surface", "why_it_matters", "self_check_method", "uncertainty"], "additionalProperties": False}
        try:
            response = self._client.messages.create(model=self._model, max_tokens=2048, system=system, messages=[{"role": "user", "content": user}], output_config={"format": {"type": "json_schema", "schema": schema}})
        except TypeError as exc:
            raise LLMResponseError("installed Anthropic SDK does not support structured JSON output") from exc
        if response.stop_reason == "refusal": raise LLMResponseError("Anthropic refused the challenge request")
        raw = next((block.text for block in response.content if block.type == "text"), None)
        if not raw: raise LLMResponseError(f"Anthropic returned no structured text (stop_reason={response.stop_reason})")
        try: result = json.loads(raw)
        except json.JSONDecodeError as exc: raise LLMResponseError("Anthropic structured output was not valid JSON") from exc
        if not isinstance(result, dict): raise LLMResponseError("Anthropic structured output was not an object")
        return result


def create_client(config) -> LLMClient:
    from cui.llm.config import LLMConfig
    if config.provider == "anthropic":
        return AnthropicClient(api_key=config.api_key, model=config.model, base_url=config.base_url)
    return OpenAIClient(api_key=config.api_key, model=config.model, base_url=config.base_url)

"""Provider-independent AI interfaces, errors and structured-output parsing."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger("tenderpilot.ai")

T = TypeVar("T", bound=BaseModel)


class AIError(Exception):
    """Base class. ``str(exc)`` is safe to show to end users (never contains secrets)."""


class AINotConfiguredError(AIError):
    pass


class AIProviderError(AIError):
    pass


class AIOutputError(AIError):
    pass


@dataclass(frozen=True)
class AIConfig:
    provider: str  # none | demo | openai | anthropic | gemini
    model: str
    api_key: str = ""
    source: str = "environment"  # environment | organization
    timeout: float = 180.0
    max_retries: int = 2

    @property
    def is_demo(self) -> bool:
        return self.provider == "demo"

    @property
    def is_configured(self) -> bool:
        if self.provider == "demo":
            return True
        return self.provider in {"openai", "anthropic", "gemini"} and bool(self.api_key) and bool(self.model)

    def __repr__(self) -> str:  # never leak the key in logs / tracebacks
        return f"AIConfig(provider={self.provider!r}, model={self.model!r}, source={self.source!r}, key_set={bool(self.api_key)})"


@dataclass
class RawCompletion:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass
class AIResult(Generic[T]):
    data: T
    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class ProviderAdapter(Protocol):
    name: str

    def complete(self, config: AIConfig, system: str, user: str, max_tokens: int) -> RawCompletion: ...


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def extract_json(text: str) -> object:
    cleaned = _FENCE_RE.sub("", text.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


def json_instruction(schema: type[BaseModel]) -> str:
    return (
        "\n\nRESPONSE FORMAT: Respond with a single JSON object only - no prose, no markdown fences. "
        "It must validate against this JSON Schema:\n" + json.dumps(schema.model_json_schema(), separators=(",", ":"))
    )


def run_structured(adapter: ProviderAdapter, config: AIConfig, system: str, user: str, schema: type[T], max_tokens: int = 16000) -> AIResult[T]:
    """Call the provider and validate the JSON output with Pydantic; one repair attempt on invalid output."""
    sys_prompt = system + json_instruction(schema)
    in_tok = out_tok = 0
    have_usage = False
    prompt = user
    last_error = ""
    for attempt in range(2):
        raw = adapter.complete(config, sys_prompt, prompt, max_tokens)
        if raw.input_tokens is not None:
            in_tok += raw.input_tokens
            have_usage = True
        if raw.output_tokens is not None:
            out_tok += raw.output_tokens
            have_usage = True
        try:
            data = schema.model_validate(extract_json(raw.text))
            return AIResult(
                data=data,
                provider=config.provider,
                model=config.model,
                input_tokens=in_tok if have_usage else None,
                output_tokens=out_tok if have_usage else None,
            )
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = str(exc)[:1500]
            logger.warning("AI output failed validation (attempt %s): %s", attempt + 1, type(exc).__name__)
            prompt = (
                user
                + "\n\nYour previous response was not valid JSON for the required schema. Validation error:\n"
                + last_error
                + "\nReturn ONLY the corrected JSON object."
            )
    raise AIOutputError("The AI provider returned output that did not match the required structure. Please retry.")

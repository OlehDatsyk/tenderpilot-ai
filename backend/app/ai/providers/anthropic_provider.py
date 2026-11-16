"""Anthropic Claude adapter (official ``anthropic`` SDK)."""

from __future__ import annotations

from typing import Any

import anthropic

from app.ai.base import AIConfig, AIProviderError, RawCompletion

# Models that accept ``output_config.effort``.
_EFFORT_PREFIXES = ("claude-opus-5", "claude-fable", "claude-sonnet-5", "claude-haiku-5", "claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6")
# Models that support server-side refusal fallbacks with ``fallbacks="default"``.
_FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-2", "claude-fable-5-1", "claude-sonnet-5-5"}
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicAdapter:
    name = "anthropic"

    def complete(self, config: AIConfig, system: str, user: str, max_tokens: int) -> RawCompletion:
        client = anthropic.Anthropic(api_key=config.api_key, timeout=config.timeout, max_retries=config.max_retries)
        params: dict = {
            "model": config.model,
            "max_tokens": max(max_tokens, 32000),
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if config.model.startswith(_EFFORT_PREFIXES):
            params["output_config"] = {"effort": "high"}
        message: Any
        try:
            # Streaming avoids HTTP timeouts on long structured outputs.
            if config.model in _FALLBACK_MODELS:
                with client.beta.messages.stream(betas=[_FALLBACK_BETA], fallbacks="default", **params) as stream:
                    message = stream.get_final_message()
            else:
                with client.messages.stream(**params) as stream:
                    message = stream.get_final_message()
        except anthropic.AuthenticationError as exc:
            raise AIProviderError("Anthropic rejected the API key (authentication failed).") from exc
        except anthropic.PermissionDeniedError as exc:
            raise AIProviderError("The Anthropic API key does not have permission for this model.") from exc
        except anthropic.NotFoundError as exc:
            raise AIProviderError(f"Anthropic model '{config.model}' was not found.") from exc
        except anthropic.RateLimitError as exc:
            raise AIProviderError("Anthropic rate limit reached. Please try again shortly.") from exc
        except anthropic.BadRequestError as exc:
            raise AIProviderError("Anthropic rejected the request (bad request). The documents may be too large.") from exc
        except anthropic.APITimeoutError as exc:
            raise AIProviderError("The Anthropic request timed out.") from exc
        except anthropic.APIConnectionError as exc:
            raise AIProviderError("Could not connect to the Anthropic API.") from exc
        except anthropic.APIStatusError as exc:
            raise AIProviderError(f"Anthropic API error (HTTP {exc.status_code}).") from exc

        if message.stop_reason == "refusal":
            raise AIProviderError("The model declined to process this request.")
        if message.stop_reason == "max_tokens":
            raise AIProviderError("The AI response was cut off (output limit reached). Try fewer or smaller documents.")
        text = "".join(getattr(block, "text", "") for block in message.content if getattr(block, "type", "") == "text")
        usage = getattr(message, "usage", None)
        return RawCompletion(
            text=text,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
        )

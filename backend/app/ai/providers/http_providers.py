"""OpenAI and Google Gemini adapters (REST over httpx, no vendor SDK required)."""

from __future__ import annotations

import random
import time

import httpx

from app.ai.base import AIConfig, AIProviderError, RawCompletion

_RETRYABLE = {408, 409, 429, 500, 502, 503, 504}


def _post_with_retries(provider: str, url: str, headers: dict, body: dict, config: AIConfig) -> dict:
    last_exc: Exception | None = None
    for attempt in range(config.max_retries + 1):
        try:
            with httpx.Client(timeout=config.timeout) as client:
                resp = client.post(url, headers=headers, json=body)
        except httpx.TimeoutException as exc:
            last_exc = AIProviderError(f"The {provider} request timed out.")
            last_exc.__cause__ = exc
        except httpx.HTTPError as exc:
            last_exc = AIProviderError(f"Could not connect to the {provider} API.")
            last_exc.__cause__ = exc
        else:
            if resp.status_code < 400:
                return resp.json()
            if resp.status_code in (401, 403):
                raise AIProviderError(f"{provider} rejected the API key (HTTP {resp.status_code}).")
            if resp.status_code == 404:
                raise AIProviderError(f"{provider} model '{config.model}' was not found.")
            if resp.status_code not in _RETRYABLE:
                raise AIProviderError(f"{provider} rejected the request (HTTP {resp.status_code}).")
            last_exc = AIProviderError(f"{provider} API error (HTTP {resp.status_code}).")
        if attempt < config.max_retries:
            time.sleep(min(2**attempt + random.uniform(0, 0.5), 20))
    assert last_exc is not None
    raise last_exc


class OpenAIAdapter:
    name = "openai"
    url = "https://api.openai.com/v1/chat/completions"

    def complete(self, config: AIConfig, system: str, user: str, max_tokens: int) -> RawCompletion:
        body = {
            "model": config.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_object"},
            "max_completion_tokens": max_tokens,
        }
        headers = {"Authorization": f"Bearer {config.api_key}"}
        data = _post_with_retries("OpenAI", self.url, headers, body, config)
        try:
            choice = data["choices"][0]
            text = choice["message"].get("content") or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise AIProviderError("OpenAI returned an unexpected response.") from exc
        if choice.get("finish_reason") == "length":
            raise AIProviderError("The AI response was cut off (output limit reached).")
        usage = data.get("usage") or {}
        return RawCompletion(text, usage.get("prompt_tokens"), usage.get("completion_tokens"))


class GeminiAdapter:
    name = "gemini"

    def complete(self, config: AIConfig, system: str, user: str, max_tokens: int) -> RawCompletion:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.model}:generateContent"
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": max_tokens},
        }
        headers = {"x-goog-api-key": config.api_key}
        data = _post_with_retries("Gemini", url, headers, body, config)
        try:
            candidate = data["candidates"][0]
            text = "".join(p.get("text", "") for p in candidate["content"]["parts"])
        except (KeyError, IndexError, TypeError) as exc:
            raise AIProviderError("Gemini returned no usable content (it may have been blocked).") from exc
        if candidate.get("finishReason") == "MAX_TOKENS":
            raise AIProviderError("The AI response was cut off (output limit reached).")
        usage = data.get("usageMetadata") or {}
        return RawCompletion(text, usage.get("promptTokenCount"), usage.get("candidatesTokenCount"))

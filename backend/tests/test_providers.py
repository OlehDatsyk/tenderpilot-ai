"""Provider adapters with mocked SDK / HTTP transports. No network calls are made."""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from app.ai.base import AIConfig, AIProviderError
from app.ai.providers import anthropic_provider, http_providers


class _Stream:
    def __init__(self, message):
        self.message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.message


def _fake_anthropic(monkeypatch, message, calls):
    class FakeMessages:
        def stream(self, **kw):
            calls.append(kw)
            return _Stream(message)

    class FakeClient:
        def __init__(self, **kw):
            calls.append({"client": kw})
            self.messages = FakeMessages()
            self.beta = SimpleNamespace(messages=FakeMessages())

    monkeypatch.setattr(anthropic_provider.anthropic, "Anthropic", FakeClient)


def _msg(stop="end_turn", text='{"ok": true}'):
    return SimpleNamespace(
        stop_reason=stop,
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=11, output_tokens=7),
    )


def test_anthropic_adapter_request_shape(monkeypatch):
    calls: list = []
    _fake_anthropic(monkeypatch, _msg(), calls)
    cfg = AIConfig(provider="anthropic", model="claude-opus-5-5", api_key="sk-x", timeout=30, max_retries=1)
    out = anthropic_provider.AnthropicAdapter().complete(cfg, "SYS", "USER", 1000)
    assert out.text == '{"ok": true}' and out.input_tokens == 11 and out.output_tokens == 7
    client_kw, req = calls[0]["client"], calls[1]
    assert client_kw == {"api_key": "sk-x", "timeout": 30, "max_retries": 1}
    assert req["model"] == "claude-opus-5-5" and req["system"] == "SYS"
    assert req["messages"] == [{"role": "user", "content": "USER"}]
    assert req["output_config"] == {"effort": "high"}
    assert req["fallbacks"] == "default" and req["betas"] == ["server-side-fallback-2026-07-01"]
    assert "temperature" not in req and "thinking" not in req


def test_anthropic_adapter_older_model_has_no_beta_params(monkeypatch):
    calls: list = []
    _fake_anthropic(monkeypatch, _msg(), calls)
    anthropic_provider.AnthropicAdapter().complete(AIConfig(provider="anthropic", model="claude-haiku-4-5", api_key="k"), "S", "U", 100)
    req = calls[1]
    assert "fallbacks" not in req and "output_config" not in req


@pytest.mark.parametrize("stop,msg", [("refusal", "declined"), ("max_tokens", "cut off")])
def test_anthropic_adapter_stop_reasons(monkeypatch, stop, msg):
    _fake_anthropic(monkeypatch, _msg(stop=stop), [])
    with pytest.raises(AIProviderError, match=msg):
        anthropic_provider.AnthropicAdapter().complete(AIConfig(provider="anthropic", model="claude-opus-5-5", api_key="k"), "S", "U", 100)


class _FakeHTTP:
    def __init__(self, responses, seen):
        self.responses, self.seen = responses, seen

    def __call__(self, timeout):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, headers, json):
        self.seen.append({"url": url, "headers": headers, "json": json})
        status, body = self.responses.pop(0)
        return httpx.Response(status, json=body, request=httpx.Request("POST", url))


def test_openai_adapter_retries_then_succeeds(monkeypatch):
    seen: list = []
    body = {"choices": [{"message": {"content": '{"a": 1}'}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 5, "completion_tokens": 3}}
    monkeypatch.setattr(http_providers.httpx, "Client", _FakeHTTP([(503, {}), (200, body)], seen))
    monkeypatch.setattr(http_providers.time, "sleep", lambda s: None)
    out = http_providers.OpenAIAdapter().complete(AIConfig(provider="openai", model="m", api_key="sk-o", max_retries=2), "S", "U", 50)
    assert json.loads(out.text) == {"a": 1} and out.input_tokens == 5 and len(seen) == 2
    assert seen[0]["headers"]["Authorization"] == "Bearer sk-o"
    assert seen[0]["json"]["response_format"] == {"type": "json_object"}


def test_openai_adapter_auth_error_is_not_retried(monkeypatch):
    seen: list = []
    monkeypatch.setattr(http_providers.httpx, "Client", _FakeHTTP([(401, {"error": "bad key sk-o"})], seen))
    with pytest.raises(AIProviderError) as err:
        http_providers.OpenAIAdapter().complete(AIConfig(provider="openai", model="m", api_key="sk-o", max_retries=3), "S", "U", 50)
    assert len(seen) == 1 and "sk-o" not in str(err.value)


def test_gemini_adapter(monkeypatch):
    seen: list = []
    body = {
        "candidates": [{"content": {"parts": [{"text": '{"g": 2}'}]}, "finishReason": "STOP"}],
        "usageMetadata": {"promptTokenCount": 9, "candidatesTokenCount": 4},
    }
    monkeypatch.setattr(http_providers.httpx, "Client", _FakeHTTP([(200, body)], seen))
    out = http_providers.GeminiAdapter().complete(AIConfig(provider="gemini", model="gem", api_key="g-key"), "S", "U", 50)
    assert json.loads(out.text) == {"g": 2} and out.output_tokens == 4
    assert seen[0]["url"].endswith("/models/gem:generateContent") and seen[0]["headers"] == {"x-goog-api-key": "g-key"}
    assert "g-key" not in seen[0]["url"]  # key is sent in a header, never in the URL

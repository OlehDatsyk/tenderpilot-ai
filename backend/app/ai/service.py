"""Resolve the effective AI configuration for an organisation and run structured calls."""

from __future__ import annotations

import uuid

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.base import AIConfig, AINotConfiguredError, AIResult, T, run_structured
from app.ai.providers import get_adapter
from app.core.config import DEFAULT_MODELS, get_settings
from app.core.security import EncryptionUnavailableError, decrypt_secret
from app.models import OrganizationAISettings

NOT_CONFIGURED_MESSAGE = (
    "AI is not configured. An administrator can choose a provider in Settings → AI provider "
    "(or set AI_PROVIDER and an API key on the server). Demo mode can be enabled for evaluation."
)


def resolve_config(db: Session, organization_id: uuid.UUID) -> AIConfig:
    settings = get_settings()
    row = db.scalar(select(OrganizationAISettings).where(OrganizationAISettings.organization_id == organization_id))
    if row is not None and row.provider != "default":
        provider = row.provider
        model = row.model or DEFAULT_MODELS.get(provider, "")
        key = ""
        if row.encrypted_api_key and settings.allow_org_ai_keys:
            try:
                key = decrypt_secret(row.encrypted_api_key)
            except EncryptionUnavailableError:
                key = ""
        if not key and provider in {"openai", "anthropic", "gemini"}:
            key = settings.env_api_key(provider)
        source = "organization"
    else:
        provider = settings.ai_provider
        model = settings.ai_model or DEFAULT_MODELS.get(provider, "")
        key = settings.env_api_key(provider)
        source = "environment"
    return AIConfig(
        provider=provider,
        model=model,
        api_key=key,
        source=source,
        timeout=settings.ai_timeout_seconds,
        max_retries=settings.ai_max_retries,
    )


def require_configured(config: AIConfig) -> None:
    if not config.is_configured:
        raise AINotConfiguredError(NOT_CONFIGURED_MESSAGE)


def call_structured(config: AIConfig, system: str, user: str, schema: type[T], max_tokens: int = 16000) -> AIResult[T]:
    require_configured(config)
    if config.is_demo:  # demo mode never calls providers; callers use app.ai.demo directly
        raise AINotConfiguredError("Demo mode does not call an AI provider.")
    return run_structured(get_adapter(config), config, system, user, schema, max_tokens)


def describe(config: AIConfig) -> dict:
    return {
        "provider": config.provider,
        "model": config.model,
        "source": config.source,
        "configured": config.is_configured,
        "is_demo": config.is_demo,
        "api_key_set": bool(config.api_key),
        "message": None if config.is_configured else NOT_CONFIGURED_MESSAGE,
    }


__all__ = ["BaseModel", "call_structured", "describe", "require_configured", "resolve_config"]

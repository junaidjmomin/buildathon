from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import Settings, get_settings


class TextProvider(Protocol):
    async def generate(self, *, system: str, prompt: str) -> str: ...


class AiNotConfiguredError(RuntimeError):
    pass


class GroqTextProvider:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.transport = transport

    async def generate(self, *, system: str, prompt: str) -> str:
        async with httpx.AsyncClient(
            base_url="https://api.groq.com/openai/v1",
            timeout=30,
            transport=self.transport,
        ) as client:
            response = await client.post(
                "/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "temperature": 0,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                },
            )
            response.raise_for_status()
            payload = response.json()
            return str(payload["choices"][0]["message"]["content"])


@dataclass(frozen=True)
class AiRuntime:
    provider: str
    model: str
    configured: bool
    provider_client: TextProvider | None
    fallback_policy: str


def build_ai_runtime(settings: Settings | None = None) -> AiRuntime:
    config = settings or get_settings()
    provider = config.llm_provider.strip().lower()
    if provider == "groq" and config.groq_api_key:
        return AiRuntime(
            provider=provider,
            model=config.llm_model,
            configured=True,
            provider_client=GroqTextProvider(
                api_key=config.groq_api_key,
                model=config.llm_model,
            ),
            fallback_policy="Deterministic verification remains authoritative.",
        )
    return AiRuntime(
        provider=provider or "none",
        model=config.llm_model,
        configured=False,
        provider_client=None,
        fallback_policy=(
            "AI-only actions are unavailable; the deterministic sl3dge pipeline "
            "remains fully operational."
        ),
    )

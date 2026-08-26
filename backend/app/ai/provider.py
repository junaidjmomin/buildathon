from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypeVar

import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from pydantic import BaseModel

from app.core.config import Settings, get_settings


class TextProvider(Protocol):
    async def generate(self, *, system: str, prompt: str) -> str: ...


StructuredOutput = TypeVar("StructuredOutput", bound=BaseModel)


class StructuredProvider(TextProvider, Protocol):
    async def generate_structured(
        self,
        *,
        schema: type[StructuredOutput],
        system: str,
        prompt: str,
    ) -> StructuredOutput: ...


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


class GroqStructuredProvider:
    """Provider adapter with schema-constrained output and bounded model usage."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: int,
        max_output_tokens: int,
        max_input_chars: int,
    ) -> None:
        self.model_name = model
        self.max_input_chars = max_input_chars
        self.model = ChatGroq(
            api_key=api_key,
            model=model,
            temperature=0,
            max_tokens=max_output_tokens,
            timeout=timeout_seconds,
            max_retries=2,
        )

    def _messages(self, *, system: str, prompt: str) -> list[SystemMessage | HumanMessage]:
        if len(system) + len(prompt) > self.max_input_chars:
            raise ValueError("LLM input exceeds the configured redacted-context limit")
        return [SystemMessage(content=system), HumanMessage(content=prompt)]

    async def generate(self, *, system: str, prompt: str) -> str:
        response = await self.model.ainvoke(self._messages(system=system, prompt=prompt))
        if isinstance(response.content, str):
            return response.content
        return str(response.content)

    async def generate_structured(
        self,
        *,
        schema: type[StructuredOutput],
        system: str,
        prompt: str,
    ) -> StructuredOutput:
        structured = self.model.with_structured_output(
            schema,
            method="json_schema",
            strict=True,
        )
        result = await structured.ainvoke(self._messages(system=system, prompt=prompt))
        if isinstance(result, schema):
            return result
        return schema.model_validate(result)


@dataclass(frozen=True)
class AiRuntime:
    provider: str
    model: str
    configured: bool
    provider_client: StructuredProvider | None
    fallback_policy: str


def build_ai_runtime(settings: Settings | None = None) -> AiRuntime:
    config = settings or get_settings()
    provider = config.llm_provider.strip().lower()
    groq_api_key = config.groq_api_key.get_secret_value()
    if provider == "groq" and groq_api_key:
        return AiRuntime(
            provider=provider,
            model=config.llm_model,
            configured=True,
            provider_client=GroqStructuredProvider(
                api_key=groq_api_key,
                model=config.llm_model,
                timeout_seconds=config.llm_timeout_seconds,
                max_output_tokens=config.llm_max_output_tokens,
                max_input_chars=config.llm_max_input_chars,
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

"""Unified LLM client with provider routing, retries, and fallback models."""

from __future__ import annotations

import asyncio
import json
import os
import re
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx
from openai import APIConnectionError, APIStatusError, AsyncOpenAI, RateLimitError

from app.config import settings
from app.utils.logger import logger


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class LLMUnavailableError(Exception):
    """Raised when every candidate model/provider is unavailable."""


# ---------------------------------------------------------------------------
# Model Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ModelConfig:
    """Configuration for a single model entry."""

    provider: str                      # "openai" | "deepseek"
    model: str                         # Model identifier, for example "deepseek/deepseek-v3.2".
    supports_streaming: bool = True
    supports_json_mode: bool = True
    max_tokens: int = 4096
    fallback: str | None = None        # Fallback model to try next.


MODEL_REGISTRY: dict[str, ModelConfig] = {
    "deepseek-v3.2": ModelConfig(
        provider="deepseek",
        model="deepseek/deepseek-v3.2",
        supports_streaming=True,
        supports_json_mode=True,
        max_tokens=8192,
        fallback=None,
    ),
    "deepseek-chat": ModelConfig(
        provider="deepseek",
        model="deepseek/deepseek-v3.2",
        supports_streaming=True,
        supports_json_mode=True,
        max_tokens=8192,
        fallback=None,
    ),
}

ROLE_MODEL_MAP: dict[str, str] = {
    "orchestrator": "deepseek-v3.2",
    "manager": "deepseek-v3.2",
    "outline": "deepseek-v3.2",
    "researcher": "deepseek-v3.2",
    "writer": "deepseek-v3.2",
    "reviewer": "deepseek-v3.2",
    "consistency": "deepseek-v3.2",
}


# ---------------------------------------------------------------------------
# Retryable API errors
# ---------------------------------------------------------------------------

_RETRYABLE = (APIConnectionError, APIStatusError, RateLimitError, asyncio.TimeoutError)


# ---------------------------------------------------------------------------
# Abstract Base Class
# ---------------------------------------------------------------------------

class BaseLLMClient(ABC):
    """Abstract interface shared by the real client and test doubles."""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        role: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.3,
        max_retries: int | None = None,
        fallback_models: list[str] | None = None,
    ) -> str:
        """Run a standard chat completion."""

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        role: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.3,
        max_retries: int | None = None,
        fallback_models: list[str] | None = None,
    ) -> AsyncIterator[str]:
        """Stream chat completion chunks."""
        raise NotImplementedError
        yield  # noqa: unreachable

    @abstractmethod
    async def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        role: str | None = None,
        schema: type | None = None,
        max_tokens: int | None = None,
        max_retries: int | None = None,
        fallback_models: list[str] | None = None,
    ) -> dict:
        """Return structured JSON and optionally validate it against a schema."""

    @abstractmethod
    async def chat_with_tools(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        *,
        model: str | None = None,
        role: str | None = None,
        max_tokens: int | None = None,
        max_retries: int | None = None,
        fallback_models: list[str] | None = None,
    ) -> dict:
        """Run a tool-capable chat request."""

    @abstractmethod
    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        """Embed texts in batches."""


# ---------------------------------------------------------------------------
# Real Implementation
# ---------------------------------------------------------------------------

class LLMClient(BaseLLMClient):
    """Real LLM client with lazy provider construction and retry logic."""

    def __init__(self, tracker: Any = None) -> None:
        self._clients: dict[str, AsyncOpenAI] = {}
        self._tracker = tracker  # Optional TokenTracker
        self._allow_build_clients = True

    @staticmethod
    def _is_placeholder_key(value: str) -> bool:
        normalized = value.strip().lower()
        if not normalized:
            return True
        return normalized in {"sk-xxx", "your-api-key", "placeholder", "changeme"}

    @staticmethod
    def _resolve_http_proxy() -> str | None:
        """Use explicit HTTP(S) proxy only; ignore SOCKS-style ALL_PROXY."""
        for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
            value = str(os.getenv(key, "")).strip()
            if not value:
                continue
            lower = value.lower()
            if lower.startswith("http://") or lower.startswith("https://"):
                return value
        return None

    def _build_client(self, provider: str) -> AsyncOpenAI:
        request_timeout = max(5, int(getattr(settings, "llm_request_timeout_seconds", 120)))
        proxy_url = self._resolve_http_proxy()
        http_client = httpx.AsyncClient(
            timeout=request_timeout,
            trust_env=False,
            proxy=proxy_url,
        )

        openrouter_key = str(getattr(settings, "openrouter_api_key", "") or "").strip()
        openrouter_base = str(getattr(settings, "openrouter_base_url", "") or "").strip()
        if (
            openrouter_key
            and openrouter_base
            and not self._is_placeholder_key(openrouter_key)
        ):
            return AsyncOpenAI(
                api_key=openrouter_key,
                base_url=openrouter_base,
                timeout=request_timeout,
                http_client=http_client,
            )

        if provider == "openai":
            if self._is_placeholder_key(settings.openai_api_key):
                raise LLMUnavailableError(
                    "Provider 'openai' not configured (missing API key)"
                )
            return AsyncOpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
                timeout=request_timeout,
                http_client=http_client,
            )
        if provider == "deepseek":
            if self._is_placeholder_key(settings.deepseek_api_key):
                raise LLMUnavailableError(
                    "Provider 'deepseek' not configured (missing API key)"
                )
            return AsyncOpenAI(
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
                timeout=request_timeout,
                http_client=http_client,
            )
        raise LLMUnavailableError(f"Provider '{provider}' not configured")

    # -- Model resolution ---------------------------------------------------

    def _resolve_model(self, model: str | None, role: str | None) -> str:
        """Resolve model in priority order: explicit model, role mapping, default."""
        if model:
            return model
        if role and role in ROLE_MODEL_MAP:
            return ROLE_MODEL_MAP[role]
        return settings.default_model

    def _get_client(self, provider: str) -> AsyncOpenAI:
        clients = getattr(self, "_clients", {})
        client = clients.get(provider)
        if client is not None:
            return client
        if not getattr(self, "_allow_build_clients", False):
            raise LLMUnavailableError(f"Provider '{provider}' not configured")
        client = self._build_client(provider)
        clients[provider] = client
        self._clients = clients
        return client

    # -- Usage logging ------------------------------------------------------

    def _log_usage(self, model: str, usage: Any, role: str | None = None) -> None:
        if not usage:
            return
        if isinstance(usage, dict):
            prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
            completion_tokens = int(usage.get("completion_tokens", 0) or 0)
            total_tokens = int(
                usage.get("total_tokens", prompt_tokens + completion_tokens) or 0
            )
            prompt_details = usage.get("prompt_tokens_details") or {}
            cached_tokens = int(prompt_details.get("cached_tokens", 0) or 0)
        else:
            prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
            completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
            total_tokens = int(getattr(usage, "total_tokens", 0) or 0)
            cached_tokens = 0
            if hasattr(usage, "prompt_tokens_details") and usage.prompt_tokens_details:
                cached_tokens = getattr(usage.prompt_tokens_details, "cached_tokens", 0) or 0

        logger.bind(
            model=model,
            role=role or "",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cached_tokens=cached_tokens,
        ).info("LLM usage")

        if self._tracker:
            self._tracker.record(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cached_tokens=cached_tokens,
                role=role,
            )

    @staticmethod
    def _extract_usage(resp: Any) -> Any:
        if isinstance(resp, dict):
            return resp.get("usage")
        return getattr(resp, "usage", None)

    @staticmethod
    def _extract_first_choice(resp: Any) -> Any | None:
        if isinstance(resp, dict):
            choices = resp.get("choices")
        else:
            choices = getattr(resp, "choices", None)
        if not choices:
            return None
        try:
            return choices[0]
        except Exception:
            return None

    @classmethod
    def _extract_message(cls, resp: Any) -> Any | None:
        choice = cls._extract_first_choice(resp)
        if choice is None:
            return None
        if isinstance(choice, dict):
            return choice.get("message")
        return getattr(choice, "message", None)

    @staticmethod
    def _extract_content_from_message(message: Any) -> str | None:
        if message is None:
            return None
        if isinstance(message, dict):
            content = message.get("content")
        else:
            content = getattr(message, "content", None)

        if isinstance(content, str):
            return content
        if isinstance(content, list):
            # Some gateways may return content parts instead of a plain string.
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
            return "".join(parts)
        return None

    @classmethod
    def _extract_text_content(cls, resp: Any) -> str:
        if isinstance(resp, str):
            return resp
        if isinstance(resp, dict):
            message = cls._extract_message(resp)
            content = cls._extract_content_from_message(message)
            if content is not None:
                return content
            if isinstance(resp.get("content"), str):
                return resp["content"]
            return ""

        message = cls._extract_message(resp)
        content = cls._extract_content_from_message(message)
        if content is not None:
            return content
        fallback_content = getattr(resp, "content", None)
        if isinstance(fallback_content, str):
            return fallback_content
        return ""

    @staticmethod
    def _is_gateway_block_payload(content: str) -> bool:
        text = (content or "").strip()
        if not text:
            return False

        lowered = text.lower()
        compact = lowered.replace(" ", "")

        if compact.startswith("<!doctypehtml"):
            return True
        if 'name="aliyun_waf_aa"' in lowered:
            return True

        html_like = compact.startswith("<html") or "<html" in compact
        challenge_markers = (
            "captcha",
            "cloudflare",
            "just a moment",
            "security check",
            "waf",
            "访问验证",
            "人机验证",
        )
        return html_like and any(marker in lowered for marker in challenge_markers)

    @classmethod
    def _assert_clean_model_output(
        cls,
        *,
        content: str,
        model: str,
        role: str | None,
    ) -> None:
        if cls._is_gateway_block_payload(content):
            raise LLMUnavailableError(
                f"Model '{model}' returned gateway/WAF challenge payload (role={role or 'n/a'})"
            )

    @staticmethod
    def _parse_json_content(content: str) -> dict:
        text = (content or "").strip()
        if not text:
            return {}

        candidates: list[str] = [text]

        fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text, re.IGNORECASE)
        if fenced:
            candidates.append(fenced.group(1).strip())

        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace != -1 and first_brace < last_brace:
            candidates.append(text[first_brace:last_brace + 1].strip())

        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue

        raise json.JSONDecodeError("No valid JSON object found", text, 0)

    # -- Retry and fallback core -------------------------------------------

    async def _call_with_retry(
        self,
        model_name: str,
        call_fn: Any,
        *,
        allow_fallback: bool = True,
        max_retries: int | None = None,
        fallback_models: list[str] | None = None,
    ) -> Any:
        """Wrap an LLM call with retries and optional fallback models."""
        config = MODEL_REGISTRY.get(model_name)
        if not config:
            raise ValueError(f"Unknown model: {model_name}")

        max_attempts = self._normalize_max_attempts(max_retries)

        # Try the primary model first.
        result, error = await self._try_model(
            config, call_fn, max_attempts=max_attempts
        )
        if error is None:
            return result

        tried_chain = [model_name]

        # If the primary model fails, walk the fallback chain.
        if allow_fallback:
            for fb_model in self._resolve_fallback_chain(
                model_name=model_name,
                default_fallback=config.fallback,
                fallback_models=fallback_models,
            ):
                fb_config = MODEL_REGISTRY.get(fb_model)
                if not fb_config:
                    logger.warning(
                        "Skipping unknown fallback model '{}' for base model '{}'",
                        fb_model,
                        model_name,
                    )
                    continue

                logger.warning("Falling back: {} -> {}", tried_chain[-1], fb_model)
                tried_chain.append(fb_model)
                result, fb_error = await self._try_model(
                    fb_config, call_fn, max_attempts=max_attempts
                )
                if fb_error is None:
                    return result
                error = fb_error

        raise LLMUnavailableError(
            f"All models unavailable (tried {' -> '.join(tried_chain)}): {error}"
        )

    def _normalize_max_attempts(self, max_retries: int | None) -> int:
        if max_retries is None:
            return settings.llm_max_retries
        if max_retries <= 0:
            return 1
        return max_retries

    def _resolve_fallback_chain(
        self,
        *,
        model_name: str,
        default_fallback: str | None,
        fallback_models: list[str] | None,
    ) -> list[str]:
        if fallback_models:
            chain = [
                item.strip()
                for item in fallback_models
                if isinstance(item, str) and item.strip()
            ]
        elif default_fallback:
            chain = [default_fallback]
        else:
            chain = []

        deduped: list[str] = []
        for candidate in chain:
            if candidate == model_name:
                continue
            if candidate in deduped:
                continue
            deduped.append(candidate)
        return deduped

    async def _retry_async(
        self,
        operation: Any,
        *,
        label: str,
        max_attempts: int,
    ) -> Any:
        last_error: Exception | None = None
        for attempt in range(max_attempts):
            try:
                request_timeout = max(5, int(getattr(settings, "llm_request_timeout_seconds", 120)))
                return await asyncio.wait_for(operation(), timeout=request_timeout)
            except _RETRYABLE as exc:
                delay = settings.llm_retry_base_delay * (2 ** attempt)
                logger.warning(
                    "{} failed (attempt={}/{}): {}",
                    label,
                    attempt + 1,
                    max_attempts,
                    exc,
                )
                if attempt < max_attempts - 1:
                    await asyncio.sleep(delay)
                last_error = exc
        raise LLMUnavailableError(f"{label} unavailable: {last_error}")

    async def _try_model(
        self,
        config: ModelConfig,
        call_fn: Any,
        *,
        max_attempts: int,
    ) -> tuple[Any, Exception | None]:
        """Try one model and return either a result or an error."""
        try:
            client = self._get_client(config.provider)
            result = await self._retry_async(
                lambda: call_fn(client, config),
                label=f"LLM call (model={config.model})",
                max_attempts=max_attempts,
            )
            return result, None
        except LLMUnavailableError as exc:
            return None, exc

    # -- Public API ---------------------------------------------------------

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        role: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.3,
        max_retries: int | None = None,
        fallback_models: list[str] | None = None,
    ) -> str:
        model_name = self._resolve_model(model, role)

        async def _call(client: AsyncOpenAI, config: ModelConfig) -> str:
            resp = await client.chat.completions.create(
                model=config.model,
                messages=messages,
                max_tokens=max_tokens or config.max_tokens,
                temperature=temperature,
            )
            self._log_usage(config.model, self._extract_usage(resp), role)
            content = self._extract_text_content(resp)
            self._assert_clean_model_output(
                content=content,
                model=config.model,
                role=role,
            )
            return content

        return await self._call_with_retry(
            model_name,
            _call,
            max_retries=max_retries,
            fallback_models=fallback_models,
        )

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        role: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.3,
        max_retries: int | None = None,
        fallback_models: list[str] | None = None,
    ) -> AsyncIterator[str]:
        model_name = self._resolve_model(model, role)

        async def _create_stream(client: AsyncOpenAI, config: ModelConfig) -> Any:
            return await client.chat.completions.create(
                model=config.model,
                messages=messages,
                max_tokens=max_tokens or config.max_tokens,
                temperature=temperature,
                stream=True,
            )

        stream = await self._call_with_retry(
            model_name,
            _create_stream,
            max_retries=max_retries,
            fallback_models=fallback_models,
        )
        async for chunk in stream:
            if chunk.choices:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content

    async def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        role: str | None = None,
        schema: type | None = None,
        max_tokens: int | None = None,
        max_retries: int | None = None,
        fallback_models: list[str] | None = None,
    ) -> dict:
        model_name = self._resolve_model(model, role)

        async def _call(client: AsyncOpenAI, config: ModelConfig) -> dict:
            kwargs: dict[str, Any] = {
                "model": config.model,
                "messages": messages,
                "max_tokens": max_tokens or config.max_tokens,
                "temperature": 0.3,
            }
            if config.supports_json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            resp = await client.chat.completions.create(**kwargs)
            self._log_usage(config.model, self._extract_usage(resp), role)

            content = self._extract_text_content(resp) or "{}"
            self._assert_clean_model_output(
                content=content,
                model=config.model,
                role=role,
            )
            try:
                result = self._parse_json_content(content)
            except json.JSONDecodeError as exc:
                logger.bind(model=config.model, role=role or "").warning(
                    f"LLM returned invalid JSON: {exc}"
                )
                raise ValueError(f"LLM returned invalid JSON: {exc}") from exc

            if schema:
                try:
                    validated = schema.model_validate(result)
                    return validated.model_dump()
                except Exception as exc:
                    logger.bind(model=config.model, role=role or "").warning(
                        f"Schema validation failed: {exc}"
                    )
                    raise ValueError(f"Schema validation failed: {exc}") from exc

            return result

        return await self._call_with_retry(
            model_name,
            _call,
            max_retries=max_retries,
            fallback_models=fallback_models,
        )

    async def chat_with_tools(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        *,
        model: str | None = None,
        role: str | None = None,
        max_tokens: int | None = None,
        max_retries: int | None = None,
        fallback_models: list[str] | None = None,
    ) -> dict:
        model_name = self._resolve_model(model, role)

        async def _call(client: AsyncOpenAI, config: ModelConfig) -> dict:
            resp = await client.chat.completions.create(
                model=config.model,
                messages=messages,
                tools=tools,
                max_tokens=max_tokens or config.max_tokens,
                temperature=0.3,
            )
            self._log_usage(config.model, self._extract_usage(resp), role)

            message = self._extract_message(resp)
            if isinstance(message, dict):
                tool_calls = message.get("tool_calls") or []
            else:
                tool_calls = getattr(message, "tool_calls", None) or []
            if tool_calls:
                return {
                    "type": "tool_calls",
                    "tool_calls": [
                        {
                            "id": tc.get("id") if isinstance(tc, dict) else tc.id,
                            "function": {
                                "name": (
                                    tc.get("function", {}).get("name")
                                    if isinstance(tc, dict)
                                    else tc.function.name
                                ),
                                "arguments": (
                                    tc.get("function", {}).get("arguments")
                                    if isinstance(tc, dict)
                                    else tc.function.arguments
                                ),
                            },
                        }
                        for tc in tool_calls
                    ],
                }
            content = self._extract_text_content(resp)
            self._assert_clean_model_output(
                content=content,
                model=config.model,
                role=role,
            )
            return {"type": "text", "content": content}

        return await self._call_with_retry(
            model_name,
            _call,
            max_retries=max_retries,
            fallback_models=fallback_models,
        )

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        embed_model = model or settings.embedding_model
        try:
            client = self._get_client("openai")
        except LLMUnavailableError as exc:
            raise LLMUnavailableError(
                "OpenAI provider not configured for embeddings"
            ) from exc

        resp = await self._retry_async(
            lambda: client.embeddings.create(
                model=embed_model,
                input=texts,
                dimensions=settings.embedding_dimensions,
            ),
            label=f"Embedding call (model={embed_model})",
            max_attempts=settings.llm_max_retries,
        )
        logger.bind(
            model=embed_model,
            input_count=len(texts),
            total_tokens=resp.usage.total_tokens,
        ).info("Embedding usage")
        return [item.embedding for item in resp.data]


class DebugMockLLMClient(BaseLLMClient):
    """Built-in mock LLM for debug/test runtime mode without external APIs."""

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        role: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.3,
        max_retries: int | None = None,
        fallback_models: list[str] | None = None,
    ) -> str:
        if role == "outline":
            return "# 大纲\n## 第1章 引言\n## 第2章 核心概念\n## 第3章 总结"
        if role == "writer":
            return "这是一段模拟生成的章节内容，用于测试。" * 5
        if role == "reviewer":
            return "审查通过，评分85分。"
        if role == "consistency":
            return "一致性检查通过，无问题。"
        return "mock response"

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        role: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.3,
        max_retries: int | None = None,
        fallback_models: list[str] | None = None,
    ) -> AsyncIterator[str]:
        for chunk in ("这是", "一段", "流式", "输出", "测试。"):
            yield chunk

    async def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        role: str | None = None,
        schema: type | None = None,
        max_tokens: int | None = None,
        max_retries: int | None = None,
        fallback_models: list[str] | None = None,
    ) -> dict:
        if role == "orchestrator":
            return {
                "nodes": [
                    {"id": "n1", "title": "大纲生成", "role": "outline", "depends_on": []},
                    {"id": "n2", "title": "第1章撰写", "role": "writer", "depends_on": ["n1"]},
                    {"id": "n3", "title": "第2章撰写", "role": "writer", "depends_on": ["n1"]},
                ]
            }
        if role == "reviewer":
            return {
                "score": 85,
                "accuracy_score": 90,
                "coherence_score": 80,
                "style_score": 85,
                "feedback": "内容结构清晰，论述完整。",
                "pass": True,
            }
        return {"result": "mock"}

    async def chat_with_tools(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        *,
        model: str | None = None,
        role: str | None = None,
        max_tokens: int | None = None,
        max_retries: int | None = None,
        fallback_models: list[str] | None = None,
    ) -> dict:
        return {"type": "text", "content": "mock tool response"}

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        return [[0.1] * settings.embedding_dimensions for _ in texts]

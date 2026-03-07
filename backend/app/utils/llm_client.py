"""LLM统一适配层 — 模型配置注册表 + 多provider适配 + 重试降级"""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    AsyncOpenAI,
    RateLimitError,
)

from app.config import settings
from app.utils.logger import logger


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class LLMUnavailableError(Exception):
    """所有模型均不可用（主模型+降级模型都失败）"""


# ---------------------------------------------------------------------------
# Model Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ModelConfig:
    """单个模型的配置"""
    provider: str                      # "openai" | "deepseek"
    model: str                         # 模型ID（如 "gpt-4o"）
    supports_streaming: bool = True
    supports_json_mode: bool = True
    max_tokens: int = 4096
    fallback: str | None = None        # 不可用时降级到的模型名


MODEL_REGISTRY: dict[str, ModelConfig] = {
    "gpt-4o": ModelConfig(
        provider="openai",
        model="gpt-4o",
        supports_streaming=True,
        supports_json_mode=True,
        max_tokens=4096,
        fallback="deepseek-chat",
    ),
    "deepseek-chat": ModelConfig(
        provider="deepseek",
        model="deepseek-chat",
        supports_streaming=True,
        supports_json_mode=True,
        max_tokens=8192,
        fallback="gpt-4o",
    ),
}

ROLE_MODEL_MAP: dict[str, str] = {
    "orchestrator": "gpt-4o",
    "manager": "deepseek-chat",
    "outline": "gpt-4o",
    "writer": "deepseek-chat",
    "reviewer": "gpt-4o",
    "consistency": "gpt-4o",
}


# ---------------------------------------------------------------------------
# Retryable API errors
# ---------------------------------------------------------------------------

_RETRYABLE = (APIConnectionError, APIStatusError, RateLimitError)


# ---------------------------------------------------------------------------
# Abstract Base Class
# ---------------------------------------------------------------------------

class BaseLLMClient(ABC):
    """LLM客户端抽象基类 — 真实实现与测试Mock共用接口"""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        role: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> str:
        """普通对话，按role自动选模型，失败自动降级"""

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        role: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        """流式输出，yield每个token chunk"""
        # Make abstract async generators work: unreachable yield
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
    ) -> dict:
        """结构化JSON输出，schema为Pydantic模型类时自动校验"""

    @abstractmethod
    async def chat_with_tools(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        *,
        model: str | None = None,
        role: str | None = None,
        max_tokens: int | None = None,
    ) -> dict:
        """工具调用（返回tool_calls列表或最终文本）"""

    @abstractmethod
    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        """文本嵌入，支持批量"""


# ---------------------------------------------------------------------------
# Real Implementation
# ---------------------------------------------------------------------------

class LLMClient(BaseLLMClient):
    """真实LLM客户端 — OpenAI/DeepSeek双provider，重试+降级+Token追踪"""

    def __init__(self, tracker: Any = None) -> None:
        self._clients: dict[str, AsyncOpenAI] = {}
        self._tracker = tracker  # Optional TokenTracker
        self._init_clients()

    def _init_clients(self) -> None:
        if settings.openai_api_key:
            self._clients["openai"] = AsyncOpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
            )
        if settings.deepseek_api_key:
            self._clients["deepseek"] = AsyncOpenAI(
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
            )

    # -- Model resolution ---------------------------------------------------

    def _resolve_model(self, model: str | None, role: str | None) -> str:
        """优先显式指定 > 角色映射 > 默认模型"""
        if model:
            return model
        if role and role in ROLE_MODEL_MAP:
            return ROLE_MODEL_MAP[role]
        return settings.default_model

    def _get_client(self, provider: str) -> AsyncOpenAI:
        client = self._clients.get(provider)
        if not client:
            raise LLMUnavailableError(
                f"Provider '{provider}' not configured (missing API key)"
            )
        return client

    # -- Usage logging -------------------------------------------------------

    def _log_usage(
        self, model: str, usage: Any, role: str | None = None
    ) -> None:
        if not usage:
            return
        cached_tokens = 0
        if hasattr(usage, "prompt_tokens_details") and usage.prompt_tokens_details:
            cached_tokens = getattr(
                usage.prompt_tokens_details, "cached_tokens", 0
            ) or 0

        logger.bind(
            model=model, role=role or "",
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            cached_tokens=cached_tokens,
        ).info("LLM usage")

        if self._tracker:
            self._tracker.record(
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                cached_tokens=cached_tokens,
                role=role,
            )

    # -- Retry + fallback core -----------------------------------------------

    async def _call_with_retry(
        self,
        model_name: str,
        call_fn: Any,
        *,
        allow_fallback: bool = True,
    ) -> Any:
        """带指数退避重试和自动降级的调用包装"""
        config = MODEL_REGISTRY.get(model_name)
        if not config:
            raise ValueError(f"Unknown model: {model_name}")

        # 尝试主模型
        result, error = await self._try_model(config, call_fn)
        if error is None:
            return result

        # 主模型失败，尝试降级
        if allow_fallback and config.fallback:
            fb_config = MODEL_REGISTRY.get(config.fallback)
            if fb_config:
                logger.warning(
                    f"Falling back: {model_name} → {config.fallback}"
                )
                result, fb_error = await self._try_model(fb_config, call_fn)
                if fb_error is None:
                    return result
                error = fb_error

        raise LLMUnavailableError(
            f"All models unavailable (tried {model_name}"
            + (f" → {config.fallback}" if config.fallback else "")
            + f"): {error}"
        )

    async def _try_model(
        self, config: ModelConfig, call_fn: Any
    ) -> tuple[Any, Exception | None]:
        """尝试用指定模型调用，返回 (result, None) 成功 或 (None, error) 失败"""
        last_error: Exception | None = None
        for attempt in range(settings.llm_max_retries):
            try:
                client = self._get_client(config.provider)
                result = await call_fn(client, config)
                return result, None
            except LLMUnavailableError as e:
                return None, e
            except _RETRYABLE as e:
                delay = settings.llm_retry_base_delay * (2 ** attempt)
                logger.warning(
                    f"LLM call failed (model={config.model}, "
                    f"attempt={attempt + 1}/{settings.llm_max_retries}): {e}",
                )
                if attempt < settings.llm_max_retries - 1:
                    await asyncio.sleep(delay)
                last_error = e
        return None, last_error

    # -- Public API ----------------------------------------------------------

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        role: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> str:
        model_name = self._resolve_model(model, role)

        async def _call(client: AsyncOpenAI, config: ModelConfig) -> str:
            resp = await client.chat.completions.create(
                model=config.model,
                messages=messages,
                max_tokens=max_tokens or config.max_tokens,
                temperature=temperature,
            )
            self._log_usage(config.model, resp.usage, role)
            return resp.choices[0].message.content or ""

        return await self._call_with_retry(model_name, _call)

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        role: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        model_name = self._resolve_model(model, role)

        async def _create_stream(
            client: AsyncOpenAI, config: ModelConfig
        ) -> Any:
            return await client.chat.completions.create(
                model=config.model,
                messages=messages,
                max_tokens=max_tokens or config.max_tokens,
                temperature=temperature,
                stream=True,
            )

        stream = await self._call_with_retry(model_name, _create_stream)
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
            self._log_usage(config.model, resp.usage, role)

            content = resp.choices[0].message.content or "{}"
            try:
                result = json.loads(content)
            except json.JSONDecodeError as e:
                logger.bind(model=config.model, role=role or "").warning(
                    f"LLM returned invalid JSON: {e}"
                )
                raise ValueError(f"LLM returned invalid JSON: {e}") from e

            if schema:
                try:
                    validated = schema.model_validate(result)
                    return validated.model_dump()
                except Exception as e:
                    logger.bind(model=config.model, role=role or "").warning(
                        f"Schema validation failed: {e}"
                    )
                    raise ValueError(f"Schema validation failed: {e}") from e

            return result

        return await self._call_with_retry(model_name, _call)

    async def chat_with_tools(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        *,
        model: str | None = None,
        role: str | None = None,
        max_tokens: int | None = None,
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
            self._log_usage(config.model, resp.usage, role)

            message = resp.choices[0].message
            if message.tool_calls:
                return {
                    "type": "tool_calls",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in message.tool_calls
                    ],
                }
            return {"type": "text", "content": message.content or ""}

        return await self._call_with_retry(model_name, _call)

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        embed_model = model or settings.embedding_model

        if "openai" not in self._clients:
            raise LLMUnavailableError(
                "OpenAI provider not configured for embeddings"
            )

        client = self._clients["openai"]
        last_error: Exception | None = None
        for attempt in range(settings.llm_max_retries):
            try:
                resp = await client.embeddings.create(
                    model=embed_model,
                    input=texts,
                    dimensions=settings.embedding_dimensions,
                )
                logger.bind(
                    model=embed_model,
                    input_count=len(texts),
                    total_tokens=resp.usage.total_tokens,
                ).info("Embedding usage")
                return [item.embedding for item in resp.data]
            except _RETRYABLE as e:
                delay = settings.llm_retry_base_delay * (2 ** attempt)
                logger.warning(
                    f"Embed call failed (attempt={attempt + 1}): {e}"
                )
                if attempt < settings.llm_max_retries - 1:
                    await asyncio.sleep(delay)
                last_error = e

        raise LLMUnavailableError(f"Embedding unavailable: {last_error}")

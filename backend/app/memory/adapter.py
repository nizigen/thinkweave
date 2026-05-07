"""Project-owned adapter around memory backends with cognee fallback."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import inspect
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.config import settings
from app.memory.config import MemoryConfig, get_memory_config
from app.utils.logger import logger


@dataclass
class _InMemoryBackend:
    """Lightweight in-process fallback backend."""

    _store: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    async def add(
        self,
        content: str,
        *,
        namespace: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ns = str(namespace or "")
        bucket = self._store.setdefault(ns, [])
        item = {
            "id": f"inmem-{len(bucket) + 1}",
            "content": content,
            "metadata": dict(metadata or {}),
        }
        bucket.append(item)
        return {"id": item["id"]}

    async def search(
        self,
        query: str,
        *,
        namespace: str | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        ns = str(namespace or "")
        rows = list(self._store.get(ns, []))
        q = str(query or "").strip().lower()
        if not q:
            return rows[: max(0, int(top_k))]

        matched = [
            row
            for row in rows
            if q in str(row.get("content", "")).lower()
        ]
        return matched[: max(0, int(top_k))]

    async def cognify(
        self,
        content: str,
        *,
        namespace: str | None = None,
    ) -> dict[str, Any]:
        text = str(content or "").strip()
        if not text:
            return {}
        return {
            "entities": [
                {
                    "name": text[:48],
                    "source": str(namespace or ""),
                }
            ]
        }


class MemoryAdapter:
    """Adapter layer for task-scoped memory operations.

    Disabled mode preserves the v1 no-op behavior. Enabled mode must use a
    supported cognee backend matrix and surface provider failures explicitly.
    """

    def __init__(
        self,
        *,
        config: MemoryConfig | None = None,
        cognee_client: Any | None = None,
    ) -> None:
        self.config = config or get_memory_config()
        self._cognee_client = cognee_client
        self._fallback_backend = _InMemoryBackend()
        self._degraded = False

    @property
    def enabled(self) -> bool:
        return self.config.memory_enabled

    @property
    def degraded(self) -> bool:
        return self._degraded

    def ensure_supported_backend_matrix(self) -> None:
        graph = self.config.graph_database_provider
        vector = self.config.vector_database_provider

        supported_graph = {"kuzu", "falkor", "neo4j_aura_dev"}
        supported_vector = {"lancedb", "falkor", "pgvector"}

        if graph not in supported_graph or vector not in supported_vector:
            raise RuntimeError(
                f"Unsupported cognee backend combination: "
                f"graph={graph}, vector={vector}"
            )

    def _require_client(self) -> Any:
        client = self._resolve_client()
        if client is None:
            raise RuntimeError("cognee client unavailable while memory is enabled")
        return client

    def _validate_runtime_config(self) -> None:
        if self.config.enable_backend_access_control:
            raise RuntimeError(
                "enable_backend_access_control must be configured before process "
                "start; MemoryAdapter does not mutate provider runtime config"
            )

    @staticmethod
    def _is_placeholder_secret(value: str | None) -> bool:
        normalized = str(value or "").strip().lower()
        if not normalized:
            return True
        return normalized in {"sk-xxx", "your-api-key", "placeholder", "changeme"}

    @staticmethod
    def _to_bool_text(value: bool) -> str:
        return "true" if value else "false"

    @staticmethod
    def _resolve_cognee_model(model_name: str | None) -> str:
        chosen = str(model_name or "").strip()
        if not chosen:
            return "deepseek/deepseek-v3.2"
        try:
            from app.utils.llm_client import MODEL_REGISTRY

            entry = MODEL_REGISTRY.get(chosen)
            if entry and entry.model:
                return str(entry.model)
        except Exception:
            pass
        return chosen if "/" in chosen else f"deepseek/{chosen}"

    def _provider_timeout_seconds(self) -> float:
        try:
            timeout = float(getattr(self.config, "memory_provider_timeout_seconds", 15.0))
        except Exception:
            timeout = 15.0
        return max(1.0, timeout)

    def _prime_cognee_env(self) -> None:
        # Cognee reads process env/.env relative to current working directory.
        # Bridge critical values from backend settings to avoid CWD-dependent drift.
        backend_root = Path(__file__).resolve().parents[2]
        os.environ.setdefault("COGNEE_LOGS_DIR", str(backend_root / "logs" / "cognee"))
        os.environ.setdefault("SYSTEM_ROOT_DIRECTORY", str(backend_root / ".cognee_system"))
        os.environ.setdefault("DATA_ROOT_DIRECTORY", str(backend_root / ".cognee_data"))
        os.environ.setdefault("CACHE_ROOT_DIRECTORY", str(backend_root / ".cognee_cache"))

        os.environ.setdefault("GRAPH_DATABASE_PROVIDER", self.config.graph_database_provider)
        os.environ.setdefault("VECTOR_DB_PROVIDER", self.config.vector_database_provider)
        os.environ.setdefault(
            "VECTOR_DATASET_DATABASE_HANDLER",
            self.config.vector_database_provider,
        )
        os.environ.setdefault(
            "ENABLE_BACKEND_ACCESS_CONTROL",
            self._to_bool_text(self.config.enable_backend_access_control),
        )

        postgres_url = str(getattr(settings, "postgres_url", "") or "").strip()
        if postgres_url:
            parsed = urlparse(postgres_url.replace("+asyncpg", ""))
            os.environ.setdefault("DB_PROVIDER", "postgres")
            if parsed.hostname:
                os.environ.setdefault("DB_HOST", parsed.hostname)
                os.environ.setdefault("VECTOR_DB_HOST", parsed.hostname)
            if parsed.port:
                os.environ.setdefault("DB_PORT", str(parsed.port))
                os.environ.setdefault("VECTOR_DB_PORT", str(parsed.port))
            if parsed.username:
                os.environ.setdefault("DB_USERNAME", parsed.username)
                os.environ.setdefault("VECTOR_DB_USERNAME", parsed.username)
            if parsed.password:
                os.environ.setdefault("DB_PASSWORD", parsed.password)
                os.environ.setdefault("VECTOR_DB_PASSWORD", parsed.password)
            db_name = parsed.path.lstrip("/")
            if db_name:
                os.environ.setdefault("DB_NAME", db_name)
                os.environ.setdefault("VECTOR_DB_NAME", db_name)

        chosen_model = self._resolve_cognee_model(getattr(settings, "default_model", ""))

        openrouter_key = str(getattr(settings, "openrouter_api_key", "") or "").strip()
        openrouter_base = str(getattr(settings, "openrouter_base_url", "") or "").strip()
        if not self._is_placeholder_secret(openrouter_key):
            os.environ.setdefault("LLM_PROVIDER", "openai")
            os.environ.setdefault("LLM_MODEL", chosen_model)
            if openrouter_base:
                os.environ.setdefault("LLM_ENDPOINT", openrouter_base)
            os.environ.setdefault("LLM_API_KEY", openrouter_key)
            return

        openai_key = str(getattr(settings, "openai_api_key", "") or "").strip()
        openai_base = str(getattr(settings, "openai_base_url", "") or "").strip()
        if not self._is_placeholder_secret(openai_key):
            os.environ.setdefault("LLM_PROVIDER", "openai")
            os.environ.setdefault("LLM_MODEL", chosen_model)
            if openai_base:
                os.environ.setdefault("LLM_ENDPOINT", openai_base)
            os.environ.setdefault("LLM_API_KEY", openai_key)
            return

        deepseek_key = str(getattr(settings, "deepseek_api_key", "") or "").strip()
        deepseek_base = str(getattr(settings, "deepseek_base_url", "") or "").strip()
        if not self._is_placeholder_secret(deepseek_key):
            os.environ.setdefault("LLM_PROVIDER", "openai")
            os.environ.setdefault("LLM_MODEL", "deepseek/deepseek-v3.2")
            if deepseek_base:
                os.environ.setdefault("LLM_ENDPOINT", deepseek_base)
            os.environ.setdefault("LLM_API_KEY", deepseek_key)

    def _resolve_client(self) -> Any | None:
        if not self.enabled:
            return None
        if self._cognee_client is not None:
            return self._cognee_client

        self._prime_cognee_env()
        self.ensure_supported_backend_matrix()
        self._validate_runtime_config()

        try:
            import cognee  # type: ignore

            self._cognee_client = cognee
            return self._cognee_client
        except Exception as exc:  # pragma: no cover
            logger.warning(f"Memory provider unavailable in enabled mode: {exc}")
            return None

    def _degrade_to_fallback(self, *, reason: str) -> None:
        if not self._degraded:
            logger.warning("Memory adapter degraded to fallback backend: {}", reason)
        self._degraded = True

    @staticmethod
    def _is_empty_search_error(exc: Exception) -> bool:
        message = str(exc or "").lower()
        empty_markers = (
            "nodataerror",
            "no data found in the system",
            "datasetnotfounderror",
            "no datasets found",
            "collection not found",
            "empty knowledge graph",
        )
        return any(marker in message for marker in empty_markers)

    @staticmethod
    def _namespace_to_dataset(namespace: str | None) -> str:
        raw = str(namespace or "").strip()
        if not raw:
            return "main_dataset"
        safe = []
        for ch in raw:
            if ch.isalnum() or ch in {"-", "_"}:
                safe.append(ch)
            else:
                safe.append("_")
        dataset = "".join(safe).strip("_")
        return dataset or "main_dataset"

    @staticmethod
    def _normalize_dataset_name(dataset: str) -> str:
        return MemoryAdapter._namespace_to_dataset(dataset)

    @staticmethod
    def _supports_param(func: Any, name: str) -> bool:
        try:
            return name in inspect.signature(func).parameters
        except Exception:
            return False

    async def _client_add(
        self,
        client: Any,
        content: str,
        *,
        namespace: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        # Prefer dataset-aware API when available (cognee >=1.0).
        # Fallback to legacy namespace mode for older clients/tests.
        if not self._supports_param(client.add, "dataset_name"):
            return await client.add(
                content,
                namespace=namespace,
                metadata=metadata or {},
            )
        dataset_name = self._namespace_to_dataset(namespace)
        return await client.add(
            content,
            dataset_name=dataset_name,
            metadata=metadata or {},
        )

    async def _client_search(
        self,
        client: Any,
        query: str,
        *,
        namespace: str | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        # Prefer dataset-aware API when available (cognee >=1.0).
        # Fallback to legacy query/namespace mode for older clients/tests.
        if not self._supports_param(client.search, "query_text"):
            rows = await client.search(query, namespace=namespace, top_k=top_k)
            return rows or []

        dataset_name = self._namespace_to_dataset(namespace)
        search_kwargs: dict[str, Any] = {
            "query_text": query,
            "datasets": [dataset_name],
            "top_k": top_k,
        }
        if hasattr(client, "SearchType"):
            try:
                search_kwargs["query_type"] = client.SearchType.CHUNKS
            except Exception:
                pass
        rows = await client.search(**search_kwargs)
        normalized: list[dict[str, Any]] = []
        for row in rows or []:
            if isinstance(row, dict):
                normalized.append(row)
                continue
            text = getattr(row, "text", None)
            if text is None:
                text = getattr(row, "search_result", None)
            if text is None:
                text = str(row)
            normalized.append({"content": str(text)})
        return normalized

    async def _client_cognify(
        self,
        client: Any,
        content: str,
        *,
        namespace: str | None = None,
    ) -> dict[str, Any]:
        # Legacy API accepts content text, while cognee>=1.0 expects datasets.
        if self._supports_param(client.cognify, "content"):
            data = await client.cognify(content, namespace=namespace)
            return data or {}

        dataset_name = self._namespace_to_dataset(namespace)
        await client.cognify(datasets=[dataset_name])
        return {"dataset": dataset_name}

    async def add(
        self,
        content: str,
        *,
        namespace: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any | None:
        if not self.enabled:
            return None
        client = self._resolve_client()
        if client is None:
            self._degrade_to_fallback(reason="cognee client unavailable")
            return await self._fallback_backend.add(
                content,
                namespace=namespace,
                metadata=metadata or {},
            )

        try:
            return await asyncio.wait_for(
                self._client_add(
                    client,
                    content,
                    namespace=namespace,
                    metadata=metadata or {},
                ),
                timeout=self._provider_timeout_seconds(),
            )
        except Exception as exc:  # pragma: no cover
            logger.warning(f"Memory add failed in enabled mode: {exc}")
            self._degrade_to_fallback(reason=f"add failed: {exc}")
            return await self._fallback_backend.add(
                content,
                namespace=namespace,
                metadata=metadata or {},
            )

    async def search(
        self,
        query: str,
        *,
        namespace: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        client = self._resolve_client()
        if client is None:
            self._degrade_to_fallback(reason="cognee client unavailable")
            return await self._fallback_backend.search(
                query,
                namespace=namespace,
                top_k=limit,
            )

        try:
            rows = await asyncio.wait_for(
                self._client_search(
                    client,
                    query,
                    namespace=namespace,
                    top_k=limit,
                ),
                timeout=self._provider_timeout_seconds(),
            )
            return rows or []
        except Exception as exc:  # pragma: no cover
            if self._is_empty_search_error(exc):
                # add() is ingestion-only in cognee v1; if chunks/graph are not
                # built yet, trigger one cognify pass and retry once.
                try:
                    await asyncio.wait_for(
                        self._client_cognify(
                            client,
                            query,
                            namespace=namespace,
                        ),
                        timeout=self._provider_timeout_seconds(),
                    )
                    rows = await asyncio.wait_for(
                        self._client_search(
                            client,
                            query,
                            namespace=namespace,
                            top_k=limit,
                        ),
                        timeout=self._provider_timeout_seconds(),
                    )
                    if rows:
                        logger.info(
                            "Memory search recovered after cognify, namespace={} query={}",
                            str(namespace or ""),
                            str(query or "")[:80],
                        )
                        return rows
                except Exception:
                    pass
                logger.info(
                    "Memory search returned empty corpus state, namespace={} query={}",
                    str(namespace or ""),
                    str(query or "")[:80],
                )
                return []
            logger.warning(f"Memory search failed in enabled mode: {exc}")
            self._degrade_to_fallback(reason=f"search failed: {exc}")
            return await self._fallback_backend.search(
                query,
                namespace=namespace,
                top_k=limit,
            )

    async def cognify(
        self,
        content: str,
        *,
        namespace: str | None = None,
    ) -> dict[str, Any]:
        if not self.enabled:
            return {}
        client = self._resolve_client()
        if client is None:
            self._degrade_to_fallback(reason="cognee client unavailable")
            return await self._fallback_backend.cognify(
                content,
                namespace=namespace,
            )

        try:
            data = await asyncio.wait_for(
                self._client_cognify(
                    client,
                    content,
                    namespace=namespace,
                ),
                timeout=self._provider_timeout_seconds(),
            )
            return data or {}
        except Exception as exc:  # pragma: no cover
            logger.warning(f"Memory cognify failed in enabled mode: {exc}")
            self._degrade_to_fallback(reason=f"cognify failed: {exc}")
            return await self._fallback_backend.cognify(
                content,
                namespace=namespace,
            )

    async def forget_dataset(self, dataset_or_namespace: str) -> bool:
        if not self.enabled:
            return True

        name = self._normalize_dataset_name(dataset_or_namespace)
        client = self._resolve_client()
        if client is None:
            self._degrade_to_fallback(reason="cognee client unavailable")
            return False

        try:
            if hasattr(client, "forget"):
                await asyncio.wait_for(
                    client.forget(dataset=name),
                    timeout=self._provider_timeout_seconds(),
                )
                return True
            if hasattr(client, "datasets") and hasattr(client.datasets, "list_datasets"):
                datasets = await asyncio.wait_for(
                    client.datasets.list_datasets(),
                    timeout=self._provider_timeout_seconds(),
                )
                target_id = None
                for item in datasets or []:
                    if str(getattr(item, "name", "")).strip() == name:
                        target_id = getattr(item, "id", None)
                        break
                if target_id and hasattr(client.datasets, "delete_dataset"):
                    await asyncio.wait_for(
                        client.datasets.delete_dataset(target_id),
                        timeout=self._provider_timeout_seconds(),
                    )
                    return True
            return False
        except Exception as exc:  # pragma: no cover
            logger.warning(f"Memory forget dataset failed: {exc}")
            return False

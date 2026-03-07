"""Tests for LLM client — model resolution, MockLLMClient, TokenTracker integration."""

import pytest

from app.utils.llm_client import (
    MODEL_REGISTRY,
    ROLE_MODEL_MAP,
    BaseLLMClient,
    LLMClient,
    LLMUnavailableError,
    ModelConfig,
)
from tests.conftest import MockLLMClient


# ---------------------------------------------------------------------------
# ModelConfig & Registry
# ---------------------------------------------------------------------------


class TestModelConfig:
    def test_model_config_frozen(self):
        cfg = ModelConfig(provider="openai", model="gpt-4o")
        with pytest.raises(AttributeError):
            cfg.provider = "deepseek"  # type: ignore[misc]

    def test_registry_has_required_models(self):
        assert "gpt-4o" in MODEL_REGISTRY
        assert "deepseek-chat" in MODEL_REGISTRY

    def test_fallback_chain(self):
        gpt = MODEL_REGISTRY["gpt-4o"]
        ds = MODEL_REGISTRY["deepseek-chat"]
        assert gpt.fallback == "deepseek-chat"
        assert ds.fallback == "gpt-4o"

    def test_role_model_map_covers_all_roles(self):
        expected_roles = {
            "orchestrator", "manager", "outline",
            "writer", "reviewer", "consistency",
        }
        assert set(ROLE_MODEL_MAP.keys()) == expected_roles


# ---------------------------------------------------------------------------
# Model Resolution (via LLMClient internals)
# ---------------------------------------------------------------------------


class TestModelResolution:
    def setup_method(self):
        # Create LLMClient without API keys — we only test resolution
        self.client = LLMClient.__new__(LLMClient)
        self.client._clients = {}
        self.client._tracker = None

    def test_explicit_model_wins(self):
        assert self.client._resolve_model("gpt-4o", "writer") == "gpt-4o"

    def test_role_mapping(self):
        assert self.client._resolve_model(None, "writer") == "deepseek-chat"
        assert self.client._resolve_model(None, "orchestrator") == "gpt-4o"

    def test_fallback_to_default(self):
        result = self.client._resolve_model(None, None)
        assert result == "gpt-4o"  # settings.default_model

    def test_unknown_role_uses_default(self):
        result = self.client._resolve_model(None, "unknown_role")
        assert result == "gpt-4o"


# ---------------------------------------------------------------------------
# MockLLMClient
# ---------------------------------------------------------------------------


class TestMockLLMClient:
    @pytest.fixture
    def mock(self):
        return MockLLMClient()

    @pytest.mark.asyncio
    async def test_chat_returns_string(self, mock):
        result = await mock.chat(
            [{"role": "user", "content": "hello"}], role="writer"
        )
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_chat_role_responses(self, mock):
        outline = await mock.chat([], role="outline")
        assert "大纲" in outline or "#" in outline

        writer = await mock.chat([], role="writer")
        assert len(writer) > 50

    @pytest.mark.asyncio
    async def test_chat_stream(self, mock):
        chunks = []
        async for chunk in mock.chat_stream([], role="writer"):
            chunks.append(chunk)
        assert len(chunks) > 0
        assert "".join(chunks) == "这是一段流式输出测试。"

    @pytest.mark.asyncio
    async def test_chat_json_orchestrator(self, mock):
        result = await mock.chat_json([], role="orchestrator")
        assert "nodes" in result
        assert len(result["nodes"]) > 0

    @pytest.mark.asyncio
    async def test_chat_json_reviewer(self, mock):
        result = await mock.chat_json([], role="reviewer")
        assert "score" in result
        assert result["pass"] is True

    @pytest.mark.asyncio
    async def test_chat_with_tools(self, mock):
        result = await mock.chat_with_tools([], tools=[{"type": "function"}])
        assert result["type"] == "text"

    @pytest.mark.asyncio
    async def test_embed(self, mock):
        result = await mock.embed(["hello", "world"])
        assert len(result) == 2
        assert len(result[0]) == 1536

    @pytest.mark.asyncio
    async def test_call_log_records_calls(self, mock):
        await mock.chat([], role="writer")
        await mock.chat_json([], role="orchestrator")
        await mock.embed(["test"])
        assert len(mock.call_log) == 3
        assert mock.call_log[0]["method"] == "chat"
        assert mock.call_log[1]["method"] == "chat_json"
        assert mock.call_log[2]["method"] == "embed"


# ---------------------------------------------------------------------------
# BaseLLMClient ABC enforcement
# ---------------------------------------------------------------------------


class TestBaseLLMClientABC:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            BaseLLMClient()  # type: ignore[abstract]

    def test_mock_is_valid_subclass(self):
        mock = MockLLMClient()
        assert isinstance(mock, BaseLLMClient)


# ---------------------------------------------------------------------------
# LLMClient — error cases (no API keys configured)
# ---------------------------------------------------------------------------


class TestLLMClientErrors:
    @pytest.mark.asyncio
    async def test_no_provider_configured(self):
        client = LLMClient.__new__(LLMClient)
        client._clients = {}
        client._tracker = None

        with pytest.raises(LLMUnavailableError, match="not configured"):
            await client.chat([{"role": "user", "content": "hi"}])

    @pytest.mark.asyncio
    async def test_unknown_model_raises(self):
        client = LLMClient.__new__(LLMClient)
        client._clients = {}
        client._tracker = None

        with pytest.raises(ValueError, match="Unknown model"):
            await client.chat(
                [{"role": "user", "content": "hi"}],
                model="nonexistent-model",
            )

    @pytest.mark.asyncio
    async def test_embed_no_openai(self):
        client = LLMClient.__new__(LLMClient)
        client._clients = {}
        client._tracker = None

        with pytest.raises(LLMUnavailableError, match="OpenAI"):
            await client.embed(["test"])


# ---------------------------------------------------------------------------
# chat_json error handling
# ---------------------------------------------------------------------------


class TestChatJsonErrorHandling:
    """Tests for JSON parse and schema validation in chat_json."""

    @pytest.fixture
    def mock(self):
        return MockLLMClient()

    @pytest.mark.asyncio
    async def test_chat_json_returns_dict(self, mock):
        result = await mock.chat_json([], role="reviewer")
        assert isinstance(result, dict)
        assert "score" in result

    @pytest.mark.asyncio
    async def test_chat_json_default_response(self, mock):
        result = await mock.chat_json([], role="unknown")
        assert result == {"result": "mock"}

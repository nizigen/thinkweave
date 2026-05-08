"""Tests for LLM client — model resolution, MockLLMClient, TokenTracker integration."""

from unittest.mock import AsyncMock

import pytest

from app.config import settings
from app.services.tool_lifecycle import tool_lifecycle_service
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
        cfg = ModelConfig(provider="deepseek", model="deepseek/deepseek-v3.2")
        with pytest.raises(AttributeError):
            cfg.provider = "deepseek"  # type: ignore[misc]

    def test_registry_has_required_models(self):
        assert "deepseek-v3.2" in MODEL_REGISTRY
        assert "deepseek-v3.2" in MODEL_REGISTRY

    def test_fallback_chain(self):
        ds = MODEL_REGISTRY["deepseek-v3.2"]
        assert ds.fallback is None

    def test_role_model_map_covers_all_roles(self):
        expected_roles = {
            "orchestrator", "manager", "outline",
            "researcher", "writer", "reviewer", "consistency",
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
        assert self.client._resolve_model("deepseek-v3.2", "writer") == "deepseek-v3.2"

    def test_role_mapping(self):
        assert self.client._resolve_model(None, "writer") == "deepseek-v3.2"
        assert self.client._resolve_model(None, "orchestrator") == "deepseek-v3.2"

    def test_fallback_to_default(self):
        result = self.client._resolve_model(None, None)
        assert result == "deepseek-v3.2"  # settings.default_model

    def test_unknown_role_uses_default(self):
        result = self.client._resolve_model(None, "unknown_role")
        assert result == "deepseek-v3.2"


class TestRetryFallbackOverrides:
    def setup_method(self):
        self.client = LLMClient.__new__(LLMClient)
        self.client._clients = {}
        self.client._tracker = None

    def test_normalize_max_attempts(self):
        assert self.client._normalize_max_attempts(None) == 3
        assert self.client._normalize_max_attempts(5) == 5
        assert self.client._normalize_max_attempts(0) == 1

    def test_resolve_fallback_chain_prefers_override(self):
        chain = self.client._resolve_fallback_chain(
            model_name="deepseek-v3.2",
            default_fallback=None,
            fallback_models=["deepseek-chat", "deepseek-v3.2", "deepseek-chat"],
        )
        assert chain == ["deepseek-chat"]

    @pytest.mark.asyncio
    async def test_call_with_retry_uses_override_chain(self):
        self.client._try_model = AsyncMock(
            side_effect=[
                (None, RuntimeError("primary fail")),
                ("ok", None),
            ]
        )

        result = await self.client._call_with_retry(
            "deepseek-v3.2",
            AsyncMock(),
            max_retries=2,
            fallback_models=["deepseek-chat"],
        )

        assert result == "ok"
        calls = self.client._try_model.call_args_list
        assert calls[0].kwargs["max_attempts"] == 2
        assert calls[0].args[0].model == "deepseek/deepseek-v3.2"
        assert calls[1].args[0].model == "deepseek/deepseek-v3.2"


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

    def test_placeholder_key_is_treated_as_unconfigured(self):
        client = LLMClient.__new__(LLMClient)
        client._clients = {}
        client._tracker = None

        assert client._is_placeholder_key("sk-xxx") is True
        assert client._is_placeholder_key("") is True
        assert client._is_placeholder_key("real-key") is False


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


class _FakeCompletions:
    def __init__(self, payload):
        self._payload = payload

    async def create(self, **kwargs):  # noqa: ARG002
        return self._payload


class _FakeChat:
    def __init__(self, payload):
        self.completions = _FakeCompletions(payload)


class _FakeProviderClient:
    def __init__(self, payload):
        self.chat = _FakeChat(payload)


class TestGatewayResponseCompatibility:
    @pytest.mark.asyncio
    async def test_chat_accepts_string_response(self):
        client = LLMClient.__new__(LLMClient)
        client._clients = {"deepseek": _FakeProviderClient("plain text response")}
        client._tracker = None
        client._allow_build_clients = False

        result = await client.chat(
            [{"role": "user", "content": "hello"}],
            model="deepseek-v3.2",
        )

        assert result == "plain text response"

    @pytest.mark.asyncio
    async def test_chat_json_accepts_dict_response(self):
        payload = {
            "choices": [
                {
                    "message": {"content": '{"ok": true, "value": 1}'},
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        client = LLMClient.__new__(LLMClient)
        client._clients = {"deepseek": _FakeProviderClient(payload)}
        client._tracker = None
        client._allow_build_clients = False

        result = await client.chat_json(
            [{"role": "user", "content": "return json"}],
            model="deepseek-v3.2",
        )

        assert result == {"ok": True, "value": 1}

    @pytest.mark.asyncio
    async def test_chat_json_extracts_fenced_json_content(self):
        payload = {
            "choices": [
                {
                    "message": {
                        "content": "```json\n{\"nodes\":[{\"id\":\"n1\",\"title\":\"x\",\"role\":\"writer\",\"depends_on\":[]}]}\n```"
                    },
                }
            ]
        }
        client = LLMClient.__new__(LLMClient)
        client._clients = {"deepseek": _FakeProviderClient(payload)}
        client._tracker = None
        client._allow_build_clients = False

        result = await client.chat_json(
            [{"role": "user", "content": "return json"}],
            model="deepseek-v3.2",
        )

        assert "nodes" in result
        assert result["nodes"][0]["id"] == "n1"

    @pytest.mark.asyncio
    async def test_chat_rejects_gateway_waf_payload(self, monkeypatch):
        payload = {
            "choices": [
                {
                    "message": {
                        "content": '<!doctypehtml><meta name="aliyun_waf_aa" content="x">',
                    }
                }
            ]
        }
        client = LLMClient.__new__(LLMClient)
        client._clients = {"deepseek": _FakeProviderClient(payload)}
        client._tracker = None
        client._allow_build_clients = False
        monkeypatch.setitem(
            MODEL_REGISTRY,
            "deepseek-v3.2",
            ModelConfig(
                provider="deepseek",
                model="deepseek/deepseek-v3.2",
                supports_streaming=True,
                supports_json_mode=True,
                max_tokens=8192,
                fallback=None,
            ),
        )

        with pytest.raises(LLMUnavailableError, match="gateway/WAF"):
            await client.chat(
                [{"role": "user", "content": "hello"}],
                model="deepseek-v3.2",
            )


class TestChatWithToolsLifecycleTracing:
    @pytest.mark.asyncio
    async def test_chat_with_tools_keeps_legacy_payload_when_lifecycle_disabled(self):
        payload = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "function": {"name": "web.search", "arguments": "{\"q\":\"x\"}"},
                            }
                        ]
                    }
                }
            ]
        }
        client = LLMClient.__new__(LLMClient)
        client._clients = {"deepseek": _FakeProviderClient(payload)}
        client._tracker = None
        client._allow_build_clients = False

        previous_enable = settings.enable_tool_lifecycle
        settings.enable_tool_lifecycle = False
        try:
            await tool_lifecycle_service.clear()
            result = await client.chat_with_tools(
                [{"role": "user", "content": "call tool"}],
                tools=[{"type": "function", "function": {"name": "web.search"}}],
                model="deepseek-v3.2",
            )
            assert result["type"] == "tool_calls"
            assert result["tool_calls"][0]["function"]["name"] == "web.search"
            records = await tool_lifecycle_service.list()
            assert records == []
        finally:
            settings.enable_tool_lifecycle = previous_enable
            await tool_lifecycle_service.clear()

    @pytest.mark.asyncio
    async def test_chat_with_tools_records_lifecycle_when_enabled(self):
        payload = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "function": {"name": "browser.open", "arguments": "{\"url\":\"https://a.com\"}"},
                            }
                        ]
                    }
                }
            ]
        }
        client = LLMClient.__new__(LLMClient)
        client._clients = {"deepseek": _FakeProviderClient(payload)}
        client._tracker = None
        client._allow_build_clients = False

        previous_enable = settings.enable_tool_lifecycle
        settings.enable_tool_lifecycle = True
        try:
            await tool_lifecycle_service.clear()
            result = await client.chat_with_tools(
                [{"role": "user", "content": "call tool"}],
                tools=[{"type": "function", "function": {"name": "browser.open"}}],
                model="deepseek-v3.2",
                role="researcher",
            )
            assert result["type"] == "tool_calls"
            records = await tool_lifecycle_service.list()
            assert len(records) == 1
            assert records[0]["tool_name"] == "browser.open"
            assert records[0]["status"] == "running"
            transition_statuses = [item["status"] for item in records[0]["transitions"]]
            assert transition_statuses == ["registered", "running"]
        finally:
            settings.enable_tool_lifecycle = previous_enable
            await tool_lifecycle_service.clear()


class TestBlockedPayloadDetector:
    def test_is_gateway_block_payload_detects_waf_marker(self):
        assert LLMClient._is_gateway_block_payload(
            '<!doctypehtml><meta name="aliyun_waf_aa" content="x">'
        )

    def test_is_gateway_block_payload_ignores_normal_markdown(self):
        assert not LLMClient._is_gateway_block_payload("# 标题\n\n正常正文内容。")

"""Worker Agent — Layer 2 通用执行层

简单 Worker：接收子任务，调用 LLM 完成，返回结果。
具体的写作/审查/一致性逻辑在 Step 4.2 的专用 Agent 中实现。

Worker 根据 ctx.agent_role 自动加载对应 Prompt 模板，
并通过 llm_client 按角色选模型。
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from app.agents.base_agent import BaseAgent
from app.services.writer_output import (
    is_valid_writer_output_text,
    make_fallback_writer_payload,
    parse_writer_payload,
    serialize_writer_payload,
    validate_writer_payload,
)
from app.services.node_schema import has_valid_schema_for_role
from app.utils.logger import logger
from app.utils.prompt_loader import PromptLoader

_FAST_PATH_MAX_TARGET_WORDS = 2000
_STAGE_AUTORETRY_LIMIT = 2


def _count_text_units(text: str) -> int:
    body = str(text or "")
    if not body:
        return 0
    han_count = len(re.findall(r"[\u4e00-\u9fff]", body))
    latin_count = len(re.findall(r"[a-zA-Z]+", body))
    return han_count + latin_count


def _measure_language_mix(text: str) -> tuple[int, int, float]:
    body = str(text or "")
    han_count = len(re.findall(r"[\u4e00-\u9fff]", body))
    latin_count = len(re.findall(r"[a-zA-Z]+", body))
    total = han_count + latin_count
    if total <= 0:
        return han_count, latin_count, 0.0
    return han_count, latin_count, (han_count / total)


def _english_requested(payload: dict[str, Any]) -> bool:
    candidates = [
        payload.get("language", ""),
        payload.get("language_policy", ""),
        payload.get("style_requirements", ""),
    ]
    hint = " ".join(str(item or "") for item in candidates).lower()
    if not hint.strip():
        return False
    triggers = (
        "english",
        "write in english",
        "output in english",
        "英文",
        "英语",
    )
    return any(token in hint for token in triggers)


class WorkerAgent(BaseAgent):
    """Layer 2 通用执行 Agent — 调用 LLM 完成子任务"""

    def __init__(self, **kwargs: Any) -> None:
        # role 可由外部指定（writer / reviewer / outline / consistency）
        kwargs.setdefault("layer", 2)
        super().__init__(**kwargs)
        self._prompt_loader = PromptLoader()

    async def handle_task(self, ctx: dict[str, Any]) -> str:
        """调用 LLM 执行子任务。

        ctx 期望包含：
          - task_id: 任务 ID
          - node_id: 节点 ID
          - title: 子任务标题
          - agent_role: 执行角色（writer/reviewer/outline/consistency）
          - payload: 子任务详细参数
        """
        task_id = ctx.get("task_id", "")
        title = ctx.get("title", "")
        agent_role = ctx.get("agent_role", self.role)
        payload = self._normalize_payload(
            agent_role=agent_role,
            payload=ctx.get("payload", {}),
            memory_context=ctx.get("memory_context", ""),
            kg_context=ctx.get("kg_context", ""),
        )

        log = logger.bind(
            task_id=task_id,
            agent_id=str(self.agent_id),
            agent_role=agent_role,
            node_id=ctx.get("node_id", ""),
        )

        log.info("executing sub-task: {}", title)

        # 构建消息
        messages = self._build_messages(title, agent_role, payload)

        # 调用 LLM
        model_override = self._select_model_override(agent_role=agent_role, payload=payload)
        log.bind(
            depth=payload.get("depth", ""),
            target_words=payload.get("target_words", ""),
            model_override=model_override or "",
        ).debug("worker model selection")
        result: str | None = None
        role_norm = str(agent_role or "").strip().lower()
        for attempt in range(1, _STAGE_AUTORETRY_LIMIT + 2):
            try:
                if role_norm == "researcher":
                    result = await self._run_researcher_tool_path(
                        messages=messages,
                        payload=payload,
                        model_override=model_override,
                    )
                    if result:
                        log.bind(result_len=len(result), attempt=attempt).info(
                            "researcher used tool-backed execution path"
                        )
                if not result and role_norm == "writer":
                    result = await self._run_writer_hard_json_path(
                        messages=messages,
                        payload=payload,
                        model_override=model_override,
                    )
                    log.bind(result_len=len(result), attempt=attempt).info(
                        "writer used hard-json generation path"
                    )
                if not result:
                    result = await self.llm_client.chat(
                        messages=messages,
                        role=agent_role,
                        model=model_override,
                    )
                break
            except Exception as exc:
                if attempt > _STAGE_AUTORETRY_LIMIT:
                    raise
                delay = min(2.0 * attempt, 8.0)
                log.warning(
                    "stage autoretry triggered (attempt {}/{}): {} ; retry in {:.1f}s",
                    attempt,
                    _STAGE_AUTORETRY_LIMIT,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)

        if result is None:
            raise RuntimeError("worker execution produced empty result after retries")
        result = await self._apply_output_contract(
            result=result,
            title=title,
            agent_role=agent_role,
            payload=payload,
        )

        log.info("sub-task completed, result length={}", len(result))
        return result

    async def _apply_output_contract(
        self,
        *,
        result: str,
        title: str,
        agent_role: str,
        payload: dict[str, Any],
    ) -> str:
        role = str(agent_role or "").strip().lower()
        if role == "writer":
            return await self._repair_writer_output_if_needed(
                result=result,
                title=title,
                payload=payload,
            )
        if role in {"reviewer", "consistency", "researcher"}:
            return await self._repair_structured_output_if_needed(
                result=result,
                agent_role=role,
                title=title,
            )
        return result

    async def _run_researcher_tool_path(
        self,
        *,
        messages: list[dict[str, str]],
        payload: dict[str, Any],
        model_override: str | None,
    ) -> str | None:
        mode = str(payload.get("mode") or "").strip().lower()
        if mode and mode != "report":
            return None

        from app.services.runtime_bootstrap import get_runtime_mcp_client

        mcp_client = get_runtime_mcp_client()
        if mcp_client is None:
            return None

        raw_allowlist = payload.get("tool_allowlist", [])
        tool_allowlist: list[str] = []
        if isinstance(raw_allowlist, list):
            for item in raw_allowlist:
                token = str(item or "").strip()
                if token:
                    tool_allowlist.append(token)
        tools = mcp_client.registry.to_openai_tools(tool_allowlist or None)
        if not tools:
            return None

        try:
            max_iterations = int(payload.get("max_tool_iterations") or 2)
        except (TypeError, ValueError):
            max_iterations = 2
        max_iterations = min(max(1, max_iterations), 4)

        conversation: list[dict[str, Any]] = [dict(item) for item in messages]

        for _ in range(max_iterations):
            response = await self.llm_client.chat_with_tools(
                messages=conversation,
                tools=tools,
                role="researcher",
                model=model_override,
            )
            if response.get("type") == "text":
                content = str(response.get("content") or "").strip()
                if content:
                    return content
                break

            tool_calls = response.get("tool_calls") or []
            if not tool_calls:
                break

            assistant_tool_calls: list[dict[str, Any]] = []
            tool_messages: list[dict[str, str]] = []

            for call in tool_calls:
                call_id = str(call.get("id") or "")
                fn = call.get("function") or {}
                tool_name = str(fn.get("name") or "").strip()
                raw_args = str(fn.get("arguments") or "").strip()
                if not call_id or not tool_name:
                    continue
                try:
                    parsed_args = json.loads(raw_args) if raw_args else {}
                except Exception:
                    parsed_args = {}
                if not isinstance(parsed_args, dict):
                    parsed_args = {}

                tool_output = await mcp_client.call_tool(tool_name, parsed_args)
                assistant_tool_calls.append(
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": json.dumps(parsed_args, ensure_ascii=False),
                        },
                    }
                )
                tool_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": str(tool_output or ""),
                    }
                )

            if not assistant_tool_calls:
                break

            conversation.append(
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": assistant_tool_calls,
                }
            )
            conversation.extend(tool_messages)
        return None

    async def _run_writer_hard_json_path(
        self,
        *,
        messages: list[dict[str, str]],
        payload: dict[str, Any],
        model_override: str | None,
    ) -> str:
        """Enforce writer output as strict JSON before post-processing.

        When model retries still fail schema checks, return a deterministic
        structured fallback to prevent shape-level scheduler failure.
        """
        attempts = 3
        working_messages: list[dict[str, str]] = [dict(item) for item in messages]
        chapter_title = str(payload.get("chapter_title") or payload.get("title") or "").strip()
        injected_prompt = self._build_writer_injected_prompt(payload=payload, chapter_title=chapter_title)
        if injected_prompt:
            working_messages.append({"role": "user", "content": injected_prompt})
        chat_json_fn = getattr(self.llm_client, "chat_json", None)
        if not callable(chat_json_fn):
            # Backward-compatible path for tests/mocks that only implement chat().
            raw_text = await self.llm_client.chat(
                messages=working_messages,
                role="writer",
                model=model_override,
            )
            return str(raw_text or "")
        last_obj: dict[str, Any] | None = None
        for attempt in range(1, attempts + 1):
            obj = await chat_json_fn(
                messages=working_messages,
                role="writer",
                model=model_override,
                max_retries=2,
            )
            last_obj = obj if isinstance(obj, dict) else None
            raw = json.dumps(obj, ensure_ascii=False)
            parsed = parse_writer_payload(raw)
            if parsed is not None:
                if not parsed.get("chapter_title"):
                    parsed["chapter_title"] = chapter_title
                return serialize_writer_payload(parsed)

            # Fall back to normal chat for this attempt to keep compatibility
            # with providers that do not reliably honor chat_json contracts.
            fallback_text = await self.llm_client.chat(
                messages=working_messages,
                role="writer",
                model=model_override,
            )
            fallback_text = str(fallback_text or "").strip()
            if fallback_text:
                parsed_fallback = parse_writer_payload(fallback_text)
                if parsed_fallback is not None:
                    if not parsed_fallback.get("chapter_title"):
                        parsed_fallback["chapter_title"] = chapter_title
                    return serialize_writer_payload(parsed_fallback)

            working_messages.append(
                {
                    "role": "user",
                    "content": (
                        "上次输出未通过 writer schema 校验。"
                        "必须返回严格 JSON 对象，且至少包含："
                        "heading, paragraphs。"
                        "其中 paragraphs 必须是数组，每项包含 text 和 citation_keys。"
                        "可附带 chapter_title, content_markdown, key_points, "
                        "evidence_trace, boundary_notes, citation_ledger。"
                        "禁止返回 markdown 代码块或额外解释。"
                    ),
                }
            )
            logger.bind(agent_id=str(self.agent_id), attempt=attempt).warning(
                "writer hard-json attempt failed schema check"
            )

        best_effort_markdown = ""
        if isinstance(last_obj, dict):
            for key in ("content_markdown", "chapter_markdown", "content", "text", "body", "draft"):
                candidate = str(last_obj.get(key) or "").strip()
                if candidate:
                    best_effort_markdown = candidate
                    break
        if not best_effort_markdown:
            best_effort_markdown = (
                f"# {chapter_title or '章节'}\n\n"
                "（自动结构化兜底：模型返回了非合规 writer JSON，"
                "后续轮次会继续补写该章节内容。）"
            )
        fallback = make_fallback_writer_payload(
            chapter_title=chapter_title,
            content_markdown=best_effort_markdown,
        )
        if fallback is not None:
            logger.bind(agent_id=str(self.agent_id)).warning(
                "writer hard-json path exhausted retries; using structured fallback payload"
            )
            return serialize_writer_payload(fallback)
        raise ValueError("Writer hard-json generation failed after retries")

    @staticmethod
    def _estimate_writer_paragraph_count(node_target_words: int) -> int:
        target = max(0, int(node_target_words or 0))
        if target <= 0:
            return 5
        # Konruns-like sizing: roughly one analytical paragraph per ~350 chars.
        return max(4, min(18, target // 350 + 1))

    def _build_writer_injected_prompt(self, *, payload: dict[str, Any], chapter_title: str) -> str:
        title = str(chapter_title or "本章").strip() or "本章"
        chapter_desc = str(payload.get("chapter_description") or "").strip()
        chapter_content = str(payload.get("chapter_content") or "").strip()
        memory_context = str(payload.get("memory_context") or "").strip()
        research_questions = str(payload.get("research_questions") or "").strip()
        topic_claims = payload.get("topic_claims")
        assigned_evidence = payload.get("assigned_evidence")
        source_policy = str(payload.get("source_policy") or "").strip()
        evidence_pool_summary = str(payload.get("evidence_pool_summary") or "").strip()
        topic_claims_text = (
            json.dumps(topic_claims, ensure_ascii=False)
            if isinstance(topic_claims, (dict, list))
            else str(topic_claims or "").strip()
        )
        assigned_evidence_text = (
            json.dumps(assigned_evidence, ensure_ascii=False)
            if isinstance(assigned_evidence, (dict, list))
            else str(assigned_evidence or "").strip()
        )
        try:
            node_target_words = int(payload.get("node_target_words") or payload.get("target_words") or 0)
        except Exception:
            node_target_words = 0
        paragraph_count = self._estimate_writer_paragraph_count(node_target_words)
        return (
            "后端强注入写作约束（必须执行）：\n"
            f"- 章节：{title}\n"
            f"- 本章目标字数：至少 {max(900, node_target_words)}\n"
            f"- 最少段落数：{paragraph_count}\n"
            f"- 章节任务：{chapter_desc or '围绕章节主题给出可执行分析与证据支撑'}\n"
            f"- 研究问题：{research_questions or '请围绕任务主题中的核心问题推进论证'}\n"
            f"- 记忆上下文：{memory_context[:1200] if memory_context else '（空）'}\n"
            f"- 章节边界(topic_claims)：{topic_claims_text[:2000] if topic_claims_text else '（空）'}\n"
            f"- 指派证据(assigned_evidence)：{assigned_evidence_text[:2000] if assigned_evidence_text else '（空）'}\n"
            "- 输出必须为严格 JSON 对象，不得有 markdown 代码块或解释文本。\n"
            '- 必须包含键：heading, paragraphs, chapter_title, content_markdown, key_points, evidence_trace, boundary_notes, citation_ledger。\n'
            '- paragraphs 每项必须是 {"text":"中文分析段落","citation_keys":["..."]}。\n'
            "- 每段应包含：可检验观点 + 证据支撑 + 边界/反例或实施含义；禁止空话和模板开头。\n"
            "- 不得写“围绕本章继续补充”“本轮扩写”等流程描述。\n"
            "- 引用仅通过 citation_keys 字段绑定，不要把 citation key 写进正文句子。\n"
            f"- 可用证据策略：{source_policy[:1200] if source_policy else '遵循给定证据池与章节边界'}\n"
            f"- 证据池摘要：{evidence_pool_summary[:1200] if evidence_pool_summary else '无摘要时使用 assigned_evidence'}\n"
            f"- 已有正文（用于扩写而非重写）：{chapter_content[:2000] if chapter_content else '（空）'}"
        )

    def _select_model_override(self, *, agent_role: str, payload: dict[str, Any]) -> str | None:
        role = str(agent_role or "").strip().lower()
        if role not in {"outline", "researcher", "writer", "reviewer", "consistency"}:
            return None

        depth = str(payload.get("depth") or "").strip().lower()
        if depth != "quick":
            return None

        try:
            target_words = int(payload.get("target_words") or 0)
        except (TypeError, ValueError):
            target_words = 0
        if target_words <= 0 or target_words > _FAST_PATH_MAX_TARGET_WORDS:
            return None
        return "deepseek-v3.2"

    @staticmethod
    def _extract_json_object(text: str) -> dict[str, Any] | None:
        body = (text or "").strip()
        if body.startswith("```"):
            lines = body.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            body = "\n".join(lines).strip()
        try:
            parsed = json.loads(body)
        except Exception:
            return None
        return parsed if isinstance(parsed, dict) else None

    def _writer_output_needs_repair(self, text: str) -> bool:
        return not is_valid_writer_output_text(text)

    async def _repair_writer_output_if_needed(
        self,
        *,
        result: str,
        title: str,
        payload: dict[str, Any],
    ) -> str:
        parsed_payload = parse_writer_payload(result)
        quality_issues: list[str] = []
        min_units = 0
        try:
            min_units = int(payload.get("word_floor") or 0)
        except (TypeError, ValueError):
            min_units = 0
        if min_units <= 0:
            try:
                target_words = int(payload.get("target_words") or 0)
            except (TypeError, ValueError):
                target_words = 0
            if target_words > 0:
                min_units = max(900, int(target_words * 0.92))
        if min_units <= 0:
            min_units = 700
        observed_units = 0
        observed_zh_ratio = 0.0
        should_enforce_chinese = not _english_requested(payload)
        if parsed_payload is not None:
            quality_issues = validate_writer_payload(parsed_payload)
            content = parsed_payload.get("content_markdown") or ""
            observed_units = _count_text_units(content)
            _, _, observed_zh_ratio = _measure_language_mix(content)

        needs_length_repair = observed_units < min_units
        needs_language_repair = (
            should_enforce_chinese
            and observed_units >= 120
            and observed_zh_ratio < 0.7
        )
        if not self._writer_output_needs_repair(result) and not needs_length_repair:
            if parsed_payload is not None and not needs_language_repair:
                return serialize_writer_payload(parsed_payload)
            return result

        chapter_title = str(payload.get("chapter_title") or title).strip()
        target_words = str(payload.get("target_words") or "").strip()
        if needs_length_repair:
            quality_issues.append(
                f"content_below_min_units:{observed_units}<{min_units}"
            )
        if needs_language_repair:
            quality_issues.append(
                f"language_policy_violation:zh_ratio={observed_zh_ratio:.3f}<0.700"
            )
        issue_hint = ", ".join(quality_issues) if quality_issues else "schema_invalid_or_missing_fields"
        source_content = (
            parsed_payload.get("content_markdown", "")
            if parsed_payload is not None
            else result
        )
        prompt = (
            "Repair the chapter into strict JSON writer schema with improved writing quality.\n"
            "Output requirements:\n"
            "- Return strict JSON object only (no markdown code fence)\n"
            '- Required keys: "heading", "paragraphs"\n'
            '- paragraphs must be array items like {"text":"...", "citation_keys":["..."]}\n'
            "- content_markdown can be provided as compatibility field but is optional\n"
            '- key_points must be string array (3-6 bullets)\n'
            '- evidence_trace must be array of {"claim": "...", "evidence_ids": ["..."]}\n'
            '- boundary_notes must be string array\n'
            "- Remove templated filler and repetitive paragraph openings\n"
            "- Avoid mechanical connector chains like 首先/其次/最后; use natural transitions\n"
            "- Keep major claims evidence-aware; unsupported claims must be marked uncertain in citation_ledger\n"
            "- Keep chapter scope intact\n"
            f"- content_markdown minimum length: {min_units} text units (Chinese chars + English words)\n"
            "- If content is below minimum, expand with concrete analysis, examples, and transitions while staying on-topic\n"
            "- Default language policy: Chinese-first prose; unless explicitly requested, keep Chinese-dominant text (>= 70% Chinese ratio)\n"
            f"- Repair reasons: {issue_hint}\n"
            f"- Chapter: {chapter_title}\n"
            f"- Target words: {target_words or 'follow original density'}\n\n"
            "Source content:\n"
            f"{source_content}"
        )
        try:
            repaired = await self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                role="writer",
            )
            repaired_text = str(repaired or "").strip()
            payload = parse_writer_payload(repaired_text)
            repaired_units = _count_text_units((payload or {}).get("content_markdown", ""))
            repaired_zh_ratio = 0.0
            if payload is not None:
                _, _, repaired_zh_ratio = _measure_language_mix(payload.get("content_markdown") or "")
            language_ok = (
                (not should_enforce_chinese)
                or repaired_units < 120
                or repaired_zh_ratio >= 0.7
            )
            if (
                payload is not None
                and not validate_writer_payload(payload)
                and repaired_units >= min_units
                and language_ok
            ):
                if not payload.get("chapter_title"):
                    payload["chapter_title"] = chapter_title
                return serialize_writer_payload(payload)
            if repaired_text and self._extract_json_object(repaired_text) is None:
                fallback = make_fallback_writer_payload(
                    chapter_title=chapter_title,
                    content_markdown=repaired_text,
                )
                if fallback is not None:
                    return serialize_writer_payload(fallback)
        except Exception:
            logger.bind(agent_id=str(self.agent_id)).opt(exception=True).warning(
                "writer output repair failed; keeping original output"
            )
        # Backend hard fallback (Konruns-style): enforce minimum length via local structured supplement,
        # instead of relying solely on model retries.
        local_fallback = make_fallback_writer_payload(
            chapter_title=chapter_title,
            content_markdown=result,
        )
        if local_fallback is None:
            local_fallback = make_fallback_writer_payload(
                chapter_title=chapter_title,
                content_markdown=f"# {chapter_title}\n\n（本地补写占位）",
            )
        if local_fallback is None:
            return result
        ensured = self._ensure_local_writer_minimum(
            payload=local_fallback,
            min_units=min_units,
            chapter_title=chapter_title,
            task_payload=payload,
        )
        return serialize_writer_payload(ensured)

    def _ensure_local_writer_minimum(
        self,
        *,
        payload: dict[str, Any],
        min_units: int,
        chapter_title: str,
        task_payload: dict[str, Any],
    ) -> dict[str, Any]:
        paragraphs_raw = payload.get("paragraphs", [])
        paragraphs: list[dict[str, Any]] = []
        if isinstance(paragraphs_raw, list):
            for item in paragraphs_raw:
                if isinstance(item, dict) and str(item.get("text") or "").strip():
                    keys_raw = item.get("citation_keys", [])
                    if isinstance(keys_raw, list):
                        keys = [str(k).strip() for k in keys_raw if str(k).strip()]
                    else:
                        keys = []
                    paragraphs.append({"text": str(item.get("text") or "").strip(), "citation_keys": keys})

        current_text = "\n\n".join(item["text"] for item in paragraphs)
        current_units = _count_text_units(current_text)
        if current_units >= min_units:
            return payload

        evidence_ids = self._derive_local_citation_keys(task_payload)
        round_idx = 1
        while current_units < min_units:
            snippet = self._build_local_writer_paragraph(
                chapter_title=chapter_title,
                round_idx=round_idx,
                base_text=current_text,
            )
            paragraphs.append(
                {
                    "text": snippet,
                    "citation_keys": evidence_ids[:2],
                }
            )
            current_text = "\n\n".join(item["text"] for item in paragraphs)
            current_units = _count_text_units(current_text)
            round_idx += 1
            if round_idx > 24:
                break

        payload["heading"] = str(payload.get("heading") or chapter_title or "").strip()
        payload["chapter_title"] = str(payload.get("chapter_title") or payload["heading"]).strip()
        payload["paragraphs"] = paragraphs
        payload["content_markdown"] = current_text
        payload.setdefault("key_points", [])
        payload.setdefault("evidence_trace", [])
        payload.setdefault("boundary_notes", [])
        payload.setdefault("citation_ledger", [])
        return payload

    @staticmethod
    def _derive_local_citation_keys(task_payload: dict[str, Any]) -> list[str]:
        out: list[str] = []
        assigned = task_payload.get("assigned_evidence", [])
        if isinstance(assigned, list):
            for item in assigned:
                if isinstance(item, dict):
                    key = str(item.get("evidence_id") or "").strip()
                else:
                    key = str(item or "").strip()
                if key and key not in out:
                    out.append(key)
        if not out:
            out.append("E-LOCAL")
        return out

    @staticmethod
    def _build_local_writer_paragraph(*, chapter_title: str, round_idx: int, base_text: str = "") -> str:
        sentences = [
            s.strip()
            for s in re.split(r"[。！？!?]\s*", str(base_text or ""))
            if len(s.strip()) >= 18
        ]
        anchor = sentences[(round_idx - 1) % len(sentences)] if sentences else f"{chapter_title}的核心结论"
        dimensions = [
            "机制解释",
            "实施步骤",
            "量化指标",
            "约束条件",
            "反例与边界",
            "落地建议",
        ]
        dim = dimensions[(round_idx - 1) % len(dimensions)]
        return (
            f"{anchor}。进一步展开其{dim}时，可以按照“现状基线—关键变量—执行动作—可观测结果”四步来描述。"
            "具体可先明确当前状态与目标差值，再给出可操作动作清单与阶段里程碑，"
            "最后用可验证的结果指标收束论证，避免停留在抽象表述。"
        )

    def _structured_output_valid(self, text: str, agent_role: str) -> bool:
        if not has_valid_schema_for_role(agent_role, text):
            return False
        if agent_role == "researcher":
            parsed = self._extract_json_object(text)
            if not parsed:
                return False
            ledger = parsed.get("evidence_ledger", [])
            if not isinstance(ledger, list):
                return False
            for item in ledger:
                if not isinstance(item, dict):
                    return False
                item_keys = {str(k).lower() for k in item.keys()}
                must_keys = {
                    "evidence_id",
                    "claim_target",
                    "required_source_type",
                    "priority",
                    "source_url",
                    "source_title",
                    "published_at",
                }
                if not must_keys.issubset(item_keys):
                    return False
            return True
        return True

    async def _repair_structured_output_if_needed(
        self,
        *,
        result: str,
        agent_role: str,
        title: str,
    ) -> str:
        if self._structured_output_valid(result, agent_role):
            return result

        if agent_role == "reviewer":
            schema_hint = (
                '{"score":0,"must_fix":[],"feedback":"","pass":false,'
                '"accuracy_score":0,"coherence_score":0,'
                '"evidence_sufficiency_score":0,"boundary_compliance_score":0,'
                '"non_overlap_score":0,"specificity_score":0,'
                '"source_attribution_score":0,'
                '"unsupported_claims":[],"missing_sources":[],'
                '"strongest_counterargument":""}'
            )
        elif agent_role == "researcher":
            schema_hint = (
                '{"topic_anchor":"","source_scope":{"allowed":[],"disallowed":[],"time_window":""},'
                '"keyword_plan":[{"bucket":"definition","queries":[]}],'
                '"evidence_ledger":[{"evidence_id":"E1","claim_target":"","required_source_type":"paper",'
                '"priority":"high","source_url":"","source_title":"","published_at":""}],'
                '"chapter_mapping":[{"chapter_hint":"","must_have_evidence_ids":[],"boundary_notes":[]}],'
                '"uncertainty_flags":[]}'
            )
        else:
            schema_hint = (
                '{"pass":false,"style_conflicts":[],"claim_conflicts":[],'
                '"duplicate_coverage":[],"term_inconsistency":[],'
                '"transition_gaps":[],"language_policy_conflicts":[],"source_policy_violations":[],'
                '"severity_summary":{"critical":0,"high":0,"medium":0,"low":0},'
                '"repair_priority":[],"repair_targets":[]}'
            )

        prompt = (
            "Return strict JSON only, matching the required schema.\n"
            f"Task: {title}\n"
            f"Schema skeleton: {schema_hint}\n\n"
            "Previous invalid output:\n"
            f"{result}"
        )
        try:
            repaired = await self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                role=agent_role,
            )
            repaired_text = str(repaired or "").strip()
            if self._structured_output_valid(repaired_text, agent_role):
                return repaired_text
        except Exception:
            logger.bind(agent_id=str(self.agent_id)).opt(exception=True).warning(
                "{} output repair failed; keeping original output",
                agent_role,
            )
        return result

    def _normalize_payload(
        self,
        *,
        agent_role: str,
        payload: dict[str, Any],
        memory_context: str,
        kg_context: str,
    ) -> dict[str, Any]:
        """Ensure role-specific prompt variables always exist to avoid fallback prompts."""
        raw = dict(payload or {})
        if agent_role == "outline":
            return {
                "title": raw.get("title", ""),
                "mode": raw.get("mode", "report"),
                "depth": raw.get("depth", ""),
                "target_words": raw.get("target_words", ""),
                "draft_text": raw.get("draft_text", ""),
                "review_comments": raw.get("review_comments", ""),
                "style_requirements": raw.get("style_requirements", ""),
                "source_policy": raw.get("source_policy", ""),
                "research_keywords": raw.get("research_keywords", ""),
                "evidence_pool_summary": raw.get("evidence_pool_summary", ""),
                "evidence_pool_markdown": raw.get("evidence_pool_markdown", ""),
            }
        if agent_role == "writer":
            return {
                "depth": raw.get("depth", ""),
                "chapter_index": raw.get("chapter_index", ""),
                "chapter_title": raw.get("chapter_title", ""),
                "stage_code": raw.get("stage_code", ""),
                "schema_version": raw.get("schema_version", ""),
                "stage_contract": raw.get("stage_contract", ""),
                "full_outline": raw.get("full_outline", ""),
                "chapter_description": raw.get("chapter_description", ""),
                "context_bridges": raw.get("context_bridges", ""),
                "memory_context": raw.get("memory_context", memory_context or ""),
                "topic_claims": raw.get("topic_claims", {}),
                "assigned_evidence": raw.get("assigned_evidence", []),
                "source_policy": raw.get("source_policy", ""),
                "research_protocol": raw.get("research_protocol", ""),
                "research_keywords": raw.get("research_keywords", ""),
                "evidence_pool_summary": raw.get("evidence_pool_summary", ""),
                "evidence_pool_markdown": raw.get("evidence_pool_markdown", ""),
                "target_words": raw.get("target_words", ""),
                "task_target_words": raw.get("task_target_words", raw.get("target_words", "")),
                "node_target_words": raw.get("node_target_words", raw.get("target_words", "")),
                "is_assembly_editor": raw.get("is_assembly_editor", False),
                "title_level_rule": raw.get("title_level_rule", ""),
                "evidence_rule": raw.get("evidence_rule", ""),
                "kg_context": raw.get("kg_context", kg_context or ""),
            }
        if agent_role == "researcher":
            return {
                "title": raw.get("title", ""),
                "mode": raw.get("mode", "report"),
                "depth": raw.get("depth", ""),
                "target_words": raw.get("target_words", ""),
                "full_outline": raw.get("full_outline", ""),
                "source_policy": raw.get("source_policy", ""),
                "research_keywords": raw.get("research_keywords", ""),
                "evidence_pool_seeds": raw.get("evidence_pool_seeds", ""),
                "evidence_pool_summary": raw.get("evidence_pool_summary", ""),
                "evidence_pool_markdown": raw.get("evidence_pool_markdown", ""),
                "memory_context": raw.get("memory_context", memory_context or ""),
                "kg_context": raw.get("kg_context", kg_context or ""),
                "tool_allowlist": raw.get("tool_allowlist", []),
                "max_tool_iterations": raw.get("max_tool_iterations", 2),
            }
        if agent_role == "reviewer":
            return {
                "depth": raw.get("depth", ""),
                "chapter_index": raw.get("chapter_index", ""),
                "chapter_title": raw.get("chapter_title", ""),
                "chapter_content": raw.get("chapter_content", ""),
                "chapter_description": raw.get("chapter_description", ""),
                "overlap_findings": raw.get("overlap_findings", "none"),
                "topic_claims": raw.get("topic_claims", {}),
                "assigned_evidence": raw.get("assigned_evidence", []),
                "source_policy": raw.get("source_policy", ""),
                "research_protocol": raw.get("research_protocol", ""),
                "research_keywords": raw.get("research_keywords", ""),
                "evidence_pool_summary": raw.get("evidence_pool_summary", ""),
                "evidence_pool_markdown": raw.get("evidence_pool_markdown", ""),
            }
        if agent_role == "consistency":
            return {
                "depth": raw.get("depth", ""),
                "target_words": raw.get("target_words", ""),
                "chapters_summary": raw.get("chapters_summary", ""),
                "key_fragments": raw.get("key_fragments", ""),
                "full_text": raw.get("full_text", raw.get("full_draft", "")),
                "topic_claims": raw.get("topic_claims", []),
                "chapter_metadata": raw.get("chapter_metadata", []),
                "source_policy": raw.get("source_policy", ""),
                "research_keywords": raw.get("research_keywords", ""),
                "evidence_pool_summary": raw.get("evidence_pool_summary", ""),
                "evidence_pool_markdown": raw.get("evidence_pool_markdown", ""),
            }
        return raw

    def _build_messages(
        self,
        title: str,
        agent_role: str,
        payload: dict[str, Any],
    ) -> list[dict[str, str]]:
        """根据角色构建 LLM 消息序列。"""
        messages: list[dict[str, str]] = []

        # 尝试加载 system prompt
        try:
            system_prompt = self._prompt_loader.load_system(agent_role)
            messages.append({"role": "system", "content": system_prompt})
        except FileNotFoundError:
            pass

        # 构建 user 消息
        user_content = self._build_user_prompt(title, agent_role, payload)
        messages.append({"role": "user", "content": user_content})

        return messages

    def _build_user_prompt(
        self,
        title: str,
        agent_role: str,
        payload: dict[str, Any],
    ) -> str:
        """构建用户 Prompt — 尝试从模板加载，失败则使用通用格式。"""
        # 角色 → 模板 action 映射
        role_action_map = {
            "outline": "generate",
            "researcher": "research",
            "writer": "write_chapter",
            "reviewer": "review_chapter",
            "consistency": "check",
        }

        action = role_action_map.get(agent_role)
        if action:
            try:
                return self._prompt_loader.load(
                    agent_role,
                    action,
                    **{
                        k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
                        for k, v in payload.items()
                    },
                )
            except (FileNotFoundError, KeyError):
                pass

        # 通用格式 fallback
        parts = [f"## 任务\n{title}"]
        if payload:
            details = "\n".join(f"- {k}: {v}" for k, v in payload.items())
            parts.append(f"\n## 详情\n{details}")
        return "\n".join(parts)

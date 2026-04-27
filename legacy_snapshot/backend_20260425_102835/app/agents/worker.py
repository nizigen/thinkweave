"""Worker Agent — Layer 2 通用执行层

简单 Worker：接收子任务，调用 LLM 完成，返回结果。
具体的写作/审查/一致性逻辑在 Step 4.2 的专用 Agent 中实现。

Worker 根据 ctx.agent_role 自动加载对应 Prompt 模板，
并通过 llm_client 按角色选模型。
"""

from __future__ import annotations

import json
from typing import Any

from app.agents.base_agent import BaseAgent
from app.services.writer_output import (
    is_valid_writer_output_text,
    make_fallback_writer_payload,
    parse_writer_payload,
    serialize_writer_payload,
    validate_writer_payload,
)
from app.utils.logger import logger
from app.utils.prompt_loader import PromptLoader


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
        result = await self.llm_client.chat(
            messages=messages,
            role=agent_role,
        )
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
        if role in {"reviewer", "consistency"}:
            return await self._repair_structured_output_if_needed(
                result=result,
                agent_role=role,
                title=title,
            )
        return result

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
        if parsed_payload is not None:
            quality_issues = validate_writer_payload(parsed_payload)

        if not self._writer_output_needs_repair(result):
            if parsed_payload is not None:
                return serialize_writer_payload(parsed_payload)
            return result

        chapter_title = str(payload.get("chapter_title") or title).strip()
        target_words = str(payload.get("target_words") or "").strip()
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
            '- Required keys: "chapter_title", "content_markdown", "key_points", "evidence_trace", "boundary_notes", "citation_ledger"\n'
            "- content_markdown must be chapter prose in markdown\n"
            '- key_points must be string array (3-6 bullets)\n'
            '- evidence_trace must be array of {"claim": "...", "evidence_ids": ["..."]}\n'
            '- boundary_notes must be string array\n'
            "- Remove templated filler and repetitive paragraph openings\n"
            "- Avoid mechanical connector chains like 首先/其次/最后; use natural transitions\n"
            "- Keep major claims evidence-aware; unsupported claims must be marked uncertain in citation_ledger\n"
            "- Keep chapter scope intact\n"
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
            if payload is not None and not validate_writer_payload(payload):
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
        fallback = make_fallback_writer_payload(
            chapter_title=chapter_title,
            content_markdown=result,
        )
        if fallback is not None:
            return serialize_writer_payload(fallback)
        return result

    def _structured_output_valid(self, text: str, agent_role: str) -> bool:
        parsed = self._extract_json_object(text)
        if not parsed:
            return False
        keys = {str(k).lower() for k in parsed.keys()}
        if agent_role == "reviewer":
            required = {"score", "must_fix", "feedback", "pass"}
            return required.issubset(keys)
        if agent_role == "consistency":
            required = {"pass", "style_conflicts", "claim_conflicts", "repair_targets"}
            return required.issubset(keys)
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
                '"non_overlap_score":0,"strongest_counterargument":""}'
            )
        else:
            schema_hint = (
                '{"pass":false,"style_conflicts":[],"claim_conflicts":[],'
                '"duplicate_coverage":[],"term_inconsistency":[],'
                '"transition_gaps":[],"repair_targets":[]}'
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
        if agent_role == "writer":
            return {
                "chapter_index": raw.get("chapter_index", ""),
                "chapter_title": raw.get("chapter_title", ""),
                "full_outline": raw.get("full_outline", ""),
                "chapter_description": raw.get("chapter_description", ""),
                "context_bridges": raw.get("context_bridges", ""),
                "memory_context": raw.get("memory_context", memory_context or ""),
                "topic_claims": raw.get("topic_claims", {}),
                "assigned_evidence": raw.get("assigned_evidence", []),
                "source_policy": raw.get("source_policy", ""),
                "research_protocol": raw.get("research_protocol", ""),
                "research_keywords": raw.get("research_keywords", ""),
                "target_words": raw.get("target_words", ""),
                "kg_context": raw.get("kg_context", kg_context or ""),
            }
        if agent_role == "researcher":
            return {
                "title": raw.get("title", ""),
                "mode": raw.get("mode", "report"),
                "target_words": raw.get("target_words", ""),
                "full_outline": raw.get("full_outline", ""),
                "source_policy": raw.get("source_policy", ""),
                "research_keywords": raw.get("research_keywords", ""),
                "memory_context": raw.get("memory_context", memory_context or ""),
                "kg_context": raw.get("kg_context", kg_context or ""),
            }
        if agent_role == "reviewer":
            return {
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
            }
        if agent_role == "consistency":
            return {
                "chapters_summary": raw.get("chapters_summary", ""),
                "full_text": raw.get("full_text", raw.get("full_draft", "")),
                "topic_claims": raw.get("topic_claims", []),
                "chapter_metadata": raw.get("chapter_metadata", []),
                "source_policy": raw.get("source_policy", ""),
                "research_keywords": raw.get("research_keywords", ""),
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

"""任务分解服务 — 调用LLM将写作需求拆解为DAG子任务图"""

from __future__ import annotations

from app.schemas.task import (
    DAGSchema,
    ValidationResult,
    VALID_DEPTHS,
    VALID_MODES,
)
from app.utils.llm_client import BaseLLMClient
from app.utils.logger import logger
from app.utils.prompt_loader import PromptLoader


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class TaskValidationError(Exception):
    """输入验证失败（标题太短、mode非法等）"""

    def __init__(self, issues: list[str]) -> None:
        self.issues = issues
        super().__init__(f"Task validation failed: {issues}")


class CyclicDAGError(Exception):
    """DAG包含环或引用了不存在的节点"""


# ---------------------------------------------------------------------------
# Input Validation
# ---------------------------------------------------------------------------

_MIN_TITLE_LENGTH = 5


def validate_task_input(
    title: str, mode: str, depth: str
) -> ValidationResult:
    """
    验证任务输入合法性（参考DeerFlow CLARIFY → PLAN → ACT模式）。
    在调用LLM前拦截明显错误。
    """
    issues: list[str] = []
    stripped = title.strip()

    if len(stripped) < _MIN_TITLE_LENGTH:
        issues.append(
            f"标题长度不足（至少{_MIN_TITLE_LENGTH}个字符，当前{len(stripped)}个）"
        )

    if mode not in VALID_MODES:
        issues.append(
            f"无效的模式 '{mode}'，可选值: {sorted(VALID_MODES)}"
        )

    if depth not in VALID_DEPTHS:
        issues.append(
            f"无效的深度 '{depth}'，可选值: {sorted(VALID_DEPTHS)}"
        )

    return ValidationResult(ok=len(issues) == 0, issues=issues)


# ---------------------------------------------------------------------------
# DAG Parsing & Validation
# ---------------------------------------------------------------------------

def parse_dag_response(raw: dict) -> DAGSchema:
    """
    解析并校验LLM返回的DAG JSON。

    Raises:
        ValueError: JSON结构不合法、role非法、节点ID重复、首节点非outline
    """
    try:
        dag = DAGSchema.model_validate(raw)
    except Exception as e:
        raise ValueError(f"DAG schema validation failed: {e}") from e

    # 检查节点ID唯一性
    node_ids = [n.id for n in dag.nodes]
    if len(node_ids) != len(set(node_ids)):
        seen: set[str] = set()
        dupes = []
        for nid in node_ids:
            if nid in seen:
                dupes.append(nid)
            seen.add(nid)
        raise ValueError(f"Duplicate node IDs: {dupes}")

    # 首节点必须是outline
    if dag.nodes[0].role != "outline":
        raise ValueError(
            f"First node must have role 'outline', got '{dag.nodes[0].role}'"
        )

    return dag


def validate_dag_acyclic(dag: DAGSchema) -> None:
    """
    验证DAG无环（Kahn拓扑排序）。

    Raises:
        CyclicDAGError: 存在环或引用了不存在的节点
    """
    node_ids = {n.id for n in dag.nodes}

    # 检查依赖引用的节点是否都存在
    for node in dag.nodes:
        for dep in node.depends_on:
            if dep not in node_ids:
                raise CyclicDAGError(
                    f"Node '{node.id}' depends on unknown node '{dep}'"
                )

    # Kahn拓扑排序检测环
    in_degree: dict[str, int] = {n.id: 0 for n in dag.nodes}
    adjacency: dict[str, list[str]] = {n.id: [] for n in dag.nodes}

    for node in dag.nodes:
        for dep in node.depends_on:
            adjacency[dep].append(node.id)
            in_degree[node.id] += 1

    queue = [nid for nid, deg in in_degree.items() if deg == 0]
    sorted_count = 0

    while queue:
        current = queue.pop(0)
        sorted_count += 1
        for neighbor in adjacency[current]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if sorted_count != len(dag.nodes):
        raise CyclicDAGError(
            f"DAG contains a cycle (sorted {sorted_count}/{len(dag.nodes)} nodes)"
        )


# ---------------------------------------------------------------------------
# Main Decomposition
# ---------------------------------------------------------------------------

_prompt_loader = PromptLoader()


async def decompose_task(
    *,
    title: str,
    mode: str,
    depth: str = "standard",
    target_words: int = 10000,
    llm_client: BaseLLMClient,
) -> DAGSchema:
    """
    验证输入 → 加载Prompt → 调用LLM → 解析DAG → 验证无环。

    Args:
        title: 任务标题/描述
        mode: 写作模式 (report/novel/custom)
        depth: 研究深度 (quick/standard/deep)
        target_words: 目标字数
        llm_client: LLM客户端（支持依赖注入Mock）

    Returns:
        DAGSchema: 经过验证的DAG结构

    Raises:
        TaskValidationError: 输入校验失败
        ValueError: DAG结构非法
        CyclicDAGError: DAG包含环
    """
    # 1. 输入验证
    validation = validate_task_input(title, mode, depth)
    if not validation.ok:
        raise TaskValidationError(validation.issues)

    # 2. 加载并渲染Prompt
    prompt = _prompt_loader.load(
        "orchestrator",
        "decompose",
        title=title,
        mode=mode,
        depth=depth,
        target_words=str(target_words),
    )

    # 3. 调用LLM获取DAG JSON
    logger.bind(title=title, mode=mode, depth=depth).info(
        "Decomposing task via LLM"
    )
    raw = await llm_client.chat_json(
        messages=[{"role": "user", "content": prompt}],
        role="orchestrator",
        schema=DAGSchema,
    )

    # chat_json with schema returns model_dump() dict
    dag = parse_dag_response(raw)

    # 4. 验证DAG无环
    validate_dag_acyclic(dag)

    logger.bind(node_count=len(dag.nodes)).info("Task decomposed successfully")
    return dag

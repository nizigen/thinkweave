"""Task decomposition service that turns writing requests into a DAG."""

from __future__ import annotations

from collections import deque

from app.schemas.task import DAGSchema, VALID_DEPTHS, VALID_MODES, ValidationResult
from app.utils.llm_client import BaseLLMClient
from app.utils.logger import logger
from app.utils.prompt_loader import PromptLoader


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class TaskValidationError(Exception):
    """Raised when task input validation fails."""

    def __init__(self, issues: list[str]) -> None:
        self.issues = issues
        super().__init__(f"Task validation failed: {issues}")


class CyclicDAGError(Exception):
    """Raised when the DAG contains a cycle or an unknown dependency."""


# ---------------------------------------------------------------------------
# Input Validation
# ---------------------------------------------------------------------------

_MIN_TITLE_LENGTH = 6


def validate_task_input(title: str, mode: str, depth: str) -> ValidationResult:
    """Validate task input before invoking the LLM."""
    issues: list[str] = []
    stripped = title.strip()

    if len(stripped) < _MIN_TITLE_LENGTH:
        issues.append(
            f"Title must be at least {_MIN_TITLE_LENGTH} characters "
            f"(got {len(stripped)})"
        )

    if mode not in VALID_MODES:
        issues.append(
            f"Invalid mode '{mode}', expected one of {sorted(VALID_MODES)}"
        )

    if depth not in VALID_DEPTHS:
        issues.append(
            f"Invalid depth '{depth}', expected one of {sorted(VALID_DEPTHS)}"
        )

    return ValidationResult(ok=len(issues) == 0, issues=issues)


# ---------------------------------------------------------------------------
# DAG Parsing and Validation
# ---------------------------------------------------------------------------

def parse_dag_response(raw: dict) -> DAGSchema:
    """
    Parse and validate the DAG JSON returned by the LLM.

    Raises:
        ValueError: The DAG payload is malformed or violates structural rules.
    """
    try:
        dag = DAGSchema.model_validate(raw)
    except Exception as e:
        raise ValueError(f"DAG schema validation failed: {e}") from e

    # Node IDs must be unique.
    node_ids = [n.id for n in dag.nodes]
    if len(node_ids) != len(set(node_ids)):
        seen: set[str] = set()
        dupes = []
        for nid in node_ids:
            if nid in seen:
                dupes.append(nid)
            seen.add(nid)
        raise ValueError(f"Duplicate node IDs: {dupes}")

    # The first node must be the outline step.
    if dag.nodes[0].role != "outline":
        raise ValueError(
            f"First node must have role 'outline', got '{dag.nodes[0].role}'"
        )

    return dag


def validate_dag_acyclic(dag: DAGSchema) -> None:
    """
    Validate that the DAG is acyclic using Kahn topological sorting.

    Raises:
        CyclicDAGError: The DAG contains a cycle or references unknown nodes.
    """
    node_ids = {n.id for n in dag.nodes}

    # Every dependency must reference an existing node.
    for node in dag.nodes:
        for dep in node.depends_on:
            if dep not in node_ids:
                raise CyclicDAGError(
                    f"Node '{node.id}' depends on unknown node '{dep}'"
                )

    # Detect cycles with Kahn topological sorting.
    in_degree: dict[str, int] = {n.id: 0 for n in dag.nodes}
    adjacency: dict[str, list[str]] = {n.id: [] for n in dag.nodes}

    for node in dag.nodes:
        for dep in node.depends_on:
            adjacency[dep].append(node.id)
            in_degree[node.id] += 1

    queue = deque(nid for nid, deg in in_degree.items() if deg == 0)
    sorted_count = 0

    while queue:
        current = queue.popleft()
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
    model: str | None = None,
    max_retries: int | None = None,
    fallback_models: list[str] | None = None,
) -> DAGSchema:
    """
    Validate input, load the prompt, call the LLM, and verify the DAG.

    Args:
        title: Task title or description.
        mode: Writing mode (report/novel/custom).
        depth: Planning depth (quick/standard/deep).
        target_words: Target word count.
        llm_client: Injected LLM client, including mocks in tests.

    Returns:
        DAGSchema: A validated DAG structure.

    Raises:
        TaskValidationError: Task input is invalid.
        ValueError: The DAG structure is invalid.
        CyclicDAGError: The DAG contains a cycle.
    """
    # Validate inputs before spending tokens.
    validation = validate_task_input(title, mode, depth)
    if not validation.ok:
        raise TaskValidationError(validation.issues)

    # Load and render the decomposition prompt.
    prompt = _prompt_loader.load(
        "orchestrator",
        "decompose",
        title=title,
        mode=mode,
        depth=depth,
        target_words=str(target_words),
    )

    # Ask the LLM for the DAG JSON.
    logger.bind(title=title, mode=mode, depth=depth).info(
        "Decomposing task via LLM"
    )
    raw = await llm_client.chat_json(
        messages=[{"role": "user", "content": prompt}],
        role="orchestrator",
        model=model,
        max_retries=max_retries,
        fallback_models=fallback_models,
        schema=DAGSchema,
    )

    # chat_json with schema returns model_dump() dict.
    dag = parse_dag_response(raw)

    # Ensure the returned DAG is acyclic.
    validate_dag_acyclic(dag)

    logger.bind(node_count=len(dag.nodes)).info("Task decomposed successfully")
    return dag
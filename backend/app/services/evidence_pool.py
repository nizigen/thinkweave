"""Evidence pool seeds and task-level markdown rendering."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_PATENT_SEED_URLS = [
    "https://patentscope.wipo.int/",
    "https://worldwide.espacenet.com/",
    "https://patents.google.com/",
    "https://www.uspto.gov/patents",
    "https://www.cnipa.gov.cn/",
    "https://depatisnet.dpma.de/",
]

_OA_SEED_URLS = [
    "https://doaj.org/",
    "https://pmc.ncbi.nlm.nih.gov/",
    "https://europepmc.org/",
    "https://openalex.org/",
    "https://arxiv.org/",
    "https://zenodo.org/",
    "https://hal.science/",
    "https://plos.org/",
]

_INDUSTRY_REPORT_SEED_URLS = [
    "https://www.worldbank.org/en/publication",
    "https://www.imf.org/en/Publications",
    "https://www.oecd-ilibrary.org/",
    "https://www.weforum.org/reports/",
    "https://www.mckinsey.com/featured-insights",
    "https://www2.deloitte.com/global/en/insights.html",
    "https://www.pwc.com/gx/en/insights.html",
    "https://www.gartner.com/en/research",
]

_FICTION_REFERENCE_SEED_URLS = [
    "https://www.gutenberg.org/",
    "https://standardebooks.org/",
    "https://librivox.org/",
    "https://zh.wikisource.org/",
    "https://ctext.org/",
    "https://www.poetryfoundation.org/",
]

_REPORT_REQUIRED_EVIDENCE_CATEGORIES = [
    "market_data",
    "technical_specs",
    "case_studies",
    "counterexamples",
    "implementation_costs",
]

_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "market_data": ("market", "tam", "sam", "som", "市场", "规模", "需求", "增速", "adoption"),
    "technical_specs": ("spec", "standard", "patent", "protocol", "技术", "标准", "参数", "性能"),
    "case_studies": ("case", "deployment", "implementation", "应用", "案例", "落地", "试点"),
    "counterexamples": ("counter", "limitation", "failure", "risk", "反例", "失败", "局限", "风险"),
    "implementation_costs": ("cost", "budget", "tco", "roi", "opex", "capex", "成本", "预算", "收益"),
}


def _normalize_mode(mode: str | None) -> str:
    return str(mode or "").strip().lower()


def evidence_pool_seeds(mode: str | None = None) -> dict[str, list[str]]:
    normalized_mode = _normalize_mode(mode)
    seeds: dict[str, list[str]] = {}
    if normalized_mode == "novel":
        seeds["fiction_reference_urls"] = list(_FICTION_REFERENCE_SEED_URLS)
        seeds["oa_urls"] = list(_OA_SEED_URLS)
        return seeds
    if normalized_mode == "report":
        seeds["oa_urls"] = list(_OA_SEED_URLS)
        seeds["patent_urls"] = list(_PATENT_SEED_URLS)
        seeds["industry_report_urls"] = list(_INDUSTRY_REPORT_SEED_URLS)
        return seeds
    seeds["oa_urls"] = list(_OA_SEED_URLS)
    seeds["patent_urls"] = list(_PATENT_SEED_URLS)
    return seeds


def _host(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").strip().lower()
    except Exception:
        return ""


def classify_source_url(url: str) -> str:
    host = _host(url)
    if not host:
        return "other"
    for seed in _PATENT_SEED_URLS:
        seed_host = _host(seed)
        if seed_host and seed_host in host:
            return "patent"
    for seed in _OA_SEED_URLS:
        seed_host = _host(seed)
        if seed_host and seed_host in host:
            return "oa"
    for seed in _INDUSTRY_REPORT_SEED_URLS:
        seed_host = _host(seed)
        if seed_host and seed_host in host:
            return "industry_report"
    for seed in _FICTION_REFERENCE_SEED_URLS:
        seed_host = _host(seed)
        if seed_host and seed_host in host:
            return "fiction_reference"
    return "other"


def normalize_evidence_ledger(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        evidence_id = str(item.get("evidence_id") or "").strip()
        claim_target = str(item.get("claim_target") or "").strip()
        source_url = str(item.get("source_url") or "").strip()
        source_title = str(item.get("source_title") or "").strip()
        published_at = str(item.get("published_at") or "").strip()
        required_source_type = str(item.get("required_source_type") or "").strip()
        priority = str(item.get("priority") or "").strip()
        if not evidence_id:
            continue
        out.append(
            {
                "evidence_id": evidence_id,
                "claim_target": claim_target,
                "source_url": source_url,
                "source_title": source_title,
                "published_at": published_at,
                "required_source_type": required_source_type,
                "priority": priority,
                "source_kind": classify_source_url(source_url),
                "required_category": infer_required_category(
                    claim_target=claim_target,
                    required_source_type=required_source_type,
                    source_kind=classify_source_url(source_url),
                    source_title=source_title,
                ),
            }
        )
    return out


def required_evidence_categories(*, mode: str | None, topic: str = "") -> list[str]:
    normalized_mode = _normalize_mode(mode)
    if normalized_mode != "report":
        return []
    _ = str(topic or "").strip().lower()
    return list(_REPORT_REQUIRED_EVIDENCE_CATEGORIES)


def infer_required_category(
    *,
    claim_target: str = "",
    required_source_type: str = "",
    source_kind: str = "",
    source_title: str = "",
) -> str:
    text = " ".join(
        [
            str(claim_target or ""),
            str(required_source_type or ""),
            str(source_kind or ""),
            str(source_title or ""),
        ]
    ).lower()
    if not text.strip():
        return "unclassified"

    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return category
    return "unclassified"


def evidence_category_coverage(
    *,
    evidence_items: list[dict[str, str]],
    required_categories: list[str],
) -> dict[str, Any]:
    required = [str(item).strip() for item in required_categories if str(item).strip()]
    counts = {category: 0 for category in required}
    unclassified = 0
    for item in evidence_items:
        category = str(item.get("required_category") or "").strip()
        if not category:
            category = infer_required_category(
                claim_target=str(item.get("claim_target") or ""),
                required_source_type=str(item.get("required_source_type") or ""),
                source_kind=str(item.get("source_kind") or ""),
                source_title=str(item.get("source_title") or ""),
            )
        if category in counts:
            counts[category] += 1
        else:
            unclassified += 1
    missing = [category for category in required if counts.get(category, 0) <= 0]
    return {
        "required_categories": required,
        "category_counts": counts,
        "missing_categories": missing,
        "is_ready_for_writing": len(missing) == 0,
        "unclassified_items": unclassified,
    }


def evidence_pool_summary(
    *,
    title: str,
    mode: str | None,
    evidence_items: list[dict[str, str]],
) -> dict[str, Any]:
    required = required_evidence_categories(mode=mode, topic=title)
    coverage = evidence_category_coverage(
        evidence_items=evidence_items,
        required_categories=required,
    )
    base_counts = evidence_pool_counts(evidence_items)
    return {
        **base_counts,
        **coverage,
    }


def evidence_pool_counts(items: list[dict[str, str]]) -> dict[str, int]:
    oa = 0
    patent = 0
    industry_report = 0
    fiction_reference = 0
    with_url = 0
    for item in items:
        if str(item.get("source_url") or "").strip():
            with_url += 1
        kind = str(item.get("source_kind") or "")
        if kind == "oa":
            oa += 1
        elif kind == "patent":
            patent += 1
        elif kind == "industry_report":
            industry_report += 1
        elif kind == "fiction_reference":
            fiction_reference += 1
    return {
        "total": len(items),
        "with_url": with_url,
        "oa": oa,
        "patent": patent,
        "industry_report": industry_report,
        "fiction_reference": fiction_reference,
        "other": max(0, len(items) - oa - patent - industry_report - fiction_reference),
    }


def evidence_pool_markdown(
    *,
    task_id: uuid.UUID,
    title: str,
    evidence_items: list[dict[str, str]],
    source_policy: dict[str, Any] | None = None,
    research_keywords: list[str] | None = None,
    mode: str | None = None,
) -> str:
    counts = evidence_pool_counts(evidence_items)
    required_categories = required_evidence_categories(mode=mode, topic=title)
    coverage = evidence_category_coverage(
        evidence_items=evidence_items,
        required_categories=required_categories,
    )
    seeds = evidence_pool_seeds(mode=mode)
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%SZ")
    keyword_line = ", ".join(str(k).strip() for k in (research_keywords or []) if str(k).strip())
    policy_name = str((source_policy or {}).get("policy_name") or "").strip()
    lines: list[str] = [
        "# Evidence Pool",
        "",
        f"- Task ID: `{task_id}`",
        f"- Title: {title}",
        f"- Updated At: {now}",
        f"- Policy: {policy_name or 'n/a'}",
        f"- Mode: {_normalize_mode(mode) or 'n/a'}",
        f"- Research Keywords: {keyword_line or 'n/a'}",
        "",
        "## Source Seeds",
    ]
    for section, urls in seeds.items():
        lines.extend(["", f"### {section}"])
        for url in urls:
            lines.append(f"- {url}")

    lines.extend(
        [
            "",
            "## Pool Summary",
            "",
            f"- Total Evidence Items: {counts['total']}",
            f"- With URL: {counts['with_url']}",
            f"- OA: {counts['oa']}",
            f"- Patent: {counts['patent']}",
            f"- Industry Report: {counts['industry_report']}",
            f"- Fiction Reference: {counts['fiction_reference']}",
            f"- Other: {counts['other']}",
            "",
            "## Required Evidence Categories",
            "",
            f"- Required: {', '.join(required_categories) if required_categories else 'n/a'}",
            f"- Missing: {', '.join(coverage['missing_categories']) if coverage['missing_categories'] else 'none'}",
            f"- Ready For Writing: {'yes' if coverage['is_ready_for_writing'] else 'no'}",
            "",
            "## Candidate Evidence Ledger",
            "",
            "| evidence_id | source_kind | required_category | priority | required_source_type | published_at | source_title | source_url | claim_target |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in evidence_items:
        claim = re.sub(r"\s+", " ", str(item.get("claim_target") or "").strip())[:120]
        title_text = re.sub(r"\s+", " ", str(item.get("source_title") or "").strip())[:80]
        lines.append(
            "| {evidence_id} | {source_kind} | {required_category} | {priority} | {required_source_type} | {published_at} | {source_title} | {source_url} | {claim_target} |".format(
                evidence_id=item.get("evidence_id", ""),
                source_kind=item.get("source_kind", "other"),
                required_category=item.get("required_category", "unclassified"),
                priority=item.get("priority", ""),
                required_source_type=item.get("required_source_type", ""),
                published_at=item.get("published_at", ""),
                source_title=title_text,
                source_url=item.get("source_url", ""),
                claim_target=claim,
            )
        )
    if not evidence_items:
        lines.append("| - | - | - | - | - | - | - | - | - |")
    return "\n".join(lines).strip() + "\n"


def evidence_pool_file_path(task_id: uuid.UUID) -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "artifacts"
        / "evidence_pool"
        / f"task_{task_id}.md"
    )

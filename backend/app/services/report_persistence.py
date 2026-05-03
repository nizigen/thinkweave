"""Persist completed task reports to local filesystem."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from pathlib import Path

from app.utils.logger import logger


_REPORTS_DIR = Path(__file__).resolve().parents[2] / "reports"


def _sanitize_filename(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return "untitled"
    # Keep Chinese/Latin/number/space/_/- and replace others with "_".
    text = re.sub(r"[^\w\u4e00-\u9fff\- ]+", "_", text, flags=re.UNICODE)
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_.")
    return text[:80] or "untitled"


def persist_completed_report(
    *,
    task_id: uuid.UUID,
    title: str,
    output_text: str,
) -> Path:
    """Write completed output to backend/reports/{timestamp}_{task_id}_{title}.md."""
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = _sanitize_filename(title)
    filename = f"{timestamp}_{task_id}_{safe_title}.md"
    path = _REPORTS_DIR / filename
    # Use UTF-8 with BOM for better compatibility with Windows editors that
    # might otherwise mis-detect encoding and display mojibake.
    path.write_text(output_text or "", encoding="utf-8-sig")
    logger.bind(task_id=str(task_id), report_path=str(path)).info(
        "completed report persisted to local file"
    )
    return path

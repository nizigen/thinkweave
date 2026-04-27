"""导出路由 — GET /api/export/{task_id}/docx|pdf"""
from __future__ import annotations

import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
import io

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_session as get_db
from app.models.task import Task
from app.security.auth import require_user_id
from app.services.exporter import DocxExporter, PdfExporter, ExportNotReadyError

router = APIRouter(prefix="/api/export", tags=["export"])

_docx_exporter = DocxExporter()
_pdf_exporter = PdfExporter()


async def _get_completed_task(task_id: uuid.UUID, db: AsyncSession) -> Task:
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status not in {"completed", "done"} or not task.output_text:
        raise HTTPException(status_code=409, detail="Task not completed yet")
    return task


@router.get("/{task_id}/docx")
async def export_docx(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(require_user_id),
) -> StreamingResponse:
    task = await _get_completed_task(task_id, db)
    try:
        data = _docx_exporter.export(task)
    except ExportNotReadyError as e:
        raise HTTPException(status_code=409, detail=str(e))

    filename = quote(f"{task.title}.docx")
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.get("/{task_id}/pdf")
async def export_pdf(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(require_user_id),
) -> StreamingResponse:
    task = await _get_completed_task(task_id, db)
    try:
        data = _pdf_exporter.export(task)
    except ExportNotReadyError as e:
        raise HTTPException(status_code=409, detail=str(e))

    filename = quote(f"{task.title}.pdf")
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )

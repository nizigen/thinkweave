"""Task 管理路由"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

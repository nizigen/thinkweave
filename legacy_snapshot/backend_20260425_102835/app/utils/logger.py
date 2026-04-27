"""loguru 日志配置 — 含结构化字段支持"""

import sys

from loguru import logger

# 移除默认 handler
logger.remove()

# 控制台输出（含 {extra} 显示 bind() 绑定的结构化字段）
logger.add(
    sys.stderr,
    level="DEBUG",
    format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "{extra} | "
        "<level>{message}</level>"
    ),
)

# 文件输出（JSON格式，便于结构化查询）
logger.add(
    "logs/hierarch_{time:YYYY-MM-DD}.log",
    level="INFO",
    rotation="00:00",
    retention="7 days",
    encoding="utf-8",
    serialize=True,  # JSON序列化，包含所有 extra 字段
)

__all__ = ["logger"]

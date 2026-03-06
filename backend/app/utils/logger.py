"""loguru 日志配置"""

import sys

from loguru import logger

# 移除默认 handler
logger.remove()

# 控制台输出
logger.add(
    sys.stderr,
    level="DEBUG",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
)

# 文件输出（按天轮转，保留 7 天）
logger.add(
    "logs/hierarch_{time:YYYY-MM-DD}.log",
    level="INFO",
    rotation="00:00",
    retention="7 days",
    encoding="utf-8",
)

__all__ = ["logger"]

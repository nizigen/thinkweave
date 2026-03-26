FROM python:3.12-slim

WORKDIR /app

# 系统依赖（用于 asyncpg 编译）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 先复制依赖文件，利用 Docker 层缓存
COPY requirements.txt .
RUN uv pip install --system -r requirements.txt

# 复制应用代码
COPY . .

# 运行数据库迁移并启动
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

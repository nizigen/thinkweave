FROM node:20-bookworm-slim AS node_runtime

FROM python:3.12-slim

WORKDIR /app

# 从 Node 官方镜像注入 npx 运行时，避免 apt 源波动影响构建
COPY --from=node_runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node_runtime /usr/local/bin/npm /usr/local/bin/npm
COPY --from=node_runtime /usr/local/bin/npx /usr/local/bin/npx
COPY --from=node_runtime /usr/local/lib/node_modules /usr/local/lib/node_modules

# 先复制依赖文件，利用 Docker 层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 启动应用；数据库迁移在部署阶段显式执行
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

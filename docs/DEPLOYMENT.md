# 部署指南

## 环境要求

- Docker >= 24.0
- Docker Compose >= 2.20
- 至少 4GB 内存（LLM 并发调用）

---

## 快速启动（开发环境）

```bash
# 1. 启动基础设施（PostgreSQL + Redis）
docker compose up -d postgres redis

# 2. 创建并激活 Python 虚拟环境
cd backend
uv venv --python 3.12
source .venv/bin/activate  # Windows: .venv\Scripts\activate
uv pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 API Key

# 4. 运行数据库迁移
alembic upgrade head

# 5. 启动后端
uvicorn app.main:app --reload --port 8000

# 6. 启动前端（新终端）
cd ../frontend
npm install
npm run dev
```

访问：http://localhost:5173

---

## 生产部署

```bash
# 1. 复制并配置环境变量
cp backend/.env.example backend/.env
# 编辑 backend/.env，设置生产参数

# 2. 启动所有服务
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# 3. 查看日志
docker compose logs -f backend
```

访问：http://localhost（前端）| http://localhost:8000（API）

---

## 环境变量说明

### 数据库

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `POSTGRES_URL` | `postgresql+asyncpg://agent_user:agent_pass@localhost:15432/agent_db` | PostgreSQL 连接串（asyncpg 驱动） |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 连接串 |

### LLM 提供商

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OPENAI_API_KEY` | *(必填)* | OpenAI API Key |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI 兼容端点（可替换为 Azure/代理） |
| `DEEPSEEK_API_KEY` | *(可选)* | DeepSeek API Key，用于降级 fallback |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com/v1` | DeepSeek 端点 |
| `DEFAULT_MODEL` | `gpt-4o` | 默认主模型 |

### 认证

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `TASK_AUTH_TOKENS` | *(必填)* | Bearer Token 映射，格式：`token1:user1,token2:user2` |
| `ADMIN_USER_IDS` | *(可选)* | 管理员用户 ID 列表，逗号分隔 |

### 应用配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `APP_HOST` | `0.0.0.0` | 监听地址 |
| `APP_PORT` | `8000` | 监听端口 |
| `DEBUG` | `false` | 调试模式（生产环境设为 false） |
| `CORS_ALLOW_ORIGINS` | `http://localhost:5173` | 允许的 CORS 来源，多个用逗号分隔 |
| `TASK_CREATE_RATE_LIMIT_PER_MINUTE` | `100` | 每用户每分钟任务创建限制 |
| `DISABLE_RATE_LIMIT` | `false` | 禁用限流（仅测试用，生产不要开启） |

### 并发控制

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MAX_CONCURRENT_LLM_CALLS` | `5` | 最大并发 LLM 调用数 |
| `MAX_CONCURRENT_WRITERS` | `3` | 最大并发写作 Agent 数 |
| `LLM_MAX_RETRIES` | `3` | LLM 调用最大重试次数 |
| `LLM_RETRY_BASE_DELAY` | `1.0` | 重试基础延迟（秒，指数退避） |

### Memory 层（可选）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MEMORY_ENABLED` | `false` | 启用 cognee 记忆层（需要 Neo4j + Qdrant） |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j 连接地址 |
| `NEO4J_USER` | `neo4j` | Neo4j 用户名 |
| `NEO4J_PASSWORD` | *(必填)* | Neo4j 密码 |
| `QDRANT_URL` | `http://localhost:6333` | Qdrant 向量数据库地址 |
| `QDRANT_API_KEY` | *(可选)* | Qdrant API Key |

### RAG（可选）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `RAG_ENABLED` | `false` | 启用 pgvector RAG |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | 向量嵌入模型 |
| `EMBEDDING_DIMENSIONS` | `1536` | 嵌入维度 |

### WebSocket

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `WS_ALLOW_QUERY_TOKEN_FALLBACK` | `false` | 允许通过 URL query 参数传 Token（不推荐生产使用） |

---

## 健康检查

```bash
# 后端
curl http://localhost:8000/health

# 数据库
docker compose exec postgres pg_isready -U agent_user -d agent_db

# Redis
docker compose exec redis redis-cli ping
```

---

## 数据库迁移

```bash
# 生成新迁移（修改 models 后）
alembic revision --autogenerate -m "描述"

# 应用迁移
alembic upgrade head

# 回滚一步
alembic downgrade -1
```

---

## 生产安全清单

- [ ] `DEBUG=false`
- [ ] `TASK_AUTH_TOKENS` 使用强随机 token（`openssl rand -hex 32`）
- [ ] `CORS_ALLOW_ORIGINS` 设置为实际域名
- [ ] `DISABLE_RATE_LIMIT=false`
- [ ] PostgreSQL/Redis 不对外暴露端口（移除 ports 映射）
- [ ] 设置 Nginx HTTPS（Let's Encrypt 或反向代理）
- [ ] 定期备份 PostgreSQL 数据卷

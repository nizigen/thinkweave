# Hierarch — 层级化 Agent 编排与长文本控制系统

构建一个支持层级化多 Agent 协作的智能编排平台，核心能力是将复杂任务（如生成万字技术报告、长篇小说）分解为结构化子任务 DAG，由多层 Agent 协同执行，最终输出结构完整、内容连贯的长文本。

## 架构概览

```
┌─────────────────────────────────┐
│  Layer 0  Orchestrator Agent    │  任务分解 / 全局协调 / DAG 生成
├─────────────────────────────────┤
│  Layer 1  Manager Agent         │  策略规划 / 资源调度 / 质量控制
├─────────────────────────────────┤
│  Layer 2  Execution Agents      │  Outline / Writer / Reviewer / Consistency
└─────────────────────────────────┘
         ▼ 通信：Redis Streams (Consumer Group)
         ▼ 持久化：PostgreSQL
```

### 长文本写作流程

```
INIT → OUTLINE → OUTLINE_REVIEW → WRITING(并行) → REVIEWING → CONSISTENCY → DONE
                                      ↑_______________|  审查不通过，最多 3 次
                                      ↑__________________________|  一致性不通过，最多 2 次
```

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.13 · FastAPI · SQLAlchemy 2.0 (async) · Pydantic v2 |
| 前端 | React 18 · TypeScript · Vite · Ant Design 5 · @antv/g6 · Zustand |
| 数据库 | PostgreSQL 15.8 · Redis 7.4 |
| LLM | OpenAI GPT-4o · DeepSeek V3.2（角色级模型分配 + 自动降级） |

## 前置要求

- Python 3.13+
- Node.js 20 LTS
- Docker Desktop（运行 PostgreSQL + Redis）
- uv（Python 包管理，可选 conda）

## 快速开始

### 1. 启动数据库

```bash
docker compose up -d
```

这会启动 PostgreSQL 15.8 和 Redis 7.4，端口分别映射到 `5432` 和 `6379`。

### 2. 配置后端

```bash
cd backend

# 创建虚拟环境并安装依赖
uv venv --python 3.13 .venv
# Windows (Git Bash)
source .venv/Scripts/activate
# Linux / macOS
# source .venv/bin/activate

uv pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入你的 API Key：
#   OPENAI_API_KEY=sk-xxx
#   DEEPSEEK_API_KEY=sk-xxx
```

### 3. 配置前端

```bash
cd frontend
npm install
```

### 4. 运行

```bash
# 终端 1 — 后端
cd backend
source .venv/Scripts/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 终端 2 — 前端
cd frontend
npm run dev
```

后端 API：http://localhost:8000  
前端页面：http://localhost:5173

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `POSTGRES_URL` | PostgreSQL 连接串 | `postgresql+asyncpg://agent_user:agent_pass@localhost:5432/agent_db` |
| `REDIS_URL` | Redis 连接串 | `redis://localhost:6379/0` |
| `OPENAI_API_KEY` | OpenAI API 密钥 | — |
| `OPENAI_BASE_URL` | OpenAI API 地址 | `https://api.openai.com/v1` |
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 | — |
| `DEEPSEEK_BASE_URL` | DeepSeek API 地址 | `https://api.deepseek.com/v1` |
| `DEFAULT_MODEL` | 默认 LLM 模型 | `gpt-4o` |

## 项目结构

```
hierarch/
├── backend/
│   ├── app/
│   │   ├── agents/        # Agent 实现（Orchestrator / Manager / Writer 等）
│   │   ├── models/        # SQLAlchemy ORM 模型
│   │   ├── routers/       # FastAPI 路由
│   │   ├── schemas/       # Pydantic 请求/响应模型
│   │   ├── services/      # 核心服务（FSM / DAG调度 / Redis通信 / 心跳）
│   │   └── utils/         # 工具（LLM统一客户端 / 日志）
│   ├── migrations/        # Alembic 数据库迁移
│   └── tests/
├── frontend/
│   └── src/
├── docs/                  # 规范文档（PRD / 技术栈 / 实施计划等）
└── docker-compose.yml     # PostgreSQL + Redis
```

## License

MIT

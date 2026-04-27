#!/bin/bash
# Agentic Nexus 自动启动+测试脚本
set -e
LOG=/root/github/agentic-nexus/logs/autotest.log
mkdir -p /root/github/agentic-nexus/logs
exec > >(tee -a $LOG) 2>&1

echo '========================================='
echo "[$(date)] 启动自动化测试流程"
echo '========================================='

UV=/root/.local/bin/uv
PROJ=/root/github/agentic-nexus
BACKEND=$PROJ/backend
FRONTEND=$PROJ/frontend

# 1. 检查 Docker 服务
echo '[STEP 1] 检查 Docker 服务...'
docker ps --format 'table {{.Names}}\	{{.Status}}'

# 2. 运行数据库迁移
echo '[STEP 2] 运行 Alembic 迁移...'
cd $BACKEND
$UV run --python 3.12 alembic upgrade head 2>&1
echo '迁移完成'

# 3. 启动后端
echo '[STEP 3] 启动后端 uvicorn...'
pkill -f 'uvicorn app.main' 2>/dev/null || true
$UV run --python 3.12 uvicorn app.main:app --host 0.0.0.0 --port 8000 > $PROJ/logs/backend.log 2>&1 &
BACKEND_PID=$!
echo "后端 PID: $BACKEND_PID"

# 等后端启动
echo '等待后端启动...'
for i in $(seq 1 30); do
  if curl -s http://localhost:8000/docs > /dev/null 2>&1; then
    echo '后端已就绪'
    break
  fi
  sleep 1
done

# 4. 启动前端
echo '[STEP 4] 启动前端...'
cd $FRONTEND
npm install --silent 2>&1 | tail -3
pkill -f 'vite' 2>/dev/null || true
npm run dev > $PROJ/logs/frontend.log 2>&1 &
FRONTEND_PID=$!
echo "前端 PID: $FRONTEND_PID"
sleep 5

# 5. 测试所有 API 端点
echo '[STEP 5] 测试 API 端点...'

test_api() {
  local method=$1
  local url=$2
  local data=$3
  local desc=$4
  echo -n "  [$method] $url ($desc): "
  if [ -n "$data" ]; then
    resp=$(curl -s -w "\
%{http_code}" -X $method http://localhost:8000$url -H 'Content-Type: application/json' -d "$data" 2>&1)
  else
    resp=$(curl -s -w "\
%{http_code}" -X $method http://localhost:8000$url 2>&1)
  fi
  code=$(echo "$resp" | tail -1)
  body=$(echo "$resp" | head -1)
  echo "HTTP $code"
  if [[ $code -ge 400 ]]; then
    echo "    ERROR BODY: $body"
  fi
}

# OpenAPI/docs
test_api GET /docs '' 'Swagger UI'
test_api GET /openapi.json '' 'OpenAPI schema'

# Agents
test_api GET /agents '' '列出所有 agents'
test_api POST /agents '{"name":"test-agent","role":"orchestrator","layer":0,"capabilities":[],"model_config":{}}' '创建 agent'

# Tasks
test_api GET /tasks '' '列出所有 tasks'
test_api POST /tasks '{"title":"test task","description":"测试任务","agent_id":null}' '创建 task'

# Nodes
test_api GET /nodes '' '列出所有 nodes'

# Outline
test_api GET /outline '' '大纲列表'

# Export
test_api GET /export '' '导出列表'

echo '[STEP 6] 检查后端日志中的错误...'
echo '--- 后端日志最后 30 行 ---'
tail -30 $PROJ/logs/backend.log

echo '[STEP 7] 运行 pytest...'
cd $BACKEND
$UV run --python 3.12 pytest tests/ -v --tb=short 2>&1 | tail -50

echo '========================================='
echo "[$(date)] 测试完成"
echo '========================================='

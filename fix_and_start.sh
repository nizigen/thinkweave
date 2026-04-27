#!/bin/bash
# 一次性修复所有问题并启动服务
LOG=/root/github/agentic-nexus/logs/fix_and_start.log
mkdir -p /root/github/agentic-nexus/logs

{
echo "======================================="
echo "[$(date '+%H:%M:%S')] 开始修复和启动"
echo "======================================="

UV=/root/.local/bin/uv
BACKEND=/root/github/agentic-nexus/backend
FRONTEND=/root/github/agentic-nexus/frontend
LOGDIR=/root/github/agentic-nexus/logs

# Step 1: 安装 psycopg2-binary 到 venv
echo "[$(date '+%H:%M:%S')] [1/7] 安装 psycopg2-binary..."
cd $BACKEND
$UV pip install psycopg2-binary --python 3.12 2>&1
echo "EXIT: $?"

# Step 2: 安装所有依赖
echo "[$(date '+%H:%M:%S')] [2/7] 安装 requirements.txt..."
$UV pip install -r requirements.txt --python 3.12 2>&1 | tail -5
echo "EXIT: $?"

# Step 3: Alembic 迁移
echo "[$(date '+%H:%M:%S')] [3/7] 运行 Alembic 迁移..."
cd $BACKEND
$UV run --python 3.12 alembic upgrade head 2>&1
echo "MIGRATION EXIT: $?"

# Step 4: 启动后端
echo "[$(date '+%H:%M:%S')] [4/7] 启动后端..."
pkill -f 'uvicorn app.main' 2>/dev/null || true
sleep 1
$UV run --python 3.12 uvicorn app.main:app --host 0.0.0.0 --port 8000 > $LOGDIR/backend.log 2>&1 &
BACKEND_PID=$!
echo "后端 PID: $BACKEND_PID"

# 等待后端就绪
echo "等待后端..."
for i in $(seq 1 20); do
  if curl -sf http://localhost:8000/docs > /dev/null 2>&1; then
    echo "[$(date '+%H:%M:%S')] 后端就绪! (${i}s)"
    break
  fi
  if [ $i -eq 20 ]; then
    echo "[$(date '+%H:%M:%S')] 后端启动超时，查看日志:"
    cat $LOGDIR/backend.log
  fi
  sleep 1
done

# Step 5: 启动前端
echo "[$(date '+%H:%M:%S')] [5/7] 启动前端..."
cd $FRONTEND
pkill -f 'vite' 2>/dev/null || true
sleep 1
npm run dev > $LOGDIR/frontend.log 2>&1 &
FRONTEND_PID=$!
echo "前端 PID: $FRONTEND_PID"
sleep 5

# Step 6: API 测试
echo "[$(date '+%H:%M:%S')] [6/7] 测试 API 端点..."
BASE=http://localhost:8000

check() {
  local m=$1 u=$2 d=$3 desc=$4
  if [ -n "$d" ]; then
    code=$(curl -s -o /tmp/api_resp.json -w "%{http_code}" -X $m $BASE$u -H 'Content-Type: application/json' -d "$d")
  else
    code=$(curl -s -o /tmp/api_resp.json -w "%{http_code}" -X $m $BASE$u)
  fi
  body=$(cat /tmp/api_resp.json 2>/dev/null | head -c 300)
  if [[ $code -ge 200 && $code -lt 300 ]]; then
    echo "  OK  [$code] $m $u ($desc)"
  elif [[ $code -eq 422 ]]; then
    echo "  422 [$code] $m $u ($desc) -- 请求体验证失败"
    echo "       $body"
  else
    echo "  ERR [$code] $m $u ($desc)"
    echo "       $body"
  fi
}

check GET /docs '' 'Swagger UI'
check GET /openapi.json '' 'OpenAPI schema'
check GET /agents '' '获取所有 agents'
check GET /tasks '' '获取所有 tasks'
check GET /nodes '' '获取所有 nodes'
check GET /outline '' '获取大纲列表'
check GET /export '' '导出列表'

# 尝试创建 Agent（根据实际模型调整字段）
check POST /agents '{"name":"test-orchestrator","role":"orchestrator","layer":0,"capabilities":[],"model_config":{"model":"gpt-4o"}}' '创建 agent'

# 获取 openapi schema 来发现真实字段
echo "--- OpenAPI schema (agents) ---"
curl -s http://localhost:8000/openapi.json | python3 -c "
import json,sys
d=json.load(sys.stdin)
paths=d.get('paths',{})
for p,v in paths.items():
    print(f'  {p}: {list(v.keys())}')
" 2>/dev/null || echo '(python3 parse failed)'

# Step 7: pytest
echo "[$(date '+%H:%M:%S')] [7/7] 运行 pytest..."
cd $BACKEND
$UV run --python 3.12 pytest tests/ -v --tb=short -x 2>&1 | tail -60

echo "======================================="
echo "[$(date '+%H:%M:%S')] 完成"
echo "后端日志: $LOGDIR/backend.log"
echo "前端日志: $LOGDIR/frontend.log"
echo "======================================="
} 2>&1 | tee $LOG

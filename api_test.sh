#!/bin/bash
# 用正确路径测试所有 API 端点
LOG=/root/github/agentic-nexus/logs/api_test.log
mkdir -p /root/github/agentic-nexus/logs

{
echo "======================================="
echo "[$(date '+%H:%M:%S')] API 测试开始"
echo "======================================="

BASE=http://localhost:8000

check() {
  local m=$1 u=$2 d=$3 desc=$4
  if [ -n "$d" ]; then
    code=$(curl -s -o /tmp/api_resp.json -w "%{http_code}" -X $m $BASE$u -H 'Content-Type: application/json' -d "$d" 2>/dev/null)
  else
    code=$(curl -s -o /tmp/api_resp.json -w "%{http_code}" -X $m $BASE$u 2>/dev/null)
  fi
  body=$(cat /tmp/api_resp.json 2>/dev/null)
  if [[ $code -ge 200 && $code -lt 300 ]]; then
    echo "  OK  [$code] $m $u ($desc)"
    echo "       $(echo $body | head -c 200)"
  else
    echo "  ERR [$code] $m $u ($desc)"
    echo "       $(echo $body | head -c 300)"
  fi
}

echo "--- 健康检查 ---"
check GET /health '' '健康检查'

echo "--- Agents API ---"
check GET /api/agents '' '列出所有 agents'
check POST /api/agents '{"name":"test-orchestrator","role":"orchestrator","layer":0,"capabilities":[],"model_config":{"model":"gpt-4o"}}' '创建 agent'

# 获取刚创建的 agent ID
AGENT_ID=$(curl -s $BASE/api/agents | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['id'] if d else '')" 2>/dev/null)
echo "  Agent ID: $AGENT_ID"

if [ -n "$AGENT_ID" ]; then
  check GET /api/agents/$AGENT_ID '' "获取 agent $AGENT_ID"
  check PATCH /api/agents/$AGENT_ID/status '{"status":"idle"}' '更新 agent 状态'
fi

echo "--- Tasks API ---"
check GET /api/tasks '' '列出所有 tasks'

# 获取 tasks 的真实字段
echo "  Tasks schema:"
curl -s $BASE/openapi.json | python3 -c "
import json,sys
d=json.load(sys.stdin)
comps=d.get('components',{}).get('schemas',{})
for name,schema in comps.items():
    if 'Task' in name and 'Create' in name:
        print(f'  {name}: {list(schema.get(\"properties\",{}).keys())}')
" 2>/dev/null

# 创建 task（根据 schema）
check POST /api/tasks '{"topic":"测试：AI在医疗领域的应用","mode":"standard","model_config":{"orchestrator_model":"gpt-4o","manager_model":"deepseek-chat","outline_model":"gpt-4o","writer_model":"deepseek-chat","reviewer_model":"gpt-4o","consistency_model":"gpt-4o"}}' '创建 task'

# 获取 task ID
TASK_ID=$(curl -s $BASE/api/tasks | python3 -c "import json,sys; d=json.load(sys.stdin); items=d.get('tasks',d) if isinstance(d,dict) else d; print(items[0]['id'] if items else '')" 2>/dev/null)
echo "  Task ID: $TASK_ID"

if [ -n "$TASK_ID" ]; then
  check GET /api/tasks/$TASK_ID '' "获取 task $TASK_ID 详情"
  check GET /api/tasks/$TASK_ID/outline '' "获取 task 大纲"
fi

echo "--- Export API ---"
if [ -n "$TASK_ID" ]; then
  check GET /api/export/$TASK_ID/docx '' 'DOCX 导出'
  check GET /api/export/$TASK_ID/pdf '' 'PDF 导出'
else
  echo "  (跳过 export，无 task ID)"
fi

echo "--- WebSocket ---"
echo "  (WebSocket 需要前端测试，此处跳过)"

echo "--- 后端日志检查 ---"
echo "最近错误:"
grep -i 'error\|exception\|traceback' /root/github/agentic-nexus/logs/backend.log | tail -20 || echo '  无错误'

echo "======================================="
echo "[$(date '+%H:%M:%S')] API 测试完成"
echo "======================================="
} 2>&1 | tee $LOG

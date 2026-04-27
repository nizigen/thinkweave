#!/bin/bash
# 完整 API 测试 - 带正确认证
TOKEN="test-token-123"
BASE="http://localhost:8000"
AUTH="Authorization: Bearer $TOKEN"
LOG=/root/github/agentic-nexus/logs/full_api_test.log

{
echo "======================================="
echo "[$(date '+%H:%M:%S')] 完整 API 测试"
echo "======================================="

OK=0; FAIL=0; WARN=0

check() {
  local m=$1 u=$2 d=$3 desc=$4 expect=$5
  expect=${expect:-200}
  if [ -n "$d" ]; then
    code=$(curl -s -o /tmp/ar.json -w "%{http_code}" -X $m "$BASE$u" -H "$AUTH" -H 'Content-Type: application/json' -d "$d" 2>/dev/null)
  else
    code=$(curl -s -o /tmp/ar.json -w "%{http_code}" -X $m "$BASE$u" -H "$AUTH" 2>/dev/null)
  fi
  body=$(cat /tmp/ar.json 2>/dev/null)
  if [[ $code -eq $expect || ($expect -eq 200 && $code -ge 200 && $code -lt 300) ]]; then
    echo "  OK  [$code] $m $u — $desc"
    echo "       $(echo $body | head -c 200)"
    OK=$((OK+1))
  elif [[ $code -ge 400 && $code -lt 500 ]]; then
    echo "  WARN[$code] $m $u — $desc"
    echo "       $(echo $body | head -c 300)"
    WARN=$((WARN+1))
  else
    echo "  ERR [$code] $m $u — $desc"
    echo "       $(echo $body | head -c 300)"
    FAIL=$((FAIL+1))
  fi
}

echo "--- 健康 ---"
check GET /health '' '健康检查'

echo "--- Agents ---"
check GET /api/agents '' '列出 agents'

# 创建 agent
check POST /api/agents \
  '{"name":"test-orchestrator","role":"orchestrator","layer":0,"capabilities":["task_decompose"],"model_config":{"model":"gpt-4o"}}' \
  '创建 orchestrator agent' 201

# 获取第一个 agent
AGENT_ID=$(curl -s -H "$AUTH" $BASE/api/agents | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['id'] if d else '')" 2>/dev/null)
echo "  使用 Agent ID: $AGENT_ID"

if [ -n "$AGENT_ID" ]; then
  check GET /api/agents/$AGENT_ID '' "获取单个 agent"
  check PATCH /api/agents/$AGENT_ID/status '{"status":"idle"}' '更新 agent 状态'
fi

echo "--- Tasks ---"
check GET /api/tasks '' '列出 tasks'

# 查看 TaskCreate schema
echo "  TaskCreate fields:"
curl -s $BASE/openapi.json | python3 -c "
import json,sys
d=json.load(sys.stdin)
s=d.get('components',{}).get('schemas',{})
for n,v in s.items():
    if 'TaskCreate' in n:
        props=v.get('properties',{})
        req=v.get('required',[])
        print(f'  required={req}')
        for k,p in props.items():
            t=p.get('type','?')
            print(f'    {k}: {t}')
" 2>/dev/null

# 创建 task
check POST /api/tasks \
  '{"title":"测试任务：AI的未来","mode":"standard","depth":3,"target_words":5000}' \
  '创建 task' 201

# 获取 task
TASK_RESP=$(curl -s -H "$AUTH" $BASE/api/tasks)
TASK_ID=$(echo $TASK_RESP | python3 -c "
import json,sys
d=json.load(sys.stdin)
if isinstance(d, list): items=d
else: items=d.get('tasks', d.get('items',[]))
print(items[0]['id'] if items else '')
" 2>/dev/null)
echo "  使用 Task ID: $TASK_ID"

if [ -n "$TASK_ID" ]; then
  check GET /api/tasks/$TASK_ID '' "获取 task 详情"
  check GET /api/tasks/$TASK_ID/outline '' "获取 task 大纲"

  echo "--- Task 控制 ---"
  check POST /api/tasks/$TASK_ID/control/pause '' '暂停 task' 200
  check POST /api/tasks/$TASK_ID/control/resume '' '恢复 task' 200

  echo "--- Export ---"
  check GET /api/export/$TASK_ID/docx '' 'DOCX 导出'
  check GET /api/export/$TASK_ID/pdf '' 'PDF 导出'
fi

echo ""
echo "=== 测试汇总 ==="
echo "  OK:   $OK"
echo "  WARN: $WARN (4xx 客户端错误，需检查)"
echo "  FAIL: $FAIL (5xx 服务器错误，需修复)"
echo ""

echo "--- 后端日志 (最近30行) ---"
tail -30 /root/github/agentic-nexus/logs/backend.log

echo "======================================="
echo "[$(date '+%H:%M:%S')] 测试完成"
echo "======================================="
} 2>&1 | tee $LOG

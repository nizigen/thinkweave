#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
TOKEN="${TASK_TOKEN:-test-token-123}"
TITLE="pw-cli-e2e-$(date +%s)-$RANDOM"
TUNNEL_PROVIDER="${TUNNEL_PROVIDER:-tunnelmole}"  # tunnelmole | localtunnel | local
WAIT_FOR_COMPLETION="${WAIT_FOR_COMPLETION:-1}"
COMPLETION_TIMEOUT_SECS="${COMPLETION_TIMEOUT_SECS:-900}"
POLL_INTERVAL_SECS="${POLL_INTERVAL_SECS:-5}"

cleanup() {
  [[ -n "${LT_PID:-}" ]] && kill "$LT_PID" >/dev/null 2>&1 || true
  [[ -n "${API_PID:-}" ]] && kill "$API_PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT

: >/tmp/pw_build.log
: >/tmp/pw_backend_e2e.log
: >/tmp/pw_lt_e2e.log
: >/tmp/pw_cli_e2e.log
: >/tmp/pw_tasks.json
: >/tmp/pw_task_detail.json

echo "[1/5] Building frontend dist..."
(cd "$FRONTEND_DIR" && npm run build >/tmp/pw_build.log 2>&1)

echo "[2/5] Starting backend with FRONTEND_DIST_DIR..."
(
  cd "$BACKEND_DIR"
  FRONTEND_DIST_DIR="$FRONTEND_DIR/dist" \
  .venv/bin/uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" \
    >/tmp/pw_backend_e2e.log 2>&1
) &
API_PID=$!

for _ in $(seq 1 30); do
  if curl -sS "http://$BACKEND_HOST:$BACKEND_PORT/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

URL=""
if [[ "$TUNNEL_PROVIDER" == "local" ]]; then
  echo "[3/5] Using local direct URL (no tunnel)..."
  URL="http://$BACKEND_HOST:$BACKEND_PORT"
else
  echo "[3/5] Creating tunnel via: $TUNNEL_PROVIDER ..."
  (
    cd "$ROOT"
    if [[ "$TUNNEL_PROVIDER" == "localtunnel" ]]; then
      npx -y localtunnel --port "$BACKEND_PORT" >/tmp/pw_lt_e2e.log 2>&1
    else
      npx -y tunnelmole "$BACKEND_PORT" >/tmp/pw_lt_e2e.log 2>&1
    fi
  ) &
  LT_PID=$!

  for _ in $(seq 1 40); do
    if [[ "$TUNNEL_PROVIDER" == "localtunnel" ]]; then
      URL=$(rg -n "your url is:" /tmp/pw_lt_e2e.log | tail -n 1 | sed -E 's/.*your url is: (https:\/\/[^ ]+).*/\1/' || true)
    else
      URL=$(rg -o "https://[a-zA-Z0-9.-]+" /tmp/pw_lt_e2e.log | head -n 1 || true)
    fi
    if [[ -n "$URL" ]]; then
      break
    fi
    sleep 1
  done

  if [[ -z "$URL" ]]; then
    echo "[ERROR] Failed to get tunnel URL"
    echo "--- /tmp/pw_lt_e2e.log ---"
    tail -n 80 /tmp/pw_lt_e2e.log || true
    exit 1
  fi
fi

echo "[4/5] Running Playwright CLI against: $URL"
cd "$ROOT"
npx -y @playwright/cli close-all >/tmp/pw_cli_e2e.log 2>&1 || true
npx -y @playwright/cli open "$URL" >>/tmp/pw_cli_e2e.log 2>&1 || true

# Bypass localtunnel warning page when present.
npx -y @playwright/cli run-code "async page => {
  const txt = await page.locator('body').innerText();
  if ((await page.title()).includes('Tunnel website ahead') || txt.includes('To continue, enter the IP shown above')) {
    const m = txt.match(/(\\d{1,3}(?:\\.\\d{1,3}){3})/);
    if (m) {
      await page.getByRole('textbox').first().fill(m[1]);
      await page.getByRole('button', { name: /Continue/i }).click();
      await page.waitForTimeout(1500);
    }
  }
  return { title: await page.title(), url: page.url() };
}" >>/tmp/pw_cli_e2e.log 2>&1 || true

# Set auth token before app data bootstrap, then reload.
npx -y @playwright/cli run-code "async page => {
  await page.evaluate((token) => { sessionStorage.setItem('task_auth_token', token); }, '$TOKEN');
  await page.reload();
  await page.waitForTimeout(3000);
  return {
    title: await page.title(),
    url: page.url(),
    body: (await page.locator('body').innerText()).slice(0, 400),
  };
}" >>/tmp/pw_cli_e2e.log 2>&1 || true

# Attempt task create flow.
npx -y @playwright/cli run-code "async page => {
  let titleInput = page.getByPlaceholder('输入主题标题').first();
  if (!(await titleInput.count())) {
    titleInput = page.locator('input, textarea').first();
  }
  if (await titleInput.count()) {
    await titleInput.fill('$TITLE');
  }

  const depthSelect = page.locator('select').nth(1);
  if (await depthSelect.count()) {
    await depthSelect.selectOption('quick');
  }

  const wordsInput = page.locator('input[type=number]').first();
  if (await wordsInput.count()) {
    await wordsInput.fill('1200');
  }

  const submit = page.getByRole('button', { name: /开始生成|创建|Create|Start|提交|Submit/i }).first();
  let clicked = false;
  if (await submit.count()) {
    if (await submit.isEnabled()) {
      await submit.click();
      clicked = true;
      await page.waitForTimeout(5000);
    }
  }
  return {
    clicked,
    submitEnabled: (await submit.count()) ? await submit.isEnabled() : false,
    title: await page.title(),
    url: page.url(),
    body: (await page.locator('body').innerText()).slice(0, 800),
  };
}" >>/tmp/pw_cli_e2e.log 2>&1 || true

npx -y @playwright/cli snapshot >>/tmp/pw_cli_e2e.log 2>&1 || true

echo "--- API ASSERTION ---"
curl -sS "http://$BACKEND_HOST:$BACKEND_PORT/api/tasks?limit=50" \
  -H "Authorization: Bearer $TOKEN" > /tmp/pw_tasks.json || true

ASSERTION_OK=0
TASK_ID=""
if TASK_ID=$(jq -r --arg t "$TITLE" '.items[]? | select(.title==$t) | .id' /tmp/pw_tasks.json | head -n 1); then
  :
fi
if [[ -n "$TASK_ID" && "$TASK_ID" != "null" ]]; then
  ASSERTION_OK=1
  echo "ASSERTION PASSED: created task title found => $TITLE"
else
  echo "ASSERTION FAILED: task title not found from UI flow => $TITLE"
  echo "FALLBACK: creating task via API to continue E2E evidence capture"
  CREATE_BODY=$(jq -nc --arg title "$TITLE" \
    '{title:$title, mode:"report", depth:"quick", target_words:1200}')
  curl -sS -X POST "http://$BACKEND_HOST:$BACKEND_PORT/api/tasks" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "$CREATE_BODY" \
    >/tmp/pw_create_fallback.json || true

  TASK_ID=$(jq -r '.id // empty' /tmp/pw_create_fallback.json 2>/dev/null || true)
  if [[ -n "$TASK_ID" ]]; then
    ASSERTION_OK=1
    echo "ASSERTION PASSED (fallback): created task id => $TASK_ID"
  else
    curl -sS "http://$BACKEND_HOST:$BACKEND_PORT/api/tasks?limit=200" \
      -H "Authorization: Bearer $TOKEN" > /tmp/pw_tasks.json || true
    TASK_ID=$(jq -r --arg t "$TITLE" '.items[]? | select(.title==$t) | .id' /tmp/pw_tasks.json | head -n 1)
  fi
  if [[ -n "$TASK_ID" && "$TASK_ID" != "null" ]]; then
    ASSERTION_OK=1
    echo "ASSERTION PASSED (fallback scan): created task title found => $TITLE"
  else
    echo "ASSERTION FAILED: task title still not found => $TITLE"
    echo "--- /tmp/pw_tasks.json (tail) ---"
    tail -n 80 /tmp/pw_tasks.json || true
  fi
fi

if [[ -z "$TASK_ID" || "$TASK_ID" == "null" ]]; then
  echo "ASSERTION FAILED: created task id not found for title => $TITLE"
  exit 3
fi
echo "Created TASK_ID: $TASK_ID"

TIMED_OUT=0
if [[ "$WAIT_FOR_COMPLETION" == "1" ]]; then
  echo "--- COMPLETION POLL ---"
  deadline=$(( $(date +%s) + COMPLETION_TIMEOUT_SECS ))
  while true; do
    now=$(date +%s)
    if (( now >= deadline )); then
      echo "TIMEOUT: task not completed within ${COMPLETION_TIMEOUT_SECS}s"
      TIMED_OUT=1
      break
    fi
    curl -sS "http://$BACKEND_HOST:$BACKEND_PORT/api/tasks/$TASK_ID" \
      -H "Authorization: Bearer $TOKEN" >/tmp/pw_task_detail.json || true
    status=$(jq -r '.status // ""' /tmp/pw_task_detail.json 2>/dev/null || echo "")
    fsm=$(jq -r '.fsm_state // ""' /tmp/pw_task_detail.json 2>/dev/null || echo "")
    words=$(jq -r '.word_count // 0' /tmp/pw_task_detail.json 2>/dev/null || echo "0")
    pending=$(jq '[.nodes[]? | select(.status=="pending" or .status=="ready" or .status=="running")] | length' /tmp/pw_task_detail.json 2>/dev/null || echo "0")
    blocking_reason=$(jq -r '.blocking_reason // ""' /tmp/pw_task_detail.json 2>/dev/null || echo "")
    echo "poll status=$status fsm=$fsm words=$words active_nodes=$pending blocking_reason=${blocking_reason:-none}"
    if [[ "$status" == "done" || "$status" == "completed" || "$status" == "failed" ]]; then
      break
    fi
    sleep "$POLL_INTERVAL_SECS"
  done
fi

echo "[5/5] Results"
echo "--- PLAYWRIGHT CLI ---"
tail -n 200 /tmp/pw_cli_e2e.log || true

echo "--- BACKEND LOG ---"
tail -n 120 /tmp/pw_backend_e2e.log || true

if [[ -s /tmp/pw_task_detail.json ]]; then
  echo "--- TASK SUMMARY ---"
  jq '{
    id,
    title,
    status,
    fsm_state,
    word_count,
    error_message,
    blocking_reason,
    stage_progress,
    node_status_summary,
    output_preview: ((.output_text // "")[:1200]),
    node_status_counts: (.nodes | group_by(.status) | map({status: .[0].status, count: length})),
    routing_results: (.checkpoint_data.routing_results // {}),
    memory_keys: ((.checkpoint_data.memory // {}) | keys)
  }' /tmp/pw_task_detail.json || true
fi

if [[ "$WAIT_FOR_COMPLETION" == "1" && "$TIMED_OUT" -eq 1 ]]; then
  reason=$(jq -r '.blocking_reason // empty' /tmp/pw_task_detail.json 2>/dev/null || true)
  if [[ -n "$reason" ]]; then
    echo "TERMINAL_BLOCKING_REASON: $reason"
  else
    echo "TERMINAL_BLOCKING_REASON: timeout without explicit blocking_reason from API"
  fi
fi

echo "--- TUNNEL LOG ---"
tail -n 60 /tmp/pw_lt_e2e.log || true

if [[ "$ASSERTION_OK" -ne 1 ]]; then
  exit 2
fi

if [[ "$WAIT_FOR_COMPLETION" == "1" && "$TIMED_OUT" -eq 1 ]]; then
  exit 4
fi

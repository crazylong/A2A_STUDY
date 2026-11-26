#!/usr/bin/env bash
# 无 LLM 回归：编译检查 + 客户端/分发契约 + Hello + A2A 全生命周期 + MCP 工具路线。
set -euo pipefail
cd "$(dirname "$0")/.."

ROOT="$PWD"
PYTHON="$ROOT/.venv/bin/python"
PROVIDER_PYTHON="$ROOT/article04_agents/provider_env/.venv/bin/python"

uv sync --locked
uv sync --locked --project article04_agents/provider_env

PIDS=()
cleanup() {
  for pid in "${PIDS[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
  for pid in "${PIDS[@]:-}"; do
    wait "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

wait_ready() {
  local port=$1
  for _ in $(seq 1 60); do
    if curl -fsS --noproxy '*' \
      "http://127.0.0.1:${port}/.well-known/agent-card.json" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.5
  done
  echo "[FAIL] :${port} 未就绪" >&2
  return 1
}

stop_server() {
  local pid=$1 port=$2
  kill "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
  for _ in $(seq 1 50); do
    if ! curl -fsS --noproxy '*' \
      "http://127.0.0.1:${port}/.well-known/agent-card.json" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.1
  done
  echo "[FAIL] :${port} 停止后仍可访问" >&2
  return 1
}

echo "== 1. 编译检查 =="
"$PYTHON" -m compileall -q \
  article02_hello article03_compare article04_agents article05_agentstack scripts
echo "OK"

echo "== 2. 客户端响应契约 =="
"$PYTHON" scripts/verify_client_contract.py

echo "== 3. 部分失败与结构化报告 =="
"$PYTHON" scripts/verify_dispatch_report.py

echo "== 4. 第二篇 Hello A2A =="
"$PYTHON" article02_hello/server.py > /tmp/a2a_verify_hello_server.log 2>&1 &
HPID=$!
PIDS+=("$HPID")
wait_ready 9999
"$PYTHON" article02_hello/client.py > /tmp/a2a_verify_hello_client.log 2>&1
grep -q 'TASK_STATE_COMPLETED' /tmp/a2a_verify_hello_client.log
grep -q 'Hello, World' /tmp/a2a_verify_hello_client.log
grep -q 'SendMessage' /tmp/a2a_verify_hello_client.log
grep -q 'SendStreamingMessage' /tmp/a2a_verify_hello_client.log
stop_server "$HPID" 9999

echo "== 5. 第四篇 A2A 路线：input_required / completed / canceled =="
"$PYTHON" article03_compare/currency_a2a_server.py > /tmp/a2a_verify_currency_server.log 2>&1 &
CPID=$!
PIDS+=("$CPID")
wait_ready 9995
"$PYTHON" article03_compare/currency_a2a_client.py > /tmp/a2a_verify_currency_client.log 2>&1
grep -q 'TASK_STATE_INPUT_REQUIRED' /tmp/a2a_verify_currency_client.log
grep -q 'TASK_STATE_COMPLETED' /tmp/a2a_verify_currency_client.log
grep -q 'TASK_STATE_CANCELED' /tmp/a2a_verify_currency_client.log
grep -q 'TaskNotCancelableError' /tmp/a2a_verify_currency_client.log
stop_server "$CPID" 9995

echo "== 6. 第四篇 MCP 路线 =="
"$PROVIDER_PYTHON" article03_compare/currency_mcp_client.py > /tmp/a2a_verify_mcp.log 2>&1
grep -q 'MCP 工具列表' /tmp/a2a_verify_mcp.log
grep -q '"status":"ok"' /tmp/a2a_verify_mcp.log

echo "全部通过。输出在 /tmp/a2a_verify_*.log"

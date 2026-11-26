#!/usr/bin/env bash
# 第六、七篇：一键启动全部四个智能体，并等待名片就绪。
# 用法：bash article04_agents/run_all.sh
set -euo pipefail
cd "$(dirname "$0")/.."

ROOT="$PWD"
PYTHON="$ROOT/.venv/bin/python"
PROVIDER_PYTHON="$ROOT/article04_agents/provider_env/.venv/bin/python"

if [[ ! -x "$PYTHON" || ! -x "$PROVIDER_PYTHON" ]]; then
  echo "请先运行 uv sync --locked 和 uv sync --locked --project article04_agents/provider_env" >&2
  exit 1
fi

read -r PROBE_HOST P_POLICY P_RESEARCH P_PROVIDER P_HEALTHCARE <<<"$(
  "$PYTHON" - <<'PY'
import os
from dotenv import dotenv_values

values = dotenv_values('.env')

def get(name, default):
    return os.environ.get(name) or values.get(name) or default

bind_host = get('BIND_HOST', '127.0.0.1')
probe_host = '127.0.0.1' if bind_host in ('0.0.0.0', '::') else bind_host
print(
    probe_host,
    get('POLICY_AGENT_PORT', '9999'),
    get('RESEARCH_AGENT_PORT', '9998'),
    get('PROVIDER_AGENT_PORT', '9997'),
    get('HEALTHCARE_AGENT_PORT', '9996'),
)
PY
)"

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

"$PYTHON" article04_agents/policy_agent.py &
PIDS+=($!)
"$PYTHON" article04_agents/research_agent.py &
PIDS+=($!)
"$PROVIDER_PYTHON" article04_agents/provider_agent.py &
PIDS+=($!)
"$PYTHON" article04_agents/healthcare_agent.py &
PIDS+=($!)

wait_ready() {
  local name=$1 port=$2
  for _ in $(seq 1 120); do
    if curl -fsS --noproxy '*' \
      "http://${PROBE_HOST}:${port}/.well-known/agent-card.json" >/dev/null 2>&1; then
      echo "[ready] ${name} → http://${PROBE_HOST}:${port}"
      return 0
    fi
    sleep 0.5
  done
  echo "[timeout] ${name} 在 60 秒内未就绪（:${port}）" >&2
  return 1
}

wait_ready "PolicyAgent" "$P_POLICY"
wait_ready "ResearchAgent" "$P_RESEARCH"
wait_ready "ProviderAgent" "$P_PROVIDER"
wait_ready "HealthcareAgent" "$P_HEALTHCARE"

echo "四个智能体已就绪；另开终端运行 demo_client.py 测试。Ctrl+C 停止全部。"
wait

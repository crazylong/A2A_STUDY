#!/usr/bin/env bash
# 篇三：一键启动全部四个智能体（Ctrl+C 全部停止）
# 用法：bash article03_agents/run_all.sh
set -e
cd "$(dirname "$0")/.."

uv run python article03_agents/policy_agent.py &
uv run python article03_agents/research_agent.py &
uv run --project article03_agents/provider_env python article03_agents/provider_agent.py &
uv run python article03_agents/healthcare_agent.py &

echo "PolicyAgent    → http://127.0.0.1:9999"
echo "ResearchAgent  → http://127.0.0.1:9998"
echo "ProviderAgent  → http://127.0.0.1:9997"
echo "HealthcareAgent→ http://127.0.0.1:9996"
echo "启动需要几秒钟；另开终端运行 demo_client.py 测试。Ctrl+C 停止全部。"

trap 'kill 0' EXIT
wait
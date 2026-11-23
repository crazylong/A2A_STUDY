# A2A_STUDY —— A2A 学习专栏配套代码

「A2A 从入门到实战」系列（共四篇）的全部示例代码，均已实测跑通。
文章见仓库同级目录 `../articles/`。

## 版本基线（2026-11 实测）

| 环境 | 关键依赖 | 用途 |
| --- | --- | --- |
| 主环境（本目录，可命名 `a2a-study`） | a2a-sdk 1.3.1 / fastmcp 4.2.0 / google-adk 2.14.1 / openai 2.x | 篇二、篇三大部分代码 |
| `article03_agents/provider_env` | mcp 1.x / langchain-mcp-adapters / langgraph 1.2.x | 篇三 ProviderAgent（与 fastmcp 4.x 的 mcp 2.x 依赖冲突，故隔离） |
| `article04_agentstack/policy_agent` | agentstack-sdk 0.7.1（钉住 a2a-sdk 0.3.24，v0.3 协议） | 篇四 Agent Stack 版智能体 |

Python 统一 3.13（最新补丁版），用 [uv](https://docs.astral.sh/uv/) 管理。
主环境默认是 `.venv`；若把环境命名为 `a2a-study`，可 `ln -s a2a-study .venv`，
或设置 `A2A_MAIN_PYTHON=/path/to/a2a-study/bin/python`（供 MCP 子进程拉起时使用）。

## 准备

```bash
# 1. 主环境
uv sync

# 2. 配置 LLM（OpenAI 兼容接口），篇二不需要，篇三/篇四需要
cp .env.sample .env   # 填入百炼的 LLM_BASE_URL / LLM_MODEL / LLM_API_KEY

# 3. 子环境（首次运行前）
uv sync --project article03_agents/provider_env
uv sync --project article04_agentstack/policy_agent
```

> 实测提示：若系统 `NO_PROXY` 含 `[::1]` 写法，httpx 会报 `InvalidURL`。
> 代码内已用 `trust_env=False` 规避；CLI 工具可用 `NO_PROXY= <命令>` 绕过。

## 篇二：Hello A2A（无需 API Key）

```bash
uv run python article02_hello/server.py    # 终端 1，:9999
uv run python article02_hello/client.py    # 终端 2
```

预期输出见 `article02_hello/sample_output.txt`。

### 2.10 对照实验：同一能力，A2A 与 MCP 两种接法（无需 API Key）

```bash
# 路线 A：A2A（:9995）
uv run python article02_hello/currency_a2a_server.py     # 终端 1
uv run python article02_hello/currency_a2a_client.py     # 终端 2

# 路线 B：MCP（客户端跑在 provider_env，服务由主环境 Python 以 stdio 拉起）
uv run --project article03_agents/provider_env python article02_hello/currency_mcp_client.py
```

两条路线的实测输出见 `article02_hello/currency_compare_output.txt`。
汇率为 `currency_rates.json` 里的虚构演示数据，不联网。

## 篇三：跨框架医疗多智能体（需要 .env）

```bash
./article03_agents/run_all.sh              # 终端 1：一键起 4 个智能体
uv run python article03_agents/demo_client.py   # 终端 2：向导诊台 :9996 提问
```

端口：Healthcare 9996 / Research 9998 / Provider 9997 / Policy 9999。
单独启动某个智能体：

```bash
uv run python article03_agents/policy_agent.py
uv run python article03_agents/research_agent.py
uv run --project article03_agents/provider_env python article03_agents/provider_agent.py
uv run python article03_agents/healthcare_agent.py
```

预期输出见 `article03_agents/sample_output.txt`。保单与医生数据均为虚构演示数据。

## 篇四：Agent Stack 版 PolicyAgent

```bash
cd article04_agentstack/policy_agent
uv run server                              # 本地启动，:8000（绕过 SDK auth_backend bug，见代码注释）

# 验证（v0.3 过渡版协议：枚举用 ROLE_USER，载荷字段是 content）
curl --noproxy '*' -X POST http://127.0.0.1:8000/v1/message:send \
  -H 'Content-Type: application/json' \
  -d '{"message":{"role":"ROLE_USER","messageId":"t1","content":[{"text":"你好"}]}}'

# 容器化
docker build -t policy-agent:a2a-study .
docker run -p 18000:8000 policy-agent:a2a-study
```

本地无平台时 LLM 扩展不可用，智能体会礼貌提示"请在平台启用 LLM 扩展"——这是预期行为。
完整平台部署（`agentstack platform start` / `agentstack add`）需要 Lima 虚拟机 + Kubernetes，
命令与版本注意事项见篇四文章。

## 目录结构

```
A2A_STUDY/
├── article02_hello/          # 篇二：最小服务端/客户端
├── article03_agents/         # 篇三：四智能体 + MCP 工具 + 公共模块
│   ├── data/                 # 虚构保单与医生名录
│   └── provider_env/         # LangGraph 子环境
└── article04_agentstack/
    └── policy_agent/         # 篇四：Agent Stack 版（独立环境 + Dockerfile）
```
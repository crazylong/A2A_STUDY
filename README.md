# A2A_STUDY —— A2A 学习专栏配套代码

「A2A 与 MCP：多智能体协作协议从入门到实战」系列（共九篇）的示例代码。无 LLM 的本地链路与客户端契约可按本文回归；真实 LLM 样本仍须按最终模型重跑。平台本体、平台模型配置/注册、加固镜像和 `client-side-build` 导入均未验证。

> 文章见 CSDN 专栏：[A2A 与 MCP：多智能体协作协议从入门到实战](https://blog.csdn.net/u012470019/category_13227184.html)

## 文章编号与代码目录

专栏已拆分为九篇，但为保留既有命令和目录耦合，代码目录仍使用历史名称。**目录名是历史命名，不代表新文章序号，也不表示目录缺失或需要重命名。**

| 新文章编号 | 文章标题 | 代码位置 | 是否需要 LLM |
| --- | --- | --- | --- |
| 01 | 认识A2A | 无独立代码目录 | 否 |
| 02 | 从零跑通Hello A2A | `article02_hello/` | 否 |
| 03 | A2A核心概念 | 无独立代码目录，复用 `article02_hello/` | 否 |
| 04 | 同一能力，A2A与MCP两种接法 | `article03_compare/` | 否 |
| 05 | A2A通用服务底座 | `article04_agents/common.py`、`a2a_helpers.py`、`a2a_client.py` | 随调用方 |
| 06 | 跨框架智能体接入 | `article04_agents/` 下的 policy / research / provider / mcpserver，以及 `provider_env/` | 是 |
| 07 | 导诊编排与可靠性 | `article04_agents/` 下的 healthcare_agent / demo_client / run_all.sh / sample_output.txt | 是 |
| 08 | AgentStack平台适配 | `article05_agentstack/policy_agent/` | 平台 LLM 扩展需要 |
| 09 | AgentStack兼容性与故障排查 | 同 `article05_agentstack/policy_agent/` | 本地协议验证否 |

例如，`article03_compare/` 对应第四篇，`article04_agents/` 承载第五至七篇，`article05_agentstack/` 承载第八、九篇。

## 版本基线（2026-11 实测）

| 环境 | 关键依赖 | 用途 |
| --- | --- | --- |
| 主环境（本目录，可命名 `a2a-study`） | a2a-sdk 1.3.1 / fastmcp 3.4.11 / mcp 1.30 / google-adk 2.14.1 / openai 2.x | 第二至四篇，以及第五至七篇的大部分代码 |
| `article04_agents/provider_env` | fastmcp 3.4.11 / mcp 1.x / langchain-mcp-adapters 0.3.2 / langgraph 1.2.x | 第四篇 MCP 服务端与客户端、第六篇 ProviderAgent、第七篇 Provider 节点（与主环境隔离，原因是 ADK 把主环境钉在 `openai<3`） |
| `article05_agentstack/policy_agent` | agentstack-sdk 0.7.1（钉住 a2a-sdk 0.3.24，v0.3 协议） | 第八、九篇 Agent Stack 版智能体 |

Python 统一 3.13（最新补丁版），用 [uv](https://docs.astral.sh/uv/) 管理。
主环境默认是 `.venv`；若把环境命名为 `a2a-study`，可 `ln -s a2a-study .venv`，
或设置 `A2A_MAIN_PYTHON=/path/to/a2a-study/bin/python`（供 MCP 子进程拉起时使用）。

> **MCP 版本口径**：仓库里所有 MCP 代码固定在 **mcp 1.x 协议代**（`fastmcp==3.4.11` + `langchain-mcp-adapters 0.3.2`）。这**不是最新写法**——MCP 2026-07-28 修订把会话改成无状态：服务端不能再在调用中途反向下发 elicitation 请求，只能随 `InputRequiredResult.inputRequests` 返回、由客户端补齐后重发（能力还在，通道变了）。这里刻意不追新：本仓库要讲的是 **A2A 与 MCP 的交互模型差异**，两端固定在同一协议代才能共用一份客户端代码、拿同一份输出做对照；换成新协议会让读者把注意力花在 MCP 自身的版本演进上，而这与 A2A/MCP 的区别无关。要迁新版，见 FastMCP 的升级说明与 `langchain.mcp` 的迁移指南。

## 准备

```bash
# 1. 主环境
uv sync --locked

# 2. 配置 LLM（OpenAI 兼容接口）：第六、七篇需要；第二至四篇不需要
#    第八、九篇的本地协议验证也不需要 LLM；平台 LLM 扩展需在平台侧另配
cp .env.sample .env   # 填入你的 OpenAI 兼容端点 / 模型名 / Key（本系列实测用百炼）

# 3. 子环境（首次运行前）
uv sync --locked --project article04_agents/provider_env
uv sync --locked --project article05_agentstack/policy_agent

# 4. 模型自检（仅已配置 .env 时运行；探测当前配置，不打印 Key；免费额度耗尽通常是 403）
uv run python scripts/check_llm.py

# 也可临时探测其他模型名（不写入配置）：
# uv run python scripts/check_llm.py <model-a> <model-b>
```

模型由你自己选择，代码不内置备选列表。切换只改 `.env` 的 `LLM_MODEL` 后重启；免费额度耗尽通常会返回 403 `insufficient_quota`，换成控制台里可用的模型即可。
`enable_thinking` 只对模型名含 `qwen` 的请求发送。
`BIND_HOST` 控制监听；调用方的 `*_AGENT_URL` 优先指定每个智能体地址，未设置时回退到 `PUBLIC_URL_TEMPLATE` / `A2A_HOST`。服务端名片广播地址由 `A2A_HOST` / `PUBLIC_URL_TEMPLATE` 决定；Agent Stack 本地/容器运行另用 `PUBLIC_URL`。

双机最小示例（地址按实际网络替换）：导诊台所在机器指向三个下游，下游所在机器用 LAN 地址广播名片。

```bash
# 导诊台机器
BIND_HOST=0.0.0.0
POLICY_AGENT_URL=http://10.0.0.11:9999
RESEARCH_AGENT_URL=http://10.0.0.11:9998
PROVIDER_AGENT_URL=http://10.0.0.11:9997

# 下游机器
BIND_HOST=0.0.0.0
A2A_HOST=10.0.0.11
```

> 实测提示：若系统 `NO_PROXY` / `no_proxy` 含 `[::1]` 写法，httpx 可能报 `InvalidURL`。
> 代码内已用 `trust_env=False` 规避；CLI 工具同时清空大小写变量：`NO_PROXY= no_proxy= <命令>`。

## 第一篇：认识A2A

概念篇，无独立代码目录，也无需运行命令。先了解智能体、Agent Card、任务生命周期与 A2A/MCP 的定位，再从第二篇开始动手。

## 第二篇：从零跑通Hello A2A（无需 API Key）

代码目录仍叫 `article02_hello/`。

```bash
uv run python article02_hello/server.py    # 终端 1，:9999
uv run python article02_hello/client.py    # 终端 2
```

预期输出见 `article02_hello/sample_output.txt`。

## 第三篇：A2A核心概念（无需 API Key）

无独立代码目录，复用第二篇的 Hello A2A 服务端、执行器和客户端，结合任务状态、Message / Task / Artifact、流式事件与 Agent Card 理解核心概念。

```bash
# 与第二篇相同：先启动服务端，再启动客户端
uv run python article02_hello/server.py
uv run python article02_hello/client.py
```

## 第四篇：同一能力，A2A与MCP两种接法（无需 API Key）

代码目录仍叫 `article03_compare/`。

```bash
# 路线 A：A2A（:9995）
uv run python article03_compare/currency_a2a_server.py     # 终端 1
uv run python article03_compare/currency_a2a_client.py     # 终端 2

# 路线 B：MCP（客户端跑在 provider_env，服务由主环境 Python 以 stdio 拉起）
uv run --project article04_agents/provider_env python article03_compare/currency_mcp_client.py

# 补充：MCP Elicitation（一次调用中追问目标币种）
printf 'CNY\n' | uv run --project article04_agents/provider_env python article03_compare/currency_mcp_elicitation_client.py
```

两条路线的实测输出见 `article03_compare/currency_compare_output.txt`。Elicitation 案例复用同一份汇率逻辑，但额外要求客户端注册用户输入回调；它演示调用内补参数，不是跨请求 Tasks 生命周期。
汇率取自 `article03_compare/currency_rates.json`，为虚构演示数据，不联网。

## 第五篇：A2A通用服务底座

代码复用 `article04_agents/` 中的 `common.py`、`a2a_helpers.py`、`a2a_client.py`，分别封装环境/地址/LLM 配置、A2A 服务端和 A2A 客户端。

本篇没有独立启动入口，公共模块由第六、七篇的智能体进程加载；运行命令见下文，编译回归见“无 LLM 回归”。

## 第六篇：跨框架智能体接入（需要 .env）

代码仍集中在 `article04_agents/`：PolicyAgent 使用纯 a2a-sdk，ResearchAgent 使用 Google ADK，ProviderAgent 使用 LangGraph + MCP，并通过 `provider_env/` 隔离 MCP 客户端依赖。

```bash
# 按需单独启动某个智能体
uv run python article04_agents/policy_agent.py
uv run python article04_agents/research_agent.py
uv run --project article04_agents/provider_env python article04_agents/provider_agent.py

# 或用一键脚本同时启动四个智能体（包含第七篇的 HealthcareAgent）
./article04_agents/run_all.sh
```

`run_all.sh` 直接使用两个 venv 的 Python，白名单读取 `.env`（不 source），退出时按记录的 PID 清理。ProviderAgent 会通过主环境 Python 自动拉起 `article04_agents/mcpserver.py`，一般不需要单独运行 MCP 服务。
端口：Policy 9999 / Research 9998 / Provider 9997 / Healthcare 9996。

## 第七篇：导诊编排与可靠性（需要 .env）

继续复用 `article04_agents/`，本篇聚焦 `healthcare_agent.py` 的导诊编排、下游任务可靠性，以及 `demo_client.py` 的演示。

```bash
bash article04_agents/run_all.sh                 # 终端 1：一个导诊台 + 三个下游
uv run python article04_agents/demo_client.py    # 终端 2：向导诊台 :9996 提问
```

`article04_agents/sample_output.txt` 是 2026-11-23 的历史真实模型输出，不含新 `dispatch-report` 与退出码契约，须待最终模型重跑。保单与医生数据均为虚构演示数据。

退出码：`0` 全部成功；`1` 外层问题失败（如冷启动名片未全量加载）；`2` 外层完成但 `dispatch-report` 的 `summary.failed>0`。测试退出 2 必须先启动全部下游并成功预热名片缓存，再让一次真实分发失败；冷启动直接停一个下游会退出 1。

## 第八篇：AgentStack平台适配

代码目录仍叫 `article05_agentstack/`，项目位于 `article05_agentstack/policy_agent/`。

```bash
cd article05_agentstack/policy_agent
uv sync --locked
uv run server                              # 本地/独立入口，:8000（绕过 SDK auth_backend bug，见第九篇）

# 本地验证（v0.3 过渡版协议：枚举用 ROLE_USER，载荷字段是 content）
curl --noproxy '*' -X POST http://127.0.0.1:8000/v1/message:send \
  -H 'Content-Type: application/json' \
  -d '{"message":{"role":"ROLE_USER","messageId":"t1","content":[{"text":"你好"}]}}'

# 容器化（Dockerfile 固定 uv 0.13.9、分层缓存、非 root；以下均未实测）
docker build -t policy-agent:a2a-study .
docker run --env PUBLIC_URL=http://127.0.0.1:18000 -p 18000:8000 policy-agent:a2a-study

# 本地构建并导入；必须在项目目录执行（未实测）
agentstack client-side-build . --tag policy-agent:a2a-study --import
```

`PUBLIC_URL` 必须指向客户端可达的地址；容器运行时显式设为宿主机映射地址，避免名片广播容器内部地址。
本地无平台时 LLM 扩展不可用，智能体会礼貌提示“请在平台启用 LLM 扩展”——这是预期行为。

Dockerfile 的 `CMD` 是本地/独立部署入口，平台托管启动方式由平台注入且未验证。完整平台部署需要 Lima 虚拟机 + Kubernetes，**目前仍未实测**；平台模型配置与注册也未验证。`agentstack add` 不支持本地目录，GitHub 来源按 `agentstack add --help` 填写。加固 Dockerfile 与 `client-side-build` 均未实测，上述命令不代表镜像、导入或平台流程已通过。

## 第九篇：AgentStack兼容性与故障排查

复用第八篇的 `article05_agentstack/policy_agent/`。本篇记录 agentstack-sdk 0.7.1 + a2a-sdk 0.3.24 的兼容性问题，并用本地协议请求验证绕过 `auth_backend` bug 后的服务。

```bash
# 终端 1：本地启动（run() 绕过 Server.serve() 的 auth_backend 透传问题）
cd article05_agentstack/policy_agent
uv sync --locked
uv run server

# 终端 2：按 v0.3 过渡版协议发送本地验证请求
curl --noproxy '*' -X POST http://127.0.0.1:8000/v1/message:send \
  -H 'Content-Type: application/json' \
  -d '{"message":{"role":"ROLE_USER","messageId":"t1","content":[{"text":"你好"}]}}'
```

本地验证不需要平台或真实 LLM Key；没有 LLM 扩展时返回平台启用提示属于预期结果。`run()` 还使用了 SDK 私有 `_agent_factory`，升级依赖后需重新复核。

## 无 LLM 回归

```bash
bash scripts/verify_all.sh
```

覆盖：全量编译、`scripts/verify_client_contract.py`、`scripts/verify_dispatch_report.py`、第二篇 Hello、第四篇 A2A 的续聊 `INPUT_REQUIRED → COMPLETED`、另一任务 `INPUT_REQUIRED → CANCELED` 与二次取消失败、第四篇 MCP 普通工具路线、MCP Elicitation 的调用内追问与正常返回。客户端契约覆盖 `COMPLETED+Artifact`、直接 `ROLE_AGENT` Message、非流式 `return_immediately` 非终态、`FAILED`、`INPUT_REQUIRED`、直接 `ROLE_USER`、`COMPLETED` 但只有状态消息且无 Artifact、非文本或纯空白 Artifact 等拒绝路径；分发契约覆盖冷/热缓存、部分失败报告、退出码 0/1/2 与异常脱敏。脚本直接调用两个 venv 的 Python，检查服务端口关闭；失败会非零退出，并在 `/tmp/a2a_verify_*.log` 留输出。
第六、七篇真实 LLM 编排需先完成 `.env` 配置，再运行 `run_all.sh` + `demo_client.py`。

## 目录结构

```text
A2A_STUDY/
├── README.md                  # 九篇文章与历史目录的对应说明
├── .env.sample                # LLM、多智能体与 Agent Stack 地址配置示例
├── scripts/
│   ├── check_llm.py           # LLM 配置自检
│   ├── verify_client_contract.py # A2A 客户端响应契约
│   ├── verify_dispatch_report.py # 分发报告、缓存边界、退出码与脱敏
│   └── verify_all.sh          # 无 LLM 回归
├── article02_hello/           # 第二篇；第三篇复用：最小服务端/客户端
├── article03_compare/         # 第四篇：同一能力的 A2A / MCP 两条接法
│   ├── currency_mcp_elicitation_server.py # MCP 调用内追问
│   └── currency_mcp_elicitation_client.py # 终端 elicitation 回调
├── article04_agents/          # 第五至七篇：公共底座、跨框架智能体与导诊编排
│   ├── common.py              # 第五篇：环境、地址与 LLM 工厂
│   ├── a2a_helpers.py         # 第五篇：A2A 服务端公共封装
│   ├── a2a_client.py          # 第五篇：A2A 客户端公共封装
│   ├── policy_agent.py        # 第六篇：纯 SDK 智能体
│   ├── research_agent.py      # 第六篇：Google ADK 智能体
│   ├── provider_agent.py      # 第六篇：LangGraph + MCP 智能体
│   ├── mcpserver.py           # 第六篇：医生名录 MCP 服务
│   ├── healthcare_agent.py    # 第七篇：导诊编排
│   ├── demo_client.py         # 第七篇：编排演示客户端
│   ├── run_all.sh             # 第六、七篇：一键启动四个智能体
│   ├── sample_output.txt      # 第七篇：历史真实模型输出，待重跑
│   ├── data/                  # 虚构保单与医生名录
│   └── provider_env/          # 第四篇 MCP 客户端、第六篇 ProviderAgent 子环境
└── article05_agentstack/
    └── policy_agent/          # 第八、九篇：Agent Stack 版（独立环境 + Dockerfile）
```

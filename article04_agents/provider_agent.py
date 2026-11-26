"""第六篇《跨框架智能体接入》：ProviderAgent —— 医生查询智能体（LangGraph + MCP，对外 A2A）。

对应课程 09 课。这是"A2A + MCP 叠加"的实例：
- 对外：A2A Server，接收导诊智能体的任务
- 对内：LangGraph ReAct 智能体通过 MCP 调用医生名录工具

注意运行环境：本脚本用 provider_env 子环境运行（mcp 1.x 生态）：
  uv run --project article04_agents/provider_env python article04_agents/provider_agent.py
MCP 服务进程则由主环境 Python 拉起（fastmcp 4.x / mcp 2.x），
两个进程之间走标准 MCP stdio 协议——依赖版本不同也能协作。
"""

import asyncio
import os
import sys
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from a2a.types import AgentSkill  # noqa: E402

from a2a_helpers import serve  # noqa: E402
from common import LLM_MODEL, PORTS, thinking_extra_body  # noqa: E402

from langchain_mcp_adapters.client import MultiServerMCPClient  # noqa: E402
from langchain_openai import ChatOpenAI  # noqa: E402
from langgraph.prebuilt import create_react_agent  # noqa: E402

# MCP 服务用主环境 Python 运行（fastmcp 4.x 装在主环境）。
# 支持 A2A_MAIN_PYTHON 显式指定；默认依次找 .venv、a2a-study 两种环境目录
MAIN_PYTHON = os.environ.get('A2A_MAIN_PYTHON') or next(
    (
        str(HERE.parent / name / 'bin' / 'python')
        for name in ('.venv', 'a2a-study')
        if (HERE.parent / name / 'bin' / 'python').exists()
    ),
    '',
)
if not MAIN_PYTHON:
    raise RuntimeError(
        '找不到主环境 Python，请设置 A2A_MAIN_PYTHON 指向主环境解释器'
    )

_agent = None
_httpx_client: httpx.AsyncClient | None = None
_agent_lock = asyncio.Lock()


async def get_agent():
    """懒加载：连 MCP 服务 → 取工具 → 建 LangGraph ReAct 智能体。"""
    global _agent, _httpx_client
    if _agent is None:
        async with _agent_lock:
            if _agent is None:
                client = MultiServerMCPClient(
                    {
                        'doctor_directory': {
                            'command': str(MAIN_PYTHON),
                            'args': [str(HERE / 'mcpserver.py')],
                            'transport': 'stdio',
                        }
                    }
                )
                _httpx_client = httpx.AsyncClient(
                    trust_env=False, timeout=httpx.Timeout(120.0)
                )
                try:
                    tools = await client.get_tools()
                    llm_kwargs = {
                        'model': LLM_MODEL,
                        'base_url': os.environ['LLM_BASE_URL'],
                        'api_key': os.environ['LLM_API_KEY'],
                        'temperature': 0,
                        'http_async_client': _httpx_client,
                    }
                    extra_body = thinking_extra_body()
                    if extra_body is not None:
                        llm_kwargs['extra_body'] = extra_body
                    llm = ChatOpenAI(**llm_kwargs)
                    _agent = create_react_agent(
                        llm,
                        tools,
                        prompt=(
                            '你是医生查询助手。使用 list_doctors 工具按城市和科室查询医生，'
                            '把结果整理成中文清单回复（姓名、科室、医院、电话、是否网内）。'
                            '查不到就如实说明。不要编造医生信息。'
                        ),
                    )
                except Exception:
                    await _httpx_client.aclose()
                    _httpx_client = None
                    raise
    return _agent


async def close_provider() -> None:
    global _httpx_client
    async with _agent_lock:
        if _httpx_client is not None:
            await _httpx_client.aclose()
            _httpx_client = None


async def answer(query: str) -> str:
    agent = await get_agent()
    result = await agent.ainvoke({'messages': [{'role': 'user', 'content': query}]})
    return result['messages'][-1].content


if __name__ == '__main__':
    serve(
        name='ProviderAgent',
        description='按城市与科室查询医生名录（内部通过 MCP 工具访问数据）',
        skill=AgentSkill(
            id='doctor_lookup',
            name='医生查询',
            description='按城市、科室查找医生，返回姓名、医院、电话与网内状态',
            tags=['doctor', 'provider', 'mcp'],
            examples=['北京有哪些心理科医生？', '上海心内科医生名单'],
        ),
        fn=answer,
        port=PORTS['provider'],
        on_shutdown=close_provider,
    )
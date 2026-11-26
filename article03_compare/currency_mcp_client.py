"""第四篇 路线 B：MCP 客户端（provider_env：mcp 1.x + langchain-mcp-adapters）

运行：
    uv run --project article04_agents/provider_env python article03_compare/currency_mcp_client.py

这里直接调用工具、不接 LLM：换成 function calling 只是把"谁来选工具"交给模型，
工具侧的交互形态（一次请求 → 一段结果，无任务对象）不变。
"""

import asyncio
import os
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient

HERE = Path(__file__).resolve().parent
# fastmcp 4.x 在主环境，provider_env 只负责当客户端（依赖冲突见第六篇的依赖隔离小节）。
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


async def main():
    client = MultiServerMCPClient(
        {
            'currency': {
                'command': str(MAIN_PYTHON),
                'args': [str(HERE / 'currency_mcp_server.py')],
                'transport': 'stdio',
            }
        }
    )

    tools = await client.get_tools()
    print('MCP 工具列表:', [tool.name for tool in tools])
    tool = next(tool for tool in tools if tool.name == 'convert_currency')

    print('\n--- 调用 1：参数齐全 ---')
    print(await tool.ainvoke(
        {'amount': 100, 'from_currency': 'USD', 'to_currency': 'CNY'}
    ))

    print('\n--- 调用 2：币种不受支持 ---')
    print(await tool.ainvoke(
        {'amount': 100, 'from_currency': 'USD', 'to_currency': 'XXX'}
    ))

    print('\n--- 调用 3：少传参数（没有 input_required，直接是调用失败） ---')
    try:
        result = await tool.ainvoke({'amount': 100, 'from_currency': 'USD'})
        print(result)
    except Exception as exc:  # noqa: BLE001 - 演示：参数缺失由调用方兜底
        print(f'{type(exc).__name__}: {str(exc).splitlines()[0][:160]}')


if __name__ == '__main__':
    asyncio.run(main())
"""第四篇 路线 B：MCP 客户端（provider_env：fastmcp 3.x + adapters 0.3.2，同为 mcp 1.x）

运行：
    uv run --project article04_agents/provider_env python article03_compare/currency_mcp_client.py

服务端与客户端在同一个环境里，stdio 子进程直接用当前解释器拉起。
这里直接调用工具、不接 LLM：换成 function calling 只是把"谁来选工具"交给模型，
工具侧的交互形态（一次请求 → 一段结果，无任务对象）不变。
"""

import asyncio
import sys
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient

HERE = Path(__file__).resolve().parent
# 服务端脚本与客户端同环境（fastmcp 3.4.11 + langchain-mcp-adapters 0.3.2 + mcp 1.30.0）
SERVER_PYTHON = sys.executable


async def main():
    client = MultiServerMCPClient(
        {
            'currency': {
                'command': str(SERVER_PYTHON),
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

    print('\n--- 调用 3：少传参数（返回校验错误，不会挂起） ---')
    try:
        result = await tool.ainvoke({'amount': 100, 'from_currency': 'USD'})
        print(result)
    except Exception as exc:  # noqa: BLE001 - 演示：参数缺失由调用方兜底
        print(f'{type(exc).__name__}: {str(exc).splitlines()[0][:160]}')


if __name__ == '__main__':
    asyncio.run(main())
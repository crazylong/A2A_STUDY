"""第四篇补充案例：带终端表单回调的 MCP Elicitation 客户端。

运行：
    uv run --project article04_agents/provider_env python article03_compare/currency_mcp_elicitation_client.py

这里只调用一次工具。服务端在执行中请求目标币种，回调收集输入后返回同一次调用。
"""

import asyncio
import sys
from pathlib import Path

from langchain_mcp_adapters.callbacks import Callbacks
from langchain_mcp_adapters.client import MultiServerMCPClient
from mcp.types import ElicitRequestFormParams, ElicitResult

HERE = Path(__file__).resolve().parent
# 服务端脚本与客户端同环境，stdio 子进程直接用当前解释器拉起
SERVER_PYTHON = sys.executable


async def handle_elicitation(mcp_context, params, context) -> ElicitResult:
    print(f'\n[elicitation] {params.message}')
    if not isinstance(params, ElicitRequestFormParams):
        print('本示例只处理表单模式，已拒绝 URL 模式。')
        return ElicitResult(action='decline')

    schema = params.requestedSchema
    value_schema = schema.get('properties', {}).get('value', {})
    choices = value_schema.get('enum', [])
    if choices:
        print('可选项:', ' / '.join(choices))
    answer = input('请输入目标币种（直接回车取消）: ').strip()
    if not answer:
        return ElicitResult(action='cancel')
    print(f'用户选择: {answer}')
    return ElicitResult(action='accept', content={'value': answer})


async def main():
    client = MultiServerMCPClient(
        {
            'currency': {
                'command': SERVER_PYTHON,
                'args': [str(HERE / 'currency_mcp_elicitation_server.py')],
                'transport': 'stdio',
            }
        },
        callbacks=Callbacks(on_elicitation=handle_elicitation),
    )

    tools = await client.get_tools()
    tool = next(t for t in tools if t.name == 'convert_currency_interactive')

    print('--- 一次 tools/call：缺少目标币种，调用中追问 ---')
    print('用户: 帮我换算 100 美元')
    result = await tool.ainvoke(
        {'amount': 100, 'from_currency': 'USD'}
    )
    print('\n工具返回:', result)


if __name__ == '__main__':
    asyncio.run(main())

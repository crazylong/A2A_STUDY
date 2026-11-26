"""第四篇 路线 A：汇率 A2A 服务端（a2a-sdk 1.3.1，:9995）

运行：uv run python article03_compare/currency_a2a_server.py
"""

import uvicorn
from starlette.applications import Starlette

from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill

from currency_agent import CurrencyAgentExecutor

PORT = 9995

skill = AgentSkill(
    id='convert_currency',
    name='Currency Conversion',
    description='按演示汇率换算两种货币，缺信息时会追问',
    input_modes=['text/plain'],
    output_modes=['text/plain'],
    tags=['currency', 'exchange-rate', 'demo'],
    examples=['100 美元换成人民币', '把 50 欧元换成日元'],
)

public_agent_card = AgentCard(
    name='Currency Agent (A2A route)',
    description='A2A 与 MCP 同一能力对照实验',
    version='1.0.0',
    default_input_modes=['text/plain'],
    default_output_modes=['text/plain'],
    capabilities=AgentCapabilities(streaming=True),
    supported_interfaces=[
        AgentInterface(
            protocol_binding='JSONRPC',
            url=f'http://127.0.0.1:{PORT}',
            protocol_version='1.0',
        )
    ],
    skills=[skill],
)

request_handler = DefaultRequestHandler(
    agent_executor=CurrencyAgentExecutor(),
    task_store=InMemoryTaskStore(),
    agent_card=public_agent_card,
)

routes = []
routes.extend(create_agent_card_routes(public_agent_card))
routes.extend(create_jsonrpc_routes(request_handler, '/'))

app = Starlette(routes=routes)

if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=PORT)
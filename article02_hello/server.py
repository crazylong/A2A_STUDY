"""篇二：Hello A2A 服务端（a2a-sdk 1.3.1）

参考 a2a-samples/samples/python/agents/helloworld，用最新 SDK 重写。
运行：uv run python article02_hello/server.py
"""

import uvicorn
from starlette.applications import Starlette

from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill

from agent_executor import HelloWorldAgentExecutor

# 1. AgentSkill：声明智能体"会做什么"
skill = AgentSkill(
    id='echo_bot',
    name='Echo Bot',
    description='接收客户端请求并回复 Hello World 的示例智能体',
    input_modes=['text/plain'],
    output_modes=['text/plain'],
    tags=['a2a', 'echo-example'],
    examples=['hi', 'how are you'],
)

# 2. AgentCard：智能体的"名片"，客户端靠它发现并了解这个智能体
public_agent_card = AgentCard(
    name='Hello World Agent',
    description='Just a hello world agent',
    version='0.0.1',
    default_input_modes=['text/plain'],
    default_output_modes=['text/plain'],
    # 声明支持流式（SSE）
    capabilities=AgentCapabilities(streaming=True),
    # 服务端点：JSON-RPC 绑定，监听本机 9999
    supported_interfaces=[
        AgentInterface(
            protocol_binding='JSONRPC',
            url='http://127.0.0.1:9999',
            protocol_version='1.0',
        )
    ],
    skills=[skill],
)

# 3. RequestHandler：把 AgentExecutor（业务逻辑）和 TaskStore（任务存储）接起来
request_handler = DefaultRequestHandler(
    agent_executor=HelloWorldAgentExecutor(),
    task_store=InMemoryTaskStore(),
    agent_card=public_agent_card,
)

# 4. 路由：Agent Card 发现路由 + JSON-RPC 方法路由（message/send、message/stream 等）
routes = []
routes.extend(create_agent_card_routes(public_agent_card))
routes.extend(create_jsonrpc_routes(request_handler, '/'))

app = Starlette(routes=routes)

if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=9999)
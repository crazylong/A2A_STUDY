"""篇三公共模块：把任意"文本进、文本出"的智能体包装成 A2A 服务。

核心套路与篇二 HelloWorldAgentExecutor 完全一致：
建 Task → working → 执行业务 → Artifact → completed
"""

from collections.abc import Awaitable, Callable

import uvicorn
from starlette.applications import Starlette

from a2a.helpers import (
    get_message_text,
    new_task_from_user_message,
    new_text_message,
    new_text_part,
)
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    TaskState,
)

from common import HOST


class TextAgentExecutor(AgentExecutor):
    """把 async (str) -> str 的业务函数适配成 A2A AgentExecutor。"""

    def __init__(self, fn: Callable[[str], Awaitable[str]]):
        self.fn = fn

    async def execute(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        task = context.current_task or new_task_from_user_message(
            context.message
        )
        if not context.current_task:
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(
            event_queue=event_queue,
            task_id=task.id,
            context_id=task.context_id,
        )
        await updater.update_status(state=TaskState.TASK_STATE_WORKING)

        query = get_message_text(context.message) or ''
        try:
            result = await self.fn(query)
            await updater.add_artifact(
                parts=[new_text_part(text=result, media_type='text/plain')]
            )
            await updater.update_status(
                state=TaskState.TASK_STATE_COMPLETED,
                message=new_text_message('done'),
            )
        except Exception as e:  # noqa: BLE001
            await updater.update_status(
                state=TaskState.TASK_STATE_FAILED,
                message=new_text_message(f'执行失败: {e}'),
            )

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        raise NotImplementedError('Cancel is not supported.')


def serve(
    name: str,
    description: str,
    skill: AgentSkill,
    fn: Callable[[str], Awaitable[str]] | None = None,
    port: int = 9999,
    executor: AgentExecutor | None = None,
) -> None:
    """组装 Agent Card + 路由并启动服务。

    二选一：传 fn（文本业务函数）或传现成的 executor（如 ADK 的 A2aAgentExecutor）。
    """
    card = AgentCard(
        name=name,
        description=description,
        version='1.0.0',
        default_input_modes=['text/plain'],
        default_output_modes=['text/plain'],
        capabilities=AgentCapabilities(streaming=True),
        supported_interfaces=[
            AgentInterface(
                protocol_binding='JSONRPC',
                url=f'http://{HOST}:{port}',
                protocol_version='1.0',
            )
        ],
        skills=[skill],
    )
    handler = DefaultRequestHandler(
        agent_executor=executor or TextAgentExecutor(fn),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    routes = [
        *create_agent_card_routes(card),
        *create_jsonrpc_routes(handler, '/'),
    ]
    print(f'[{name}] serving on http://{HOST}:{port}')
    uvicorn.run(Starlette(routes=routes), host=HOST, port=port)
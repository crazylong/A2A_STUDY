"""第五篇《A2A通用服务底座》：把文本业务函数包装成 A2A 服务。"""

import logging
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import httpx
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
    Part,
    TaskNotCancelableError,
    TaskState,
)

from common import BIND_HOST, agent_url

logger = logging.getLogger(__name__)

_TERMINAL_STATES = {
    TaskState.TASK_STATE_COMPLETED,
    TaskState.TASK_STATE_FAILED,
    TaskState.TASK_STATE_CANCELED,
    TaskState.TASK_STATE_REJECTED,
}


@dataclass
class TaskResult:
    text: str
    extra_parts: list[Part] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


def _public_error(exc: Exception) -> str:
    status = getattr(exc, 'status_code', None)
    if status in (402, 403, 429):
        code, summary = 'LLM_QUOTA_OR_RATE_LIMIT', '模型服务额度、权限或限流异常'
    elif isinstance(exc, httpx.TimeoutException):
        code, summary = 'UPSTREAM_TIMEOUT', '上游调用超时'
    elif isinstance(exc, (ConnectionError, httpx.ConnectError)):
        code, summary = 'UPSTREAM_UNAVAILABLE', '上游服务不可用'
    else:
        code, summary = 'AGENT_EXECUTION_FAILED', '业务执行失败'
    return f'执行失败（{code}）：{summary}，详情见服务端日志'


class TextAgentExecutor(AgentExecutor):
    def __init__(
        self, fn: Callable[[str], Awaitable[str | TaskResult]]
    ):
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
            if isinstance(result, str):
                result = TaskResult(text=result)
            if not result.text.strip():
                raise ValueError('业务函数返回了空文本')
            await updater.add_artifact(
                parts=[new_text_part(text=result.text, media_type='text/plain')],
                artifact_id='answer',
                name='answer',
                metadata=result.metadata or None,
            )
            if result.extra_parts:
                await updater.add_artifact(
                    parts=result.extra_parts,
                    artifact_id='dispatch-report',
                    name='dispatch-report',
                )
            await updater.update_status(
                state=TaskState.TASK_STATE_COMPLETED,
                message=new_text_message('done'),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception('A2A 业务执行失败')
            await updater.update_status(
                state=TaskState.TASK_STATE_FAILED,
                message=new_text_message(_public_error(exc)),
            )

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        task = context.current_task
        if task is None or task.status.state in _TERMINAL_STATES:
            raise TaskNotCancelableError(
                f'Task {context.task_id} is not cancelable'
            )
        updater = TaskUpdater(
            event_queue=event_queue,
            task_id=task.id,
            context_id=task.context_id,
        )
        await updater.cancel(message=new_text_message('任务已取消'))


class _SanitizedEventQueue:
    def __init__(self, event_queue: EventQueue):
        self._event_queue = event_queue

    async def enqueue_event(self, event) -> None:
        status = getattr(event, 'status', None)
        if status is not None and status.state == TaskState.TASK_STATE_FAILED:
            status.message.CopyFrom(
                new_text_message(_public_error(RuntimeError('executor failure')))
            )
        await self._event_queue.enqueue_event(event)

    def __getattr__(self, name: str):
        return getattr(self._event_queue, name)


class SanitizedExecutor(AgentExecutor):
    def __init__(self, executor: AgentExecutor):
        self.executor = executor

    async def execute(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        await self.executor.execute(context, _SanitizedEventQueue(event_queue))

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        await self.executor.cancel(context, event_queue)


def serve(
    name: str,
    description: str,
    skill: AgentSkill,
    fn: Callable[[str], Awaitable[str | TaskResult]] | None = None,
    port: int = 9999,
    executor: AgentExecutor | None = None,
    on_shutdown: Callable[[], Awaitable[None]] | None = None,
) -> None:
    if (fn is None) == (executor is None):
        raise ValueError('serve() 的 fn 与 executor 必须二选一')
    advertised_url = agent_url(port)
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
                url=advertised_url,
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

    @asynccontextmanager
    async def lifespan(_app):
        yield
        if on_shutdown is not None:
            await on_shutdown()

    app = Starlette(routes=routes, lifespan=lifespan)
    print(f'[{name}] listening on {BIND_HOST}:{port}，名片地址 {advertised_url}')
    uvicorn.run(app, host=BIND_HOST, port=port)

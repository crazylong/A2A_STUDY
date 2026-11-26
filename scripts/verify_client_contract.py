"""无 LLM 的 A2A 客户端响应契约回归。"""

import asyncio
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'article04_agents'))
os.environ['A2A_HOST'] = '127.0.0.1'
os.environ['PUBLIC_URL_TEMPLATE'] = ''
os.environ.setdefault('LLM_MODEL', 'contract-stub')
os.environ.setdefault('LLM_BASE_URL', 'http://127.0.0.1:1')
os.environ.setdefault('LLM_API_KEY', 'not-used')

import httpx  # noqa: E402
import uvicorn  # noqa: E402
from starlette.applications import Starlette  # noqa: E402

from a2a.client import A2ACardResolver, ClientConfig, create_client  # noqa: E402
from a2a.helpers import (  # noqa: E402
    get_message_text,
    new_data_part,
    new_task_from_user_message,
    new_text_message,
    new_text_part,
)
from a2a.server.agent_execution import AgentExecutor, RequestContext  # noqa: E402
from a2a.server.events import EventQueue  # noqa: E402
from a2a.server.request_handlers import DefaultRequestHandler  # noqa: E402
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes  # noqa: E402
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater  # noqa: E402
from a2a.types import (  # noqa: E402
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    Role,
    SendMessageConfiguration,
    SendMessageRequest,
    TaskNotCancelableError,
    TaskState,
)

from a2a_client import AgentTaskError, ask_agent  # noqa: E402

PORT = 19999

# return_immediately 会让 SDK 1.3.1 在 dispatcher 正常结束后误报等待警告。
logging.getLogger('a2a.server.events.event_queue_v2').setLevel(logging.ERROR)


class StubExecutor(AgentExecutor):
    async def execute(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        query = get_message_text(context.message) or ''
        if query == 'direct':
            await event_queue.enqueue_event(
                new_text_message('直接答复', role=Role.ROLE_AGENT)
            )
            return
        if query == 'direct_user':
            await event_queue.enqueue_event(
                new_text_message('伪装答复', role=Role.ROLE_USER)
            )
            return

        task = new_task_from_user_message(context.message)
        await event_queue.enqueue_event(task)
        updater = TaskUpdater(
            event_queue=event_queue,
            task_id=task.id,
            context_id=task.context_id,
        )
        if query == 'fail':
            await updater.update_status(
                state=TaskState.TASK_STATE_FAILED,
                message=new_text_message('业务失败'),
            )
            return
        if query == 'input_required':
            await updater.update_status(
                state=TaskState.TASK_STATE_INPUT_REQUIRED,
                message=new_text_message('需要补充参数'),
            )
            return

        await updater.update_status(state=TaskState.TASK_STATE_WORKING)
        if query == 'status_only':
            await updater.update_status(
                state=TaskState.TASK_STATE_COMPLETED,
                message=new_text_message('done'),
            )
            return
        if query == 'slow':
            await updater.update_status(state=TaskState.TASK_STATE_WORKING)
            await asyncio.sleep(0.3)
            await updater.add_artifact(
                parts=[new_text_part('慢任务答复', media_type='text/plain')]
            )
            await updater.update_status(
                state=TaskState.TASK_STATE_COMPLETED,
                message=new_text_message('done'),
            )
            return
        if query == 'nontext':
            await updater.add_artifact(
                parts=[new_data_part({'ok': True}, media_type='application/json')]
            )
        elif query == 'blank':
            await updater.add_artifact(
                parts=[new_text_part(' \n\t', media_type='text/plain')]
            )
        else:
            await updater.add_artifact(
                parts=[new_text_part('任务答复', media_type='text/plain')]
            )
        await updater.update_status(
            state=TaskState.TASK_STATE_COMPLETED,
            message=new_text_message('done'),
        )

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        raise TaskNotCancelableError('stub')


def create_app() -> Starlette:
    card = AgentCard(
        name='ContractStub',
        description='客户端响应契约桩服务',
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
        skills=[
            AgentSkill(
                id='contract',
                name='contract',
                description='返回预定义响应形态',
                tags=['test'],
            )
        ],
    )
    handler = DefaultRequestHandler(
        agent_executor=StubExecutor(),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    return Starlette(
        routes=[
            *create_agent_card_routes(card),
            *create_jsonrpc_routes(handler, '/'),
        ]
    )


async def verify_return_immediately() -> None:
    async with httpx.AsyncClient(trust_env=False) as hc:
        card = await A2ACardResolver(
            httpx_client=hc, base_url=f'http://127.0.0.1:{PORT}'
        ).get_agent_card()
        client = await create_client(
            agent=card,
            client_config=ClientConfig(streaming=False, httpx_client=hc),
        )
        request = SendMessageRequest(
            message=new_text_message('slow', role=Role.ROLE_USER),
            configuration=SendMessageConfiguration(return_immediately=True),
        )
        try:
            chunks = [chunk async for chunk in client.send_message(request)]
        finally:
            await client.close()
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.WhichOneof('payload') == 'task'
    assert chunk.task.status.state != TaskState.TASK_STATE_COMPLETED
    print('[通过] 非流式 return_immediately 可返回非终态 Task')
    await asyncio.sleep(0.4)


async def expect_error(query: str, state: str | None = None) -> None:
    try:
        await ask_agent(PORT, query)
    except AgentTaskError as exc:
        if state is not None:
            assert state in str(exc), (query, str(exc))
        print(f'[通过] {query} → AgentTaskError')
    else:
        raise AssertionError(f'{query} 应失败')


async def verify() -> None:
    assert await ask_agent(PORT, 'ok') == '任务答复'
    print('[通过] COMPLETED Task + Artifact')
    assert await ask_agent(PORT, 'direct') == '直接答复'
    print('[通过] 直接 ROLE_AGENT Message')
    await verify_return_immediately()
    await expect_error('fail', 'TASK_STATE_FAILED')
    await expect_error('input_required', 'TASK_STATE_INPUT_REQUIRED')
    await expect_error('direct_user')
    await expect_error('status_only')
    await expect_error('nontext')
    await expect_error('blank')


async def main() -> None:
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(), host='127.0.0.1', port=PORT, log_level='warning'
        )
    )
    task = asyncio.create_task(server.serve())
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            for _ in range(100):
                try:
                    response = await client.get(
                        f'http://127.0.0.1:{PORT}/.well-known/agent-card.json'
                    )
                    if response.status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.05)
            else:
                raise RuntimeError('桩服务未就绪')
        await verify()
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, timeout=10)


if __name__ == '__main__':
    asyncio.run(main())

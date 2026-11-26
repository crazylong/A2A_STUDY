"""第四篇 路线 A：A2A 客户端（两轮对话，展示任务状态机）

运行：uv run python article03_compare/currency_a2a_client.py
"""

import asyncio

import httpx

from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import (
    get_artifact_text,
    get_message_text,
    new_text_message,
)
from a2a.types import (
    CancelTaskRequest,
    GetTaskRequest,
    Role,
    SendMessageRequest,
    Task,
    TaskState,
)

BASE_URL = 'http://127.0.0.1:9995'


async def run_turn(client, text_query: str, task: Task | None = None) -> Task | None:
    """发一轮用户消息；若给了 task，就带 taskId 续聊同一任务。"""
    message = new_text_message(text_query, role=Role.ROLE_USER)
    if task is not None:
        message.task_id = task.id
        message.context_id = task.context_id

    task_obj = task
    async for chunk in client.send_message(SendMessageRequest(message=message)):
        kind = chunk.WhichOneof('payload')
        if kind == 'task':
            task_obj = chunk.task
            print(f'  [task]          id={task_obj.id[:8]}… state={TaskState.Name(task_obj.status.state)}')
        elif kind == 'status_update':
            update = chunk.status_update
            note = (
                get_message_text(update.status.message)
                if update.status.HasField('message')
                else ''
            )
            print(f'  [status_update] {TaskState.Name(update.status.state)} | {note}')
        elif kind == 'artifact_update':
            artifact = chunk.artifact_update.artifact
            print(f'  [artifact_update] name={artifact.name} | {get_artifact_text(artifact)}')
        elif kind == 'message':
            print(f'  [message]       {get_message_text(chunk.message)}')
    return task_obj


async def main():
    # trust_env=False：本机直连，不读系统代理（NO_PROXY 含 [::1] 时 httpx 会报 InvalidURL）
    async with httpx.AsyncClient(trust_env=False) as httpx_client:
        resolver = A2ACardResolver(httpx_client=httpx_client, base_url=BASE_URL)
        card = await resolver.get_agent_card()
        print(f'发现智能体: {card.name}，技能: {[s.id for s in card.skills]}')

        client = await create_client(
            agent=card,
            client_config=ClientConfig(streaming=True, httpx_client=httpx_client),
        )

        print('\n--- 第 1 轮：信息不全，服务端应追问 ---')
        print('用户: 帮我换算 100 美元')
        task = await run_turn(client, '帮我换算 100 美元')

        print('\n--- 第 2 轮：带同一个 taskId 续聊 ---')
        print('用户: 换成人民币')
        await run_turn(client, '换成人民币', task=task)

        print('\n--- 第 3 轮：GetTask 回查 + CancelTask 取消 ---')
        print('用户: 帮我换算 100 美元')
        task = await run_turn(client, '帮我换算 100 美元')
        fetched = await client.get_task(GetTaskRequest(id=task.id))
        print(
            f'  [get_task]      state={TaskState.Name(fetched.status.state)}'
        )
        cancelled = await client.cancel_task(CancelTaskRequest(id=task.id))
        print(
            f'  [cancel_task]   state={TaskState.Name(cancelled.status.state)}'
        )
        try:
            await client.cancel_task(CancelTaskRequest(id=task.id))
        except Exception as e:  # noqa: BLE001
            print(f'  [cancel_task]   二次取消被拒绝：{type(e).__name__}: {e}')

        await client.close()


if __name__ == '__main__':
    asyncio.run(main())
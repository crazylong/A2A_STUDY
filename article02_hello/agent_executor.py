"""篇二：HelloWorldAgentExecutor —— 业务逻辑与 A2A 任务生命周期的桥梁。

execute() 的五步就是 A2A 服务端的核心套路：
建 Task → 报 working → 干活 → 产 Artifact → 报 completed
"""

from a2a.helpers import (
    get_message_text,
    new_task_from_user_message,
    new_text_message,
    new_text_part,
)
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import TaskState


class HelloWorldAgent:
    """真正的"智能体"。这里不调 LLM，所以本篇不需要任何 API Key。"""

    async def invoke(self, user_request: str) -> str:
        return f'Hello, World! I have received your request ({user_request})'


class HelloWorldAgentExecutor(AgentExecutor):
    def __init__(self) -> None:
        self.agent = HelloWorldAgent()

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        # 1. 取任务：续聊用已有 Task，新请求则从用户 Message 建一个
        if context.current_task:
            task = context.current_task
        else:
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)

        # 2. TaskUpdater 负责向事件队列发状态/产物事件
        task_updater = TaskUpdater(
            event_queue=event_queue,
            task_id=task.id,
            context_id=task.context_id,
        )
        await task_updater.update_status(
            state=TaskState.TASK_STATE_WORKING,
            message=new_text_message('Processing request...'),
        )

        # 3. 从 Message 的 Part 里取文本，调用业务逻辑
        query = get_message_text(context.message)
        result = (
            await self.agent.invoke(user_request=query)
            if query
            else 'No text input is provided!'
        )

        # 4. 产出 Artifact（最终结果，区别于过程中的 Message）
        await task_updater.add_artifact(
            parts=[new_text_part(text=result, media_type='text/plain')]
        )
        print('Result: ', result)

        # 5. 任务完成
        await task_updater.update_status(
            state=TaskState.TASK_STATE_COMPLETED,
            message=new_text_message('Request is completed!'),
        )

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        raise NotImplementedError('Cancel is not supported.')
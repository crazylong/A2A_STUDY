"""篇二 2.10 路线 A：把汇率换算包装成 A2A 智能体。

与 2.3 的 HelloWorldAgentExecutor 同一套路，只是业务从"回显"换成"换算"，
并通过 TASK_STATE_INPUT_REQUIRED 展示多轮追问。
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
from a2a.types import Role, TaskState

from currency_core import convert, parse_request


class CurrencyAgent:
    """无 LLM 的确定性智能体：解析用户文本 → 换算 → 返回结论。"""

    def reply(self, user_texts: list[str]) -> dict:
        parsed = parse_request(user_texts)
        if parsed['status'] != 'ok':
            return parsed

        result = convert(
            parsed['amount'], parsed['from_currency'], parsed['to_currency']
        )
        if result['status'] != 'ok':
            return result

        return {
            'status': 'completed',
            'message': (
                f"{result['amount']:g} {result['from_currency']} ≈ "
                f"{result['converted']:g} {result['to_currency']}"
                f"（汇率 {result['rate']}，演示数据 as_of {result['as_of']}）"
            ),
        }


def _user_texts(context: RequestContext) -> list[str]:
    """把任务历史里的用户消息和本轮消息拼起来。

    续聊时"换成人民币"本身不含金额和源币种，需要从历史补全。
    只取 ROLE_USER，避免智能体自己的追问文本干扰解析。
    """
    texts = []
    if context.current_task:
        for message in context.current_task.history:
            if message.role == Role.ROLE_USER:
                text = get_message_text(message)
                if text:
                    texts.append(text)
    current = get_message_text(context.message)
    if current:
        texts.append(current)
    return texts


class CurrencyAgentExecutor(AgentExecutor):
    """A2A 服务端桥接层：Task 生命周期 + 状态机。"""

    def __init__(self) -> None:
        self.agent = CurrencyAgent()

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        if context.current_task:
            task = context.current_task
        else:
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(
            event_queue=event_queue,
            task_id=task.id,
            context_id=task.context_id,
        )
        await updater.update_status(
            state=TaskState.TASK_STATE_WORKING,
            message=new_text_message('正在解析金额与币种…'),
        )

        result = self.agent.reply(_user_texts(context))

        if result['status'] == 'input_required':
            # 非终态：任务留在看板上，客户端可用同一个 taskId 继续对话
            await updater.update_status(
                state=TaskState.TASK_STATE_INPUT_REQUIRED,
                message=new_text_message(result['message']),
            )
            return

        if result['status'] == 'error':
            await updater.update_status(
                state=TaskState.TASK_STATE_FAILED,
                message=new_text_message(result['message']),
            )
            return

        await updater.add_artifact(
            parts=[new_text_part(text=result['message'], media_type='text/plain')],
            name='conversion_result',
        )
        await updater.update_status(
            state=TaskState.TASK_STATE_COMPLETED,
            message=new_text_message('换算完成'),
        )

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        raise NotImplementedError('Cancel is not supported.')
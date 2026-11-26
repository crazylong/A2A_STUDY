"""第五篇《A2A通用服务底座》公共模块：A2A 客户端助手。"""

from dataclasses import dataclass

import httpx
from google.protobuf.json_format import MessageToDict

from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import get_message_text, new_text_message
from a2a.types import Artifact, Role, SendMessageRequest, TaskState

from common import agent_url

TIMEOUT = httpx.Timeout(120.0)


class AgentTaskError(RuntimeError):
    """下游任务没有成功完成，或完成了却没有返回可交付文本。"""


@dataclass
class AgentAnswer:
    text: str
    artifacts: list[Artifact]
    state: int | None


async def get_agent_card(
    target: int | str, httpx_client: httpx.AsyncClient | None = None
):
    if httpx_client is not None:
        resolver = A2ACardResolver(
            httpx_client=httpx_client, base_url=agent_url(target)
        )
        return await resolver.get_agent_card()
    async with httpx.AsyncClient(trust_env=False, timeout=TIMEOUT) as hc:
        resolver = A2ACardResolver(
            httpx_client=hc, base_url=agent_url(target)
        )
        return await resolver.get_agent_card()


def get_data_artifact(
    artifacts: list[Artifact], artifact_id: str
) -> dict | None:
    for artifact in artifacts:
        if artifact.artifact_id != artifact_id:
            continue
        for part in artifact.parts:
            if part.WhichOneof('content') == 'data':
                value = MessageToDict(part.data)
                return value if isinstance(value, dict) else None
    return None


async def ask_agent_detailed(target: int | str, query: str) -> AgentAnswer:
    async with httpx.AsyncClient(trust_env=False, timeout=TIMEOUT) as hc:
        card = await get_agent_card(target, hc)
        client = await create_client(
            agent=card,
            client_config=ClientConfig(streaming=False, httpx_client=hc),
        )
        request = SendMessageRequest(
            message=new_text_message(query, role=Role.ROLE_USER)
        )
        texts: list[str] = []
        artifacts: list[Artifact] = []
        direct_message = None
        saw_task = False
        final_state: int | None = None
        status_note = ''
        try:
            async for chunk in client.send_message(request):
                which = chunk.WhichOneof('payload')
                if which == 'task':
                    saw_task = True
                    final_state = chunk.task.status.state
                    if chunk.task.status.HasField('message'):
                        status_note = get_message_text(
                            chunk.task.status.message
                        )
                    artifacts.extend(chunk.task.artifacts)
                    for artifact in chunk.task.artifacts:
                        texts.extend(
                            p.text
                            for p in artifact.parts
                            if p.WhichOneof('content') == 'text'
                            and p.text.strip()
                        )
                elif which == 'status_update':
                    saw_task = True
                    final_state = chunk.status_update.status.state
                    if chunk.status_update.status.HasField('message'):
                        status_note = get_message_text(
                            chunk.status_update.status.message
                        )
                elif which == 'artifact_update':
                    saw_task = True
                    artifact = chunk.artifact_update.artifact
                    artifacts.append(artifact)
                    texts.extend(
                        p.text
                        for p in artifact.parts
                        if p.WhichOneof('content') == 'text' and p.text
                    )
                elif which == 'message' and not saw_task:
                    direct_message = chunk.message
        finally:
            await client.close()

    if saw_task:
        if final_state != TaskState.TASK_STATE_COMPLETED:
            state_name = (
                TaskState.Name(final_state)
                if final_state is not None
                else 'UNKNOWN'
            )
            detail = f'：{status_note}' if status_note else ''
            raise AgentTaskError(
                f'下游任务未完成（{state_name}）{detail}'
            )
        if not texts:
            raise AgentTaskError('下游任务已完成，但没有返回可交付文本')
        return AgentAnswer('\n'.join(texts), artifacts, final_state)

    if direct_message is None:
        raise AgentTaskError('服务端既没返回任务也没返回消息')
    if direct_message.role != Role.ROLE_AGENT:
        raise AgentTaskError('直接响应不是智能体答复')
    text = get_message_text(direct_message)
    if not text.strip():
        raise AgentTaskError('直接响应没有可交付文本')
    return AgentAnswer(text, [], None)


async def ask_agent(target: int | str, query: str) -> str:
    return (await ask_agent_detailed(target, query)).text

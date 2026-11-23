"""篇三公共模块：A2A 客户端助手。

发现 Agent Card → 发消息 → 收集 Artifact 文本。
注意：httpx 默认超时 5 秒，LLM 智能体必须显式放宽。
"""

import httpx

from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import new_text_message
from a2a.types import Role, SendMessageRequest

from common import HOST

# LLM 推理 + 多轮工具调用可能较慢，统一放宽到 120 秒
TIMEOUT = httpx.Timeout(120.0)


async def ask_agent(port: int, query: str) -> str:
    """向指定端口的 A2A 智能体提问，返回全部 Artifact 文本。"""
    async with httpx.AsyncClient(trust_env=False, timeout=TIMEOUT) as hc:
        resolver = A2ACardResolver(
            httpx_client=hc, base_url=f'http://{HOST}:{port}'
        )
        card = await resolver.get_agent_card()
        client = await create_client(
            agent=card,
            client_config=ClientConfig(streaming=False, httpx_client=hc),
        )
        request = SendMessageRequest(
            message=new_text_message(query, role=Role.ROLE_USER)
        )
        texts: list[str] = []
        async for chunk in client.send_message(request):
            # chunk 是 StreamResponse（proto oneof：task/message/status_update/artifact_update）
            which = chunk.WhichOneof('payload')
            if which == 'task':
                for artifact in chunk.task.artifacts:
                    texts.extend(p.text for p in artifact.parts if p.text)
            elif which == 'artifact_update':
                texts.extend(
                    p.text for p in chunk.artifact_update.artifact.parts if p.text
                )
            elif which == 'message':
                texts.extend(p.text for p in chunk.message.parts if p.text)
        await client.close()
        return '\n'.join(texts)
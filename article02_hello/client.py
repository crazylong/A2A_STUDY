"""篇二：A2A 客户端演示（a2a-sdk 1.3.1）

依次演示：发现 Agent Card → 非流式调用 → 流式调用。
运行：uv run python article02_hello/client.py
"""

import asyncio

import httpx

from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import new_text_message
from a2a.types import Role, SendMessageRequest

BASE_URL = 'http://127.0.0.1:9999'


async def get_agent_card():
    """第一步：发现。从 /.well-known/agent-card.json 拉取名片。"""
    # trust_env=False：本机直连，不读系统代理配置
    # （某些环境的 NO_PROXY 含 [::1] 写法，httpx 解析会直接报错）
    async with httpx.AsyncClient(trust_env=False) as httpx_client:
        resolver = A2ACardResolver(
            httpx_client=httpx_client, base_url=BASE_URL
        )
        card = await resolver.get_agent_card()
    print(f'发现智能体: {card.name} v{card.version}')
    print(f'技能: {[s.id for s in card.skills]}')
    return card


async def send_message(card, text_query: str, streaming: bool):
    """第二/三步：发消息。streaming 决定走 message/send 还是 message/stream。"""
    # 注入 trust_env=False 的 httpx 客户端，避免系统代理配置干扰本机直连
    async with httpx.AsyncClient(trust_env=False) as httpx_client:
        client = await create_client(
            agent=card,
            client_config=ClientConfig(
                streaming=streaming, httpx_client=httpx_client
            ),
        )
        message = new_text_message(text_query, role=Role.ROLE_USER)
        request = SendMessageRequest(message=message)

        mode = '流式 message/stream' if streaming else '非流式 message/send'
        print(f'\n--- {mode} ---')
        async for chunk in client.send_message(request):
            # 每个 chunk 是 StreamResponse：task / message / status_update / artifact_update 四选一
            print(chunk)
        await client.close()


async def main():
    card = await get_agent_card()
    await send_message(card, 'Hi there!', streaming=False)
    await send_message(card, 'Hi there!', streaming=True)


if __name__ == '__main__':
    asyncio.run(main())
"""PolicyAgent 的 Agent Stack 版本（第八篇《AgentStack平台适配》、第九篇《AgentStack兼容性与故障排查》）。

与第五至七篇使用的 A2A v1.0 代码相比，主要区别：
- 不再自己管 LLM 密钥/端点，而是向平台申请 LLM 扩展（LLMServiceExtensionSpec），
  由 Agent Stack 统一提供模型推理（llm_fulfillments 里带 api_base/api_key/api_model）
- 用 agentstack_sdk.Server 包装，注册名 PolicyAgent，供平台发现与调用

注意版本事实（2026-11 实测）：agentstack-sdk 0.7.1 依赖 a2a-sdk 0.3.24（v0.3 协议），
尚未跟进 A2A v1.0。因此本目录是独立环境，与第五至七篇的 v1.0 代码不混用。

本地运行（不接平台时 LLM 扩展不可用，会提示需要平台）：
  uv run --project article05_agentstack/policy_agent server
"""

import asyncio
import os
from pathlib import Path
from typing import Annotated

import httpx

from a2a.types import Message
from a2a.utils.message import get_message_text
from agentstack_sdk.a2a.extensions import (
    LLMServiceExtensionServer,
    LLMServiceExtensionSpec,
)
from agentstack_sdk.a2a.types import AgentMessage
from agentstack_sdk.server import Server
from agentstack_sdk.server.context import RunContext
from openai import AsyncOpenAI

POLICY_TEXT = (
    Path(__file__).resolve().parent / 'data' / 'sample_policy.md'
).read_text(encoding='utf-8')

SYSTEM_PROMPT = (
    '你是保单咨询专员。只能依据提供的保单内容回答；'
    '保单中没有的信息，回答"保单中未提及该信息"。用中文简洁作答。'
)

server = Server()
_llm_clients: dict[tuple[str, str, str], AsyncOpenAI] = {}
_llm_lock = asyncio.Lock()


async def _get_llm_client(api_base: str, api_key: str, api_model: str) -> AsyncOpenAI:
    key = (api_base, api_key, api_model)
    async with _llm_lock:
        client = _llm_clients.get(key)
        if client is not None:
            return client
        old_clients = [
            old
            for old_key, old in _llm_clients.items()
            if old_key != key
        ]
        _llm_clients.clear()
        client = AsyncOpenAI(
            base_url=api_base,
            api_key=api_key,
            max_retries=2,
            http_client=httpx.AsyncClient(
                trust_env=False, timeout=httpx.Timeout(120.0)
            ),
        )
        _llm_clients[key] = client
    for old in old_clients:
        await old.close()
    return client


@server.agent(name='PolicyAgent')
async def policy_agent(
    input: Message,
    context: RunContext,
    llm: Annotated[
        LLMServiceExtensionServer,
        # 不指定具体模型：由平台侧的模型提供方配置决定（可接百炼等 OpenAI 兼容端点；
        # agentstack-cli 0.7.1 对百炼的原生支持以 `agentstack model add` 实际选项为准）
        LLMServiceExtensionSpec.single_demand(),
    ],
):
    """保单问答：LLM 由 Agent Stack 平台的 LLM 扩展提供。"""
    prompt = get_message_text(input)

    fulfillment = None
    if llm and llm.data and llm.data.llm_fulfillments:
        fulfillment = llm.data.llm_fulfillments.get('default')
    if not fulfillment or not fulfillment.api_key:
        yield AgentMessage(
            text='LLM 服务不可用：请在 Agent Stack 平台为本智能体启用 LLM 扩展。'
        )
        return

    client = await _get_llm_client(
        fulfillment.api_base,
        fulfillment.api_key,
        fulfillment.api_model,
    )
    # 平台下发的可能是非 Qwen 模型；只有模型名含 qwen 时才发送该参数
    kwargs = {}
    if 'qwen' in (fulfillment.api_model or '').lower():
        kwargs['extra_body'] = {'enable_thinking': False}
    resp = await client.chat.completions.create(
        model=fulfillment.api_model,
        messages=[
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'system', 'content': f'保单内容：\n{POLICY_TEXT}'},
            {'role': 'user', 'content': prompt},
        ],
        **kwargs,
    )
    yield AgentMessage(text=resp.choices[0].message.content or 'I don\'t know')


def run():
    """本地启动入口。

    实测坑（agentstack-sdk 0.7.1 + a2a-sdk 0.3.24 + fastapi 0.163）：
    Server.run() 会把 auth_backend 关键字一路透传给 FastAPI 构造器，
    抛 TypeError: unexpected keyword argument 'auth_backend'。
    这里绕过 Server.serve()，直接用官方 create_app() 组装应用（不传 auth_backend），
    再用 uvicorn 启动。平台托管部署时由平台注入自己的启动方式。
    """
    import uvicorn
    from agentstack_sdk.server.app import create_app
    from agentstack_sdk.server.store.memory_context_store import (
        InMemoryContextStore,
    )

    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', '8000'))
    # HOST 只决定监听；名片必须用外部可达地址，不能广播 0.0.0.0
    public_url = os.environ.get('PUBLIC_URL', '').rstrip('/')
    if not public_url:
        public_url = f'http://127.0.0.1:{port}'

    context_store = InMemoryContextStore()
    # 注意：_agent_factory 是 SDK 私有 API，升级后需复核；
    # 平台托管模式由平台注入启动方式，不走这里。
    agent = server._agent_factory(context_store.modify_dependencies)
    agent.card.url = public_url
    app = create_app(agent)          # 不传 auth_backend，绕开 SDK bug
    uvicorn.run(app, host=host, port=port)


if __name__ == '__main__':
    run()
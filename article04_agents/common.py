"""第五篇《A2A通用服务底座》公共模块：环境、地址与 LLM 客户端。"""

import os
from pathlib import Path
from threading import Lock

import httpx
from dotenv import load_dotenv
from openai import AsyncOpenAI

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / '.env')

BIND_HOST = os.getenv('BIND_HOST', '127.0.0.1')
_DEFAULT_A2A_HOST = '127.0.0.1' if BIND_HOST in ('0.0.0.0', '::') else BIND_HOST
A2A_HOST = os.getenv('A2A_HOST', _DEFAULT_A2A_HOST)
PUBLIC_URL_TEMPLATE = os.getenv('PUBLIC_URL_TEMPLATE', '').strip()

PORTS = {
    'policy': int(os.getenv('POLICY_AGENT_PORT', '9999')),
    'research': int(os.getenv('RESEARCH_AGENT_PORT', '9998')),
    'provider': int(os.getenv('PROVIDER_AGENT_PORT', '9997')),
    'healthcare': int(os.getenv('HEALTHCARE_AGENT_PORT', '9996')),
}
AGENT_URLS = {
    name: os.getenv(f'{name.upper()}_AGENT_URL', '').strip().rstrip('/')
    for name in PORTS
}

LLM_MODEL = os.environ['LLM_MODEL']
LLM_ENABLE_THINKING = os.getenv('LLM_ENABLE_THINKING', 'false').lower() in (
    '1',
    'true',
    'yes',
    'on',
)

_llm_client: AsyncOpenAI | None = None
_llm_client_lock = Lock()


def agent_url(target: int | str) -> str:
    """按端口或智能体名返回可达地址；独立 URL 优先于主机模板。"""
    if isinstance(target, str):
        explicit = AGENT_URLS.get(target)
        if explicit:
            return explicit
        port = PORTS[target]
    else:
        port = target
    if PUBLIC_URL_TEMPLATE:
        return PUBLIC_URL_TEMPLATE.format(port=port).rstrip('/')
    return f'http://{A2A_HOST}:{port}'


def llm_client() -> AsyncOpenAI:
    """返回进程级客户端；同步初始化使用线程锁避免并发重复创建。"""
    global _llm_client
    if _llm_client is None:
        with _llm_client_lock:
            if _llm_client is None:
                _llm_client = AsyncOpenAI(
                    base_url=os.environ['LLM_BASE_URL'],
                    api_key=os.environ['LLM_API_KEY'],
                    max_retries=2,
                    http_client=httpx.AsyncClient(
                        trust_env=False, timeout=httpx.Timeout(120.0)
                    ),
                )
    return _llm_client


async def close_llm_client() -> None:
    global _llm_client
    with _llm_client_lock:
        client = _llm_client
        _llm_client = None
    if client is not None:
        await client.close()


def thinking_extra_body(model: str | None = None) -> dict | None:
    if 'qwen' not in (model or LLM_MODEL).lower():
        return None
    return {'enable_thinking': LLM_ENABLE_THINKING}


async def chat(system: str, user: str) -> str:
    client = llm_client()
    kwargs = {}
    extra_body = thinking_extra_body()
    if extra_body is not None:
        kwargs['extra_body'] = extra_body
    resp = await client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': user},
        ],
        **kwargs,
    )
    return resp.choices[0].message.content or ''

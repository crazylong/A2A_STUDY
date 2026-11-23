"""篇三公共模块：环境加载与 LLM 工厂。

LLM 走 OpenAI 兼容接口（.env 配置），不绑定具体厂商。
"""

import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from openai import AsyncOpenAI

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / '.env')

HOST = '127.0.0.1'
PORTS = {
    'policy': int(os.getenv('POLICY_AGENT_PORT', '9999')),
    'research': int(os.getenv('RESEARCH_AGENT_PORT', '9998')),
    'provider': int(os.getenv('PROVIDER_AGENT_PORT', '9997')),
    'healthcare': int(os.getenv('HEALTHCARE_AGENT_PORT', '9996')),
}


def llm_client() -> AsyncOpenAI:
    # trust_env=False：不读系统代理配置（某些环境 NO_PROXY 含 [::1]，
    # httpx 解析会直接抛 InvalidURL），LLM 调用放宽超时到 120 秒
    return AsyncOpenAI(
        base_url=os.environ['LLM_BASE_URL'],
        api_key=os.environ['LLM_API_KEY'],
        http_client=httpx.AsyncClient(
            trust_env=False, timeout=httpx.Timeout(120.0)
        ),
    )


LLM_MODEL = os.environ['LLM_MODEL']


async def chat(system: str, user: str) -> str:
    """一次简单的系统提示 + 用户消息对话。"""
    client = llm_client()
    resp = await client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': user},
        ],
        # qwen3 系列默认开思考模式，会把推理过程混进正文；关掉
        extra_body={'enable_thinking': False},
    )
    return resp.choices[0].message.content or ''
"""第六篇《跨框架智能体接入》：ResearchAgent —— 健康研究智能体（Google ADK + LiteLlm，经 ADK 官方适配器暴露为 A2A）。

对应课程 07 课。课程里用 Serper API 做网页搜索，这里简化为基于模型知识回答
（不引入额外搜索密钥）；协议接入方式与课程一致：ADK 官方 A2aAgentExecutor。

这是"跨框架互操作"的关键一环：ADK 写的智能体，与纯 SDK 写的 PolicyAgent、
LangGraph 写的 ProviderAgent 通过同一套 A2A 协议协作。

运行：uv run python article04_agents/research_agent.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from a2a.types import AgentSkill  # noqa: E402

from a2a_helpers import SanitizedExecutor, serve  # noqa: E402
from common import LLM_MODEL, PORTS, thinking_extra_body  # noqa: E402

from google.adk.a2a.executor.a2a_agent_executor import A2aAgentExecutor  # noqa: E402
from google.adk.agents import Agent  # noqa: E402
from google.adk.models.lite_llm import LiteLlm  # noqa: E402
from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402

_lite_llm_kwargs = {
    'model': f'openai/{LLM_MODEL}',
    'api_base': os.environ['LLM_BASE_URL'],
    'api_key': os.environ['LLM_API_KEY'],
}
_extra_body = thinking_extra_body()
if _extra_body is not None:
    _lite_llm_kwargs['extra_body'] = _extra_body

# ADK 通过 LiteLlm 接 OpenAI 兼容接口（模型名加 openai/ 前缀）
research_agent = Agent(
    name='health_research_agent',
    model=LiteLlm(**_lite_llm_kwargs),
    description='回答疾病知识与健康建议类问题的研究智能体',
    instruction=(
        '你是健康研究助手，用中文回答疾病知识、生活方式与健康建议类问题。'
        '回答要科学、克制：说明一般性知识，不做诊断，涉及具体病情时建议就医。'
        '分点作答，控制在 300 字以内。'
    ),
)

runner = Runner(
    agent=research_agent,
    app_name='health_research',
    session_service=InMemorySessionService(),
)

if __name__ == '__main__':
    serve(
        name='ResearchAgent',
        description='健康研究智能体（Google ADK 实现）：疾病知识与健康建议',
        skill=AgentSkill(
            id='health_research',
            name='健康研究',
            description='回答疾病知识、健康建议类问题（基于模型知识，不做诊断）',
            tags=['health', 'research', 'adk'],
            examples=['糖尿病有哪些类型？', '怎样科学降低胆固醇？'],
        ),
        port=PORTS['research'],
        executor=SanitizedExecutor(A2aAgentExecutor(runner=runner)),
    )
"""篇三：PolicyAgent —— 保单问答智能体（纯 a2a-sdk + LLM）。

对应课程 04~05 课：先有一个 QA 智能体，再包成 A2A Server。
这里 QA 逻辑 = 把虚构保单全文放进系统提示，让 LLM 据此回答。

运行：uv run python article03_agents/policy_agent.py
"""

from pathlib import Path

from a2a.types import AgentSkill

from a2a_helpers import serve
from common import PORTS, chat

POLICY_TEXT = (Path(__file__).parent / 'data' / 'sample_policy.md').read_text(
    encoding='utf-8'
)

SYSTEM_PROMPT = f"""你是保单咨询专员。只能依据下面的保单内容回答用户问题。
如果保单里没有相关信息，明确回答"保单中未提及该信息"，不要编造。
回答用中文，简洁、分点。

保单内容：
{POLICY_TEXT}
"""


async def answer(query: str) -> str:
    return await chat(SYSTEM_PROMPT, query)


if __name__ == '__main__':
    serve(
        name='PolicyAgent',
        description='解读示例健康保单的保障范围、共付比例与理赔流程',
        skill=AgentSkill(
            id='policy_qa',
            name='保单问答',
            description='回答保单保障范围、门诊/住院报销比例、理赔流程等问题',
            tags=['insurance', 'policy', 'qa'],
            examples=['门诊网内网外共付比例是多少？', '心理健康咨询报销吗？'],
        ),
        fn=answer,
        port=PORTS['policy'],
    )
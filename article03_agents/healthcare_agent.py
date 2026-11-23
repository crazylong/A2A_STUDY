"""篇三：HealthcareAgent —— 导诊与编排智能体（纯 a2a-sdk + LLM 路由）。

对应课程 11 课的编排角色（课程用 BeeAI RequirementAgent + HandoffTool，
这里用 LLM function calling 实现同样的"按需分发"语义，更透明易懂）。

它自己不回答专业问题，而是：
1. 让 LLM 判断该问哪个下游智能体（可多选、可多轮）
2. 通过 A2A 客户端把子任务发过去
3. 汇总下游结果，给用户最终答复

运行：uv run python article03_agents/healthcare_agent.py
（需先启动 policy / provider / research 三个智能体）
"""

import json

from a2a.types import AgentSkill

from a2a_client import ask_agent
from a2a_helpers import serve
from common import PORTS, LLM_MODEL, llm_client

DOWNSTREAM = {
    'policy': ('保单咨询', PORTS['policy'], '保障范围、报销比例、理赔流程等保单问题'),
    'provider': ('医生查询', PORTS['provider'], '按城市/科室查找医生'),
    'research': ('健康研究', PORTS['research'], '疾病知识、健康建议等研究类问题'),
}

TOOLS = [
    {
        'type': 'function',
        'function': {
            'name': f'ask_{key}',
            'description': f'把子任务交给{label}智能体：{desc}',
            'parameters': {
                'type': 'object',
                'properties': {
                    'question': {
                        'type': 'string',
                        'description': '要问下游智能体的完整问题（中文）',
                    }
                },
                'required': ['question'],
            },
        },
    }
    for key, (label, _port, desc) in DOWNSTREAM.items()
]

SYSTEM_PROMPT = """你是医疗导诊台。你不直接回答专业问题，而是把用户问题分发给合适的下游智能体：
- ask_policy：保单、报销、理赔相关
- ask_provider：找医生、医院相关
- ask_research：疾病知识、健康建议相关
一个问题可能需要多个智能体协作，可以多次调用工具。
拿到全部结果后，用中文给用户一份整合后的清晰答复，注明各部分来自哪个智能体。
如果用户问题与医疗无关，礼貌说明职责范围。"""


async def orchestrate(query: str) -> str:
    client = llm_client()
    messages = [
        {'role': 'system', 'content': SYSTEM_PROMPT},
        {'role': 'user', 'content': query},
    ]
    # 最多 5 轮工具调用，防止死循环
    for _ in range(5):
        resp = await client.chat.completions.create(
            model=LLM_MODEL, messages=messages, tools=TOOLS
        )
        msg = resp.choices[0].message
        if not msg.tool_calls:
            return msg.content or ''
        messages.append(msg.model_dump(exclude_none=True))
        for call in msg.tool_calls:
            key = call.function.name.removeprefix('ask_')
            args = json.loads(call.function.arguments)
            label, port, _ = DOWNSTREAM[key]
            print(f'[HealthcareAgent] 分发子任务 → {label}: {args["question"]}')
            try:
                answer = await ask_agent(port, args['question'])
            except Exception as e:  # noqa: BLE001
                answer = f'（{label}智能体调用失败：{e}）'
            messages.append(
                {
                    'role': 'tool',
                    'tool_call_id': call.id,
                    'content': answer,
                }
            )
    return '（编排轮次超限，请简化问题重试）'


if __name__ == '__main__':
    serve(
        name='HealthcareAgent',
        description='医疗导诊台：理解用户问题，经 A2A 分发给保单/医生/研究智能体并汇总答复',
        skill=AgentSkill(
            id='healthcare_triage',
            name='导诊编排',
            description='综合医疗咨询入口，自动路由到保单、医生查询、健康研究智能体',
            tags=['healthcare', 'orchestrator', 'triage'],
            examples=['我最近焦虑，北京能看谁？保单报销吗？'],
        ),
        fn=orchestrate,
        port=PORTS['healthcare'],
    )
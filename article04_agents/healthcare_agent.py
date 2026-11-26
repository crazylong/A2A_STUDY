"""第七篇《导诊编排与可靠性》：HealthcareAgent 导诊与编排智能体。"""

import asyncio
import json
import logging
import os

import httpx

from a2a.helpers import new_data_part
from a2a.types import AgentSkill

from a2a_client import TIMEOUT, ask_agent, get_agent_card
from a2a_helpers import TaskResult, _public_error, serve
from common import PORTS, LLM_MODEL, close_llm_client, llm_client, thinking_extra_body

logger = logging.getLogger(__name__)

DOWNSTREAM_PORTS = {
    'policy': PORTS['policy'],
    'provider': PORTS['provider'],
    'research': PORTS['research'],
}

SYSTEM_PROMPT = """你是医疗导诊台。你不直接回答专业问题，而是把用户问题分发给合适的下游智能体：
- ask_policy：保单、报销、理赔相关
- ask_provider：找医生、医院相关
- ask_research：疾病知识、健康建议相关
一个问题可能需要多个智能体协作，可以多次调用工具。
拿到全部结果后，用中文给用户一份整合后的清晰答复，注明各部分来自哪个智能体。
只能引用下游返回的内容；下游没有提供的信息，明确说"下游未返回"，不要自行补充。
如果用户问题与医疗无关，礼貌说明职责范围。"""

_DOWNSTREAM: dict[str, dict] = {}
_TOOLS: list[dict] | None = None
_DOWNSTREAM_LOCK = asyncio.Lock()
_SEMAPHORE: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _SEMAPHORE
    if _SEMAPHORE is None:
        _SEMAPHORE = asyncio.Semaphore(
            int(os.getenv('MAX_PARALLEL_TOOL_CALLS', '2'))
        )
    return _SEMAPHORE


async def load_downstream() -> list[dict]:
    global _TOOLS
    if _TOOLS is not None:
        return _TOOLS
    async with _DOWNSTREAM_LOCK:
        if _TOOLS is not None:
            return _TOOLS

        async with httpx.AsyncClient(trust_env=False, timeout=TIMEOUT) as hc:
            try:
                cards = await asyncio.gather(
                    *(
                        get_agent_card(key, hc)
                        for key in DOWNSTREAM_PORTS
                    )
                )
            except Exception as e:  # noqa: BLE001
                raise RuntimeError(
                    '无法从下游名片生成路由，请先启动 policy/provider/research '
                    f'三个智能体：{type(e).__name__}'
                ) from e

        tools = []
        for key, card in zip(DOWNSTREAM_PORTS, cards, strict=True):
            skill = card.skills[0] if card.skills else None
            label = (skill.name if skill and skill.name else card.name) or key
            description = (
                skill.description
                if skill and skill.description
                else card.description
            ) or label
            examples = (
                f"；示例：{' / '.join(skill.examples[:2])}"
                if skill and skill.examples
                else ''
            )
            _DOWNSTREAM[key] = {
                'label': label,
                'target': key,
                'card_name': card.name,
            }
            tools.append(
                {
                    'type': 'function',
                    'function': {
                        'name': f'ask_{key}',
                        'description': (
                            f'把子任务交给 {card.name}（{label}）：{description}'
                            f'{examples}'
                        ),
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
            )
            print(
                f'[HealthcareAgent] 从名片生成工具 ask_{key}：'
                f'{card.name} / {label}'
            )

        _TOOLS = tools
        return tools


def _record(target: str, ok: bool, error: str | None = None) -> dict:
    label = _DOWNSTREAM.get(target, {}).get('label', target)
    return {'agent': label, 'target': target, 'ok': ok, 'error': error}


async def _dispatch(call):
    key = call.function.name.removeprefix('ask_')
    target = _DOWNSTREAM.get(key)
    if target is None:
        record = _record(key, False, '未知下游')
        return call.id, f'（未知下游：{call.function.name}）', record
    try:
        args = json.loads(call.function.arguments)
        question = args['question']
        if not isinstance(question, str) or not question.strip():
            raise ValueError('question 必须是非空字符串')
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        record = _record(key, False, f'参数解析失败：{type(e).__name__}')
        return call.id, f'（参数解析失败：{e}）', record

    label = target['label']
    async with _get_semaphore():
        print(f'[HealthcareAgent] 分发子任务 → {label}: {question}')
        try:
            answer = await ask_agent(key, question)
        except Exception as e:  # noqa: BLE001
            logger.exception('下游智能体调用失败：%s', label)
            detail = _public_error(e)
            record = _record(key, False, detail)
            return call.id, f'（{label}智能体调用失败：{detail}）', record
    return call.id, answer, _record(key, True)


def _task_result(text: str, records: list[dict]) -> TaskResult:
    if not records:
        return TaskResult(text=text)
    succeeded = sum(1 for record in records if record['ok'])
    summary = {
        'total': len(records),
        'succeeded': succeeded,
        'failed': len(records) - succeeded,
    }
    report = {'calls': records, 'summary': summary}
    return TaskResult(
        text=text,
        extra_parts=[new_data_part(report, media_type='application/json')],
        metadata={'dispatch_summary': summary},
    )


async def orchestrate(query: str) -> TaskResult:
    client = llm_client()
    tools = await load_downstream()
    messages = [
        {'role': 'system', 'content': SYSTEM_PROMPT},
        {'role': 'user', 'content': query},
    ]
    extra_body = thinking_extra_body()
    records: list[dict] = []

    for _ in range(5):
        kwargs = {'tools': tools}
        if extra_body is not None:
            kwargs['extra_body'] = extra_body
        resp = await client.chat.completions.create(
            model=LLM_MODEL, messages=messages, **kwargs
        )
        msg = resp.choices[0].message
        if not msg.tool_calls:
            return _task_result(msg.content or '（模型没有返回内容）', records)
        messages.append(msg.model_dump(exclude_none=True))
        results = await asyncio.gather(
            *(_dispatch(call) for call in msg.tool_calls)
        )
        for call_id, answer, record in results:
            records.append(record)
            messages.append(
                {'role': 'tool', 'tool_call_id': call_id, 'content': answer}
            )
    return _task_result('（编排轮次超限，请简化问题重试）', records)


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
        on_shutdown=close_llm_client,
    )

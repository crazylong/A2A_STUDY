"""无 LLM 的部分失败、缓存边界、退出码与错误脱敏回归。"""

import asyncio
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'article04_agents'))
os.environ.setdefault('LLM_MODEL', 'dispatch-stub')
os.environ.setdefault('LLM_BASE_URL', 'http://127.0.0.1:1')
os.environ.setdefault('LLM_API_KEY', 'not-used')

import httpx  # noqa: E402
from a2a.helpers import get_message_text, new_text_message  # noqa: E402
from a2a.types import (  # noqa: E402
    Artifact,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)

from a2a_client import (  # noqa: E402
    AgentAnswer,
    AgentTaskError,
    get_data_artifact,
)
from a2a_helpers import SanitizedExecutor, _public_error  # noqa: E402
import demo_client  # noqa: E402
import healthcare_agent  # noqa: E402


async def fake_ask_agent(target: str, query: str) -> str:
    if target == 'policy':
        return '保单答复'
    raise AgentTaskError('下游任务未完成（TASK_STATE_FAILED）：测试失败')


def make_call(call_id: str, target: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(
            name=f'ask_{target}',
            arguments=json.dumps({'question': '测试问题'}),
        ),
    )


def report_artifact(report: dict | None) -> list[Artifact]:
    if report is None:
        return []
    result = healthcare_agent._task_result('整合答复', report['calls'])
    return [
        Artifact(artifact_id='dispatch-report', parts=result.extra_parts)
    ]


async def verify_dispatch() -> None:
    healthcare_agent._DOWNSTREAM = {
        'policy': {'label': '保单问答', 'target': 'policy'},
        'provider': {'label': '医生查询', 'target': 'provider'},
    }
    healthcare_agent.ask_agent = fake_ask_agent

    _, _, ok_record = await healthcare_agent._dispatch(make_call('1', 'policy'))
    with patch.object(healthcare_agent.logger, 'exception') as logged:
        _, answer, failed_record = await healthcare_agent._dispatch(
            make_call('2', 'provider')
        )
    logged.assert_called_once()
    assert ok_record['ok'] is True
    assert failed_record['ok'] is False
    assert '调用失败' in answer

    result = healthcare_agent._task_result(
        '整合答复', [ok_record, failed_record]
    )
    artifact = Artifact(
        artifact_id='dispatch-report', parts=result.extra_parts
    )
    report = get_data_artifact([artifact], 'dispatch-report')
    assert report is not None
    assert report['summary'] == {'total': 2.0, 'succeeded': 1.0, 'failed': 1.0}
    assert report['calls'][1]['ok'] is False
    print('[通过] 部分失败保留答复并生成 dispatch-report')
    print('[通过] 汇总计数 total=2, succeeded=1, failed=1')


async def verify_dispatch_sanitization() -> None:
    secret = 'http://user:private-secret@internal.example/v1'
    healthcare_agent._DOWNSTREAM = {
        'policy': {'label': '保单问答', 'target': 'policy'},
    }

    async def leaking_ask_agent(target, query):
        raise AgentTaskError(f'下游任务失败：{secret}')

    healthcare_agent.ask_agent = leaking_ask_agent
    with patch.object(healthcare_agent.logger, 'exception') as logged:
        _, answer, record = await healthcare_agent._dispatch(
            make_call('secret', 'policy')
        )
    logged.assert_called_once()
    assert record['ok'] is False
    assert 'AGENT_EXECUTION_FAILED' in record['error']
    assert secret not in record['error']
    assert secret not in answer
    print('[通过] 编排报告与 LLM 回填不包含下游原始异常')


async def verify_executor_sanitization() -> None:
    secret = 'http://user:private-secret@internal.example/v1'

    class RecordingQueue:
        def __init__(self):
            self.events = []

        async def enqueue_event(self, event):
            self.events.append(event)

    class RawFailureExecutor:
        async def execute(self, context, event_queue):
            await event_queue.enqueue_event(
                TaskStatusUpdateEvent(
                    task_id='task-1',
                    context_id='context-1',
                    status=TaskStatus(
                        state=TaskState.TASK_STATE_FAILED,
                        message=new_text_message(secret),
                    ),
                )
            )

        async def cancel(self, context, event_queue):
            raise AssertionError('测试不应触发取消')

    queue = RecordingQueue()
    await SanitizedExecutor(RawFailureExecutor()).execute(
        SimpleNamespace(), queue
    )
    public = get_message_text(queue.events[0].status.message)
    assert 'AGENT_EXECUTION_FAILED' in public
    assert secret not in public
    print('[通过] 框架 Executor 失败事件在对外前完成脱敏')


async def verify_cold_start() -> None:
    async def card_for(target, httpx_client):
        return SimpleNamespace(
            name=f'{target}Agent',
            description=f'{target} description',
            skills=[
                SimpleNamespace(
                    name=f'{target} skill',
                    description=f'{target} skill description',
                    examples=[],
                )
            ],
        )

    for missing in ('policy', 'provider', 'research'):
        async def maybe_unavailable_card(
            target, httpx_client, missing=missing
        ):
            if target == missing:
                raise httpx.ConnectError(f'{target} unavailable')
            return await card_for(target, httpx_client)

        healthcare_agent._TOOLS = None
        healthcare_agent._DOWNSTREAM = {}
        healthcare_agent._DOWNSTREAM_LOCK = asyncio.Lock()
        healthcare_agent.get_agent_card = maybe_unavailable_card
        try:
            await healthcare_agent.load_downstream()
        except RuntimeError as exc:
            assert 'policy/provider/research' in str(exc)
        else:
            raise AssertionError(f'冷启动缺少 {missing} 名片时应失败')
        assert healthcare_agent._TOOLS is None
        assert healthcare_agent._DOWNSTREAM == {}
        print(f'[通过] 冷启动单独缺少 {missing} 名片时失败且不写半成品缓存')


class FakeMessage:
    def __init__(self, tool_calls=None, content=''):
        self.tool_calls = tool_calls or []
        self.content = content

    def model_dump(self, exclude_none=False):
        return {
            'role': 'assistant',
            'tool_calls': [
                {
                    'id': call.id,
                    'type': 'function',
                    'function': {
                        'name': call.function.name,
                        'arguments': call.function.arguments,
                    },
                }
                for call in self.tool_calls
            ],
            'content': self.content,
        }


class FakeCompletions:
    def __init__(self, messages):
        self.messages = iter(messages)

    async def create(self, **kwargs):
        message = next(self.messages)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message)]
        )


async def verify_warm_cache() -> None:
    healthcare_agent._TOOLS = [
        {'type': 'function', 'function': {'name': f'ask_{name}'}}
        for name in ('policy', 'provider', 'research')
    ]
    healthcare_agent._DOWNSTREAM = {
        'policy': {'label': '保单问答', 'target': 'policy'},
        'provider': {'label': '医生查询', 'target': 'provider'},
        'research': {'label': '健康研究', 'target': 'research'},
    }

    async def run_case(fake_ask, text: str, succeeded: int) -> None:
        healthcare_agent.ask_agent = fake_ask
        first = FakeMessage(
            [
                make_call('1', target)
                for target in ('policy', 'provider', 'research')
            ]
        )
        fake_client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=FakeCompletions(
                    [first, FakeMessage(content=text)]
                )
            )
        )
        healthcare_agent.llm_client = lambda: fake_client

        result = await healthcare_agent.orchestrate('测试问题')
        artifact = Artifact(
            artifact_id='dispatch-report', parts=result.extra_parts
        )
        report = get_data_artifact([artifact], 'dispatch-report')
        assert result.text == text
        assert report is not None
        assert report['summary'] == {
            'total': 3.0,
            'succeeded': float(succeeded),
            'failed': float(3 - succeeded),
        }

    with patch.object(healthcare_agent.logger, 'exception') as logged:
        await run_case(fake_ask_agent, '部分成功答复', 1)
    assert logged.call_count == 2
    print('[通过] 热缓存下部分下游失败仍返回结构化报告')

    async def all_fail(target, query):
        raise AgentTaskError('下游任务未完成（TASK_STATE_FAILED）：测试失败')

    with patch.object(healthcare_agent.logger, 'exception') as logged:
        await run_case(all_fail, '全部失败答复', 0)
    assert logged.call_count == 3
    print('[通过] 热缓存下三个下游全不可调用时仍返回结构化报告')


async def verify_exit_codes() -> None:
    demo_client.QUESTIONS = ['测试问题']
    failed_records = [
        {'agent': '保单问答', 'target': 'policy', 'ok': False, 'error': '测试失败'}
    ]
    success_records = [
        {'agent': '保单问答', 'target': 'policy', 'ok': True, 'error': None}
    ]

    async def full_success(target, query):
        return AgentAnswer(
            '完整答复',
            report_artifact({'calls': success_records}),
            2,
        )

    async def partial_failure(target, query):
        return AgentAnswer(
            '部分答复',
            report_artifact({'calls': failed_records}),
            2,
        )

    async def outer_failure(target, query):
        raise AgentTaskError('外层任务失败')

    demo_client.ask_agent_detailed = full_success
    assert await demo_client.main() == 0
    demo_client.ask_agent_detailed = partial_failure
    assert await demo_client.main() == 2
    demo_client.ask_agent_detailed = outer_failure
    assert await demo_client.main() == 1
    print('[通过] demo 退出码 0/1/2 与完整成功/外层失败/部分失败一致')


def verify_error_sanitization() -> None:
    secret = 'http://user:private-secret@internal.example/v1'
    public = _public_error(RuntimeError(secret))
    assert 'AGENT_EXECUTION_FAILED' in public
    assert 'private-secret' not in public
    assert 'internal.example' not in public
    print('[通过] 生产异常仅返回稳定错误码与脱敏摘要')


async def verify() -> None:
    await verify_dispatch()
    await verify_dispatch_sanitization()
    await verify_executor_sanitization()
    await verify_cold_start()
    await verify_warm_cache()
    await verify_exit_codes()
    verify_error_sanitization()


if __name__ == '__main__':
    asyncio.run(verify())

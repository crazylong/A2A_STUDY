"""第七篇《导诊编排与可靠性》：演示客户端。"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from a2a_client import (  # noqa: E402
    ask_agent_detailed,
    get_data_artifact,
)
from common import PORTS  # noqa: E402

QUESTIONS = [
    '我最近经常焦虑失眠，住在北京。可以找谁看诊？我的保单对心理咨询是怎么报销的？',
    '怎样科学地降低胆固醇？',
]


async def main() -> int:
    failures = 0
    partial = False
    for q in QUESTIONS:
        print(f'\n{"=" * 60}\n用户: {q}\n{"=" * 60}')
        try:
            answer = await ask_agent_detailed(PORTS['healthcare'], q)
            print(answer.text)
            report = get_data_artifact(answer.artifacts, 'dispatch-report')
            if report:
                summary = report.get('summary', {})
                failed = int(summary.get('failed', 0))
                total = int(summary.get('total', 0))
                if failed:
                    partial = True
                    print(f'[部分失败] {failed}/{total} 个下游失败')
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f'[失败] {type(e).__name__}: {e}')
    if failures:
        print(f'\n{failures}/{len(QUESTIONS)} 个问题失败')
        return 1
    if partial:
        print('\n部分下游失败，请检查 dispatch-report。')
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))

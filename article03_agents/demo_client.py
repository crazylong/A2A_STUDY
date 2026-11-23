"""篇三：演示客户端 —— 向 HealthcareAgent 提两个典型问题。

先运行 run_all.sh 启动全部智能体，再：
  uv run python article03_agents/demo_client.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from a2a_client import ask_agent  # noqa: E402
from common import PORTS  # noqa: E402

QUESTIONS = [
    '我最近经常焦虑失眠，住在北京。可以找谁看诊？我的保单对心理咨询是怎么报销的？',
    '怎样科学地降低胆固醇？',
]


async def main():
    for q in QUESTIONS:
        print(f'\n{"=" * 60}\n用户: {q}\n{"=" * 60}')
        print(await ask_agent(PORTS['healthcare'], q))


if __name__ == '__main__':
    asyncio.run(main())
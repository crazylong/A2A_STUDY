"""第六篇《跨框架智能体接入》：医生名录 MCP 服务（FastMCP）。

ProviderAgent 的"内部工具层"：只暴露一个 list_doctors 工具。
由 provider_agent.py 通过 stdio 自动拉起，一般不需要单独运行。
"""

import json
from pathlib import Path

from fastmcp import FastMCP

mcp = FastMCP('DoctorDirectory')

DOCTORS = json.loads(
    (Path(__file__).parent / 'data' / 'doctors.json').read_text(
        encoding='utf-8'
    )
)


@mcp.tool
def list_doctors(city: str = '', specialty: str = '') -> str:
    """按城市和/或科室查询医生名录。

    Args:
        city: 城市名，如"北京"；留空表示不限城市。
        specialty: 科室名，如"心理科"；留空表示不限科室。
    """
    results = [
        d
        for d in DOCTORS
        if (not city or city in d['city'])
        and (not specialty or specialty in d['specialty'])
    ]
    if not results:
        return '未找到符合条件的医生。'
    return json.dumps(results, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    mcp.run()  # 默认 stdio 传输
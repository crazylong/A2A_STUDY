"""第四篇：复用的汇率换算业务逻辑（A2A 与 MCP 两条路线共用）。

这里刻意不依赖任何协议库，只有"解析 + 计算"：
- A2A 服务把它包装成 Task 生命周期（见 currency_agent.py）
- MCP 服务把它暴露成工具（见 currency_mcp_server.py）

汇率为本地静态演示数据，不联网，也不代表真实汇率。
"""

import json
import re
from pathlib import Path

RATES_FILE = Path(__file__).resolve().parent / 'currency_rates.json'

# 币种别名：中文/英文都认。注意不要用 "元" 这种会被 "美元/欧元" 包含的短词
ALIASES = {
    'USD': ('usd', '美元', '美金'),
    'CNY': ('cny', 'rmb', '人民币'),
    'EUR': ('eur', '欧元'),
    'JPY': ('jpy', '日元'),
    'GBP': ('gbp', '英镑'),
    'HKD': ('hkd', '港元', '港币'),
}


def load_rates() -> dict:
    return json.loads(RATES_FILE.read_text(encoding='utf-8'))


def parse_request(texts: list[str]) -> dict:
    """从多轮用户文本里抽金额和币种。

    金额取第一个数字；币种按出现位置排序，第一个当源币种、最后一个当目标币种。
    缺信息时返回 input_required —— 这正是 A2A 路线要展示的多轮追问。
    """
    text = ' '.join(texts)
    lowered = text.lower()

    amount_match = re.search(r'\d+(?:\.\d+)?', text)
    amount = float(amount_match.group()) if amount_match else None

    hits = []
    for code, aliases in ALIASES.items():
        for alias in aliases:
            pos = lowered.find(alias)
            if pos >= 0:
                hits.append((pos, code))
                break
    codes = [code for _, code in sorted(hits)]

    if amount is None:
        return {'status': 'input_required', 'message': '请告诉我换算金额，例如“100 美元换成人民币”。'}
    if not codes:
        return {'status': 'input_required', 'message': '请告诉我源币种和目标币种，例如“100 美元换成人民币”。'}
    if len(codes) == 1:
        return {
            'status': 'input_required',
            'message': f'收到 {amount:g} {codes[0]}，请告诉我要换成哪种货币（CNY / EUR / JPY / GBP / HKD）。',
        }

    from_currency, to_currency = codes[0], codes[-1]
    if from_currency == to_currency:
        return {'status': 'input_required', 'message': '源币种和目标币种相同，请换一个目标币种。'}
    return {
        'status': 'ok',
        'amount': amount,
        'from_currency': from_currency,
        'to_currency': to_currency,
    }


def convert(amount: float, from_currency: str, to_currency: str) -> dict:
    """纯计算：以 USD 为基准做交叉汇率换算。"""
    data = load_rates()
    rates = data['rates']
    source, target = from_currency.upper(), to_currency.upper()
    if source not in rates or target not in rates:
        return {
            'status': 'error',
            'message': f'不支持的币种：{source} → {target}，可选：{sorted(rates)}',
        }

    rate = rates[target] / rates[source]
    return {
        'status': 'ok',
        'amount': amount,
        'from_currency': source,
        'to_currency': target,
        'rate': round(rate, 4),
        'converted': round(amount * rate, 2),
        'as_of': data['as_of'],
        'note': data['note'],
    }
"""探测 LLM 模型是否可用。

用法：
    uv run python scripts/check_llm.py                 # 只探测 .env 里的 LLM_MODEL
    uv run python scripts/check_llm.py model-a model-b # 额外探测命令行给出的模型

只发一次 max_tokens=8 的最小请求，不打印 API Key，也不内置模型列表。
免费额度耗尽通常返回 403 insufficient_quota，换控制台里可用的模型即可。
"""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'article04_agents'))


async def probe(model: str) -> None:
    from common import llm_client, thinking_extra_body

    kwargs = {}
    extra_body = thinking_extra_body(model)
    if extra_body is not None:
        kwargs['extra_body'] = extra_body
    resp = await llm_client().chat.completions.create(
        model=model,
        messages=[{'role': 'user', 'content': '只回复 OK'}],
        max_tokens=8,
        **kwargs,
    )
    text = (resp.choices[0].message.content or '').strip()
    print(f'[可用] {model} → {text or "(空回复)"}')


async def main() -> int:
    # 导入 common 会先加载 .env，因此这里拿到的就是配置文件里的值
    from common import LLM_MODEL

    requested = [m for m in sys.argv[1:] if m.strip()]
    models = list(dict.fromkeys([LLM_MODEL, *requested]))
    print(f'当前 .env LLM_MODEL={LLM_MODEL}')
    if requested:
        print(f'本次额外探测：{", ".join(requested)}')

    available = []
    current_available = False
    for model in models:
        try:
            await probe(model)
            available.append(model)
            if model == LLM_MODEL:
                current_available = True
        except Exception as e:  # noqa: BLE001
            status = getattr(e, 'status_code', None)
            print(f'[不可用] {model} → {type(e).__name__}: {e}')
            if status == 403:
                print('  提示：403 多为免费额度耗尽或模型未开通')
            elif status == 404:
                print('  提示：404 多为模型名或地域/端点不匹配')
            elif status == 429:
                print('  提示：429 触发限流，降低并发或稍后重试')

    if not current_available:
        print('\n当前 .env 配置的 LLM_MODEL 不可用；请检查配置或更换模型。')
        return 1
    print(f'\n可用模型：{", ".join(available)}')
    print('把 .env 的 LLM_MODEL 设为其中一个后重启服务。')
    return 0


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
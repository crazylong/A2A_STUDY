"""第四篇补充案例：MCP Elicitation 汇率工具（FastMCP，stdio）。

运行方式由 MCP 客户端以子进程拉起：
    .venv/bin/python article03_compare/currency_mcp_elicitation_server.py
"""

from fastmcp import Context, FastMCP

from currency_core import convert, load_rates

mcp = FastMCP('currency-elicitation')


@mcp.tool
async def convert_currency_interactive(
    ctx: Context,
    amount: float,
    from_currency: str,
    to_currency: str = '',
) -> dict:
    """汇率换算；缺少目标币种时通过 Elicitation 请用户选择。"""
    if not to_currency:
        currencies = list(load_rates()['rates'])
        result = await ctx.elicit(
            f'收到 {amount:g} {from_currency.upper()}，请选择目标币种。',
            response_type=currencies,
            response_title='目标币种',
            response_description='可选币种：' + ' / '.join(currencies),
        )
        if result.action != 'accept':
            message = (
                '用户取消了换算。'
                if result.action == 'cancel'
                else '用户拒绝补充目标币种。'
            )
            return {'status': result.action, 'message': message}
        to_currency = result.data

    return convert(amount, from_currency, to_currency)


if __name__ == '__main__':
    mcp.run(transport='stdio', show_banner=False)

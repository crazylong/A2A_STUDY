"""篇二 2.10 路线 B：同一换算能力的 MCP 接法（FastMCP，stdio）。

运行方式由 MCP 客户端以子进程拉起：
    .venv/bin/python article02_hello/currency_mcp_server.py
"""

from fastmcp import FastMCP

from currency_core import convert

mcp = FastMCP('currency-tools')


@mcp.tool
def convert_currency(
    amount: float, from_currency: str, to_currency: str
) -> dict:
    """把 amount 从 from_currency 换算成 to_currency（USD 基准交叉汇率）。

    Args:
        amount: 待换算金额。
        from_currency: 源币种代码，如 USD、CNY。
        to_currency: 目标币种代码，如 CNY、EUR。
    """
    return convert(amount, from_currency, to_currency)


if __name__ == '__main__':
    mcp.run(transport='stdio', show_banner=False)
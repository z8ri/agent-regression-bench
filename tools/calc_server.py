"""calc MCP server：白名单字符 + ast 解析的安全四则运算，不用 eval。"""

import ast
import re
from decimal import Decimal, DivisionByZero, InvalidOperation

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("calc")

ALLOWED_CHARS = re.compile(r"^[0-9+\-*/(). ]+$")

_BIN_OPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
}
_UNARY_OPS = {
    ast.UAdd: lambda a: a,
    ast.USub: lambda a: -a,
}


class CalcError(Exception):
    pass


def _eval_node(node) -> Decimal:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return Decimal(str(node.value))
        raise CalcError("不支持的常量")
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        return _BIN_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval_node(node.operand))
    raise CalcError("不支持的表达式结构")


def _format_decimal(d: Decimal) -> str:
    text = format(d, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


@mcp.tool()
def calculate(expression: str) -> str:
    """计算一个只含数字和 + - * / ( ) 的四则运算表达式，不支持字母或函数调用。"""
    if not expression or not ALLOWED_CHARS.match(expression):
        return f"非法表达式，仅支持数字和 + - * / ( )：{expression}"
    try:
        tree = ast.parse(expression, mode="eval")
        result = _eval_node(tree)
    except (DivisionByZero, InvalidOperation):
        return "除数不能为零"
    except (CalcError, SyntaxError, ZeroDivisionError):
        return f"表达式无法解析：{expression}"
    return _format_decimal(result)


if __name__ == "__main__":
    mcp.run()

"""Tool: a safe arithmetic calculator using a restricted AST evaluator."""
import ast
import math
import operator as op
import re

from langchain_core.tools import tool

# Integer powers are exact and unbounded in Python, so "9 ** 9 ** 9" would
# pin a worker for a very long time. Cap the result size (~3,000 digits,
# below Python's 4,300-digit int->str limit) before computing.
_MAX_POW_BITS = 10_000


def _safe_pow(base, exponent):
    if (
        isinstance(base, int)
        and isinstance(exponent, int)
        and exponent > 0
        and abs(base) > 1
        and exponent * math.log2(abs(base)) > _MAX_POW_BITS
    ):
        raise ValueError("result too large (exponent out of range)")
    return op.pow(base, exponent)


# Whitelist of safe AST node types and operators.
_OPS = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.FloorDiv: op.floordiv,
    ast.Mod: op.mod,
    ast.Pow: _safe_pow,
    ast.USub: op.neg,
    ast.UAdd: op.pos,
}


def _eval(node):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("Only numeric constants allowed")
    if isinstance(node, ast.BinOp):
        return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp):
        return _OPS[type(node.op)](_eval(node.operand))
    raise ValueError(f"Unsupported expression element: {type(node).__name__}")


def _normalize(expression: str) -> str:
    """Strip thousands-separator commas and common LLM-isms.

    Handles inputs like:
      "87,500 * 24"           -> "87500 * 24"
      "1,000,000 / 4"         -> "1000000 / 4"
      "$87,500 * 24"          -> "87500 * 24"
      "x ** 2 where x=3"      -> handled by AST rejection (good)

    A digit-comma-digit pattern is treated as a thousands separator. We do
    NOT strip commas between non-digits, so legitimate tuples (which we
    want to reject anyway) still fail loudly.
    """
    s = expression.strip()
    # Remove currency symbols and stray whitespace inside numbers.
    s = s.replace("$", "").replace("\u00a3", "").replace("\u20ac", "")
    # Strip thousands separators: comma between digits.
    s = re.sub(r"(?<=\d),(?=\d)", "", s)
    return s


@tool
def calculator(expression: str) -> str:
    """Evaluate a basic arithmetic expression safely.

    Supports + - * / // % ** and parentheses. Numbers may include thousands
    separators (commas) and currency symbols, which are stripped before
    evaluation. Does NOT support variables, function calls, or imports.
    Use this for any math the user asks about.

    Args:
        expression: An arithmetic expression, e.g. "23 * (45 + 7) / 2"
            or "87,500 * 24" or "$1,000 + $250".

    Returns:
        The numeric result as a string, or an error message.
    """
    try:
        normalized = _normalize(expression)
        tree = ast.parse(normalized, mode="eval")
        result = _eval(tree.body)
        return str(result)
    except ZeroDivisionError:
        return "Error: division by zero"
    except Exception as e:
        return f"Error: {e}"
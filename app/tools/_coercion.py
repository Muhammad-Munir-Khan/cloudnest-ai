"""Defensive numeric coercion for LLM-provided tool arguments.

Small open-source models (gpt-oss-20B, Llama 3.1 8B) sometimes serialize
numeric arguments in unexpected ways:
  - As quoted strings: "2100000" instead of 2100000
  - With thousands separators: "2,100,000"
  - As math expressions: "0.15 * 240000"

The first two were handled per-tool. The third hit currency_converter on
2026-05-16 with amount="0.15 * 240000" and broke the demo.

This module centralizes coercion so every tool with a numeric parameter
can defend against the same class of input.
"""
import ast
import operator

_ALLOWED_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


class CoercionError(ValueError):
    """Raised when a value can't be coerced to a number safely."""


def _eval_math_node(node: ast.AST) -> float:
    """Recursively evaluate a whitelisted AST node. Raise on anything weird."""
    if isinstance(node, ast.Expression):
        return _eval_math_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise CoercionError(f"non-numeric constant: {node.value!r}")
    if isinstance(node, ast.Num):  # py<3.8 fallback
        return float(node.n)
    if isinstance(node, ast.BinOp):
        op = _ALLOWED_OPS.get(type(node.op))
        if op is None:
            raise CoercionError(f"operator {type(node.op).__name__} not allowed")
        return op(_eval_math_node(node.left), _eval_math_node(node.right))
    if isinstance(node, ast.UnaryOp):
        op = _ALLOWED_OPS.get(type(node.op))
        if op is None:
            raise CoercionError(f"unary {type(node.op).__name__} not allowed")
        return op(_eval_math_node(node.operand))
    raise CoercionError(f"node type {type(node).__name__} not allowed")


def coerce_numeric(value: float | int | str) -> float:
    """Coerce an LLM-provided value to a float, defensively.

    Accepts:
      - int or float: returned as float
      - plain numeric string: "36000", "36,000", "1_000"
      - math expression string: "0.15 * 240000", "(5 + 3) / 4"

    Raises CoercionError on:
      - non-numeric strings ("hello")
      - expressions with function calls, names, or other risky AST nodes
      - non-numeric / non-string types
    """
    if isinstance(value, (int, float)):
        return float(value)

    if not isinstance(value, str):
        raise CoercionError(
            f"expected number or string, got {type(value).__name__}"
        )

    cleaned = value.replace(",", "").replace("_", "").strip()
    if not cleaned:
        raise CoercionError("empty value")

    # Try the simple case first - just a number.
    try:
        return float(cleaned)
    except ValueError:
        pass

    # Fall back to safe AST evaluation for expressions like "0.15 * 240000".
    try:
        tree = ast.parse(cleaned, mode="eval")
    except SyntaxError as e:
        raise CoercionError(f"not a valid number or expression: {value!r}") from e

    try:
        result = _eval_math_node(tree)
    except CoercionError:
        raise
    except (TypeError, ZeroDivisionError, OverflowError) as e:
        raise CoercionError(f"math error in {value!r}: {e}") from e

    return float(result)

"""compute.py — safe arithmetic for the model.

Companion to `aggregate.py`. Aggregation answers "how many / how much across the
fleet"; this handles the small derived arithmetic that follows it: service
credits as a percentage of a fee, cents to currency, availability as a
percentage, downtime in hours, days between two counts.

Implemented as an AST walk over a whitelist of node types, **not** `eval()`. An
expression containing a name, attribute access, a call to anything outside
ALLOWED, an import, or a subscript is rejected before evaluation — so a
malformed or adversarial expression can only ever produce an error string.

Deliberately small. It does arithmetic and nothing else; anything needing a
record goes through the real tools.
"""
from __future__ import annotations

import ast
import math
import operator

MAX_LENGTH = 200
# Guards expressions like 9**9**9 that would otherwise hang the process.
MAX_EXPONENT = 64

BINARY = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}

ALLOWED = {
    "round": round,
    "abs": abs,
    "min": min,
    "max": max,
    "sum": sum,
    "floor": math.floor,
    "ceil": math.ceil,
}


class Unsafe(ValueError):
    """Raised when an expression contains anything outside the whitelist."""


def _walk(node: ast.AST):
    if isinstance(node, ast.Expression):
        return _walk(node.body)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        raise Unsafe(f"only numeric literals are allowed, got {node.value!r}")

    if isinstance(node, ast.BinOp):
        op = BINARY.get(type(node.op))
        if op is None:
            raise Unsafe(f"operator {type(node.op).__name__} is not allowed")
        left, right = _walk(node.left), _walk(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
            raise Unsafe(f"exponent {right} exceeds the limit of {MAX_EXPONENT}")
        if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)) and right == 0:
            raise Unsafe("division by zero")
        return op(left, right)

    if isinstance(node, ast.UnaryOp):
        op = UNARY.get(type(node.op))
        if op is None:
            raise Unsafe(f"unary {type(node.op).__name__} is not allowed")
        return op(_walk(node.operand))

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in ALLOWED:
            name = getattr(node.func, "id", type(node.func).__name__)
            raise Unsafe(f"function {name!r} is not allowed")
        if node.keywords:
            raise Unsafe("keyword arguments are not allowed")
        return ALLOWED[node.func.id](*[_walk(a) for a in node.args])

    if isinstance(node, (ast.List, ast.Tuple)):
        return [_walk(e) for e in node.elts]      # so sum([...]) / max([...]) work

    raise Unsafe(f"{type(node).__name__} is not allowed in an expression")


def compute(expression: str) -> dict:
    """Evaluate a pure-arithmetic expression exactly.

    Args:
        expression: e.g. "317500 / 100", "round(0.9931 * 100, 2)",
                    "2400000 * 0.05 / 12", "386 / 60".
                    Numbers and + - * / // % ** only, plus
                    round/abs/min/max/sum/floor/ceil. No variables, no names —
                    substitute the actual numbers first.

    Returns:
        {"expression": ..., "result": <number>} or {"error": "..."}.
        Never guesses: an invalid expression is an error, not a number.
    """
    if not isinstance(expression, str) or not expression.strip():
        return {"error": "expression must be a non-empty string"}
    if len(expression) > MAX_LENGTH:
        return {"error": f"expression exceeds {MAX_LENGTH} characters"}

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as e:
        return {"error": f"could not parse expression: {e.msg}"}

    try:
        result = _walk(tree)
    except Unsafe as e:
        return {"error": str(e)}
    except (ZeroDivisionError, OverflowError, TypeError, ValueError) as e:
        return {"error": f"{type(e).__name__}: {e}"}

    if isinstance(result, float):
        # Kill float noise like 6.1000000000000005 without overstating precision.
        result = round(result, 10)
    return {"expression": expression, "result": result}

"""The safe arithmetic tool.

Two things are asserted: that the maths is right, and that the sandbox holds.
The second matters because the expression string is written by a model and could
in principle be anything.
"""
from __future__ import annotations

import pytest

from tools.compute import compute


@pytest.mark.parametrize("expression,expected", [
    ("2 + 2", 4),
    ("317500 / 100", 3175.0),                    # cents -> currency
    ("round(0.9931 * 100, 2)", 99.31),           # fraction -> percentage
    ("2400000 * 0.05 / 12", 10000.0),            # 5% credit on a monthly share
    ("386 / 60", 6.4333333333),                  # downtime minutes -> hours
    ("round(386 / 60, 1)", 6.4),
    ("2400000 * 0.15", 360000.0),                # 15% spares deposit
    ("max(8, 4)", 8),
    ("min(0.9931, 0.995)", 0.9931),
    ("abs(-42)", 42),
    ("sum([120000, 85000, 8500])", 213500),
    ("(90 - 76)", 14),                           # days left in burn-in
    ("-5 + 3", -2),
    ("10 // 3", 3),
    ("10 % 3", 1),
    ("2 ** 10", 1024),
    ("ceil(6.43)", 7),
    ("floor(6.43)", 6),
])
def test_arithmetic_is_exact(expression, expected):
    assert compute(expression)["result"] == pytest.approx(expected)


def test_float_noise_is_cleaned_up():
    # 0.1 + 0.2 is 0.30000000000000004 in raw float arithmetic.
    assert compute("0.1 + 0.2")["result"] == 0.3


def test_result_echoes_the_expression():
    assert compute("2 + 2")["expression"] == "2 + 2"


# ---------------------------------------------------------------------------
# the sandbox — each of these must be an error, never a value
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("expression", [
    "__import__('os').system('echo pwned')",
    "open('/etc/passwd').read()",
    "print('hi')",
    "[].__class__",
    "().__class__.__bases__",
    "exec('1')",
    "lambda: 1",
    "x + 1",                      # bare name
    "'a' * 10",                   # string literal
    "True + 1",                   # bool literal
    "{'a': 1}",
    "9 ** 9 ** 9",                # exponent bomb
    "1 / 0",
    "10 // 0",
    "5 % 0",
    "2 +",                        # syntax error
    "",
    "   ",
])
def test_unsafe_or_invalid_input_is_rejected(expression):
    result = compute(expression)
    assert "error" in result, f"{expression!r} should have been rejected"
    assert "result" not in result


def test_overlong_expression_is_rejected():
    assert "error" in compute("1+" * 200 + "1")


def test_non_string_input_is_rejected():
    assert "error" in compute(None)      # type: ignore[arg-type]
    assert "error" in compute(42)        # type: ignore[arg-type]

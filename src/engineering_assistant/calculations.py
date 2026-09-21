"""Restricted arithmetic checks. Expressions never execute Python code."""
from __future__ import annotations

import ast
import math
import operator

from .units import BUILTIN_CONSTANTS, describe, expression_dimension, parse_unit, power_notation_hint, same_dimension, shadowed_constants

OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
       ast.Div: operator.truediv, ast.Pow: operator.pow}
FUNCTIONS = {"sqrt": math.sqrt, "exp": math.exp, "log": math.log, "abs": abs}


def evaluate(expression: str, variables: dict) -> float:
    if not isinstance(expression, str) or len(expression) > 2000:
        raise ValueError("Expression must be a string of at most 2000 characters.")
    tree = ast.parse(expression, mode="eval")
    if sum(1 for _ in ast.walk(tree)) > 150:
        raise ValueError("Expression is too complex.")

    def finite(value):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("Calculations require finite numeric values.")
        return float(value)

    variables = {name: finite(value) for name, value in variables.items()}

    def visit(node):
        if isinstance(node, ast.Constant):
            return finite(node.value)
        if isinstance(node, ast.Name):
            if node.id not in variables:
                # Reached only when nothing of this name was supplied: a
                # supplied value is already in `variables` and wins there.
                if node.id in BUILTIN_CONSTANTS:
                    return BUILTIN_CONSTANTS[node.id]
                raise ValueError(f"Missing variable: {node.id}")
            return variables[node.id]
        if isinstance(node, ast.BinOp) and type(node.op) in OPS:
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 100:
                raise ValueError("Exponent exceeds the supported bound.")
            return finite(OPS[type(node.op)](left, right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            return visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS and len(node.args) == 1 and not node.keywords:
            return finite(FUNCTIONS[node.func.id](visit(node.args[0])))
        raise ValueError(
            "Unsupported expression; only numeric arithmetic and sqrt/exp/log/abs are allowed."
            + power_notation_hint(expression)
        )

    return visit(tree.body)


def _mode(variables) -> str:
    """Decide whether dimensions can be checked, and refuse a half-declared check.

    Dimensional checking runs only when every variable carries a unit.  With
    some declared and some bare, a check would have to invent a dimension or
    quietly skip the ones it lacks, and either way report a pass that means
    less than it says.
    """
    if not isinstance(variables, dict) or not variables:
        return "arithmetic"
    united = [isinstance(value, dict) for value in variables.values()]
    if all(united):
        return "dimensional"
    if any(united):
        raise ValueError(
            "Dimensional checking needs a unit on every variable; "
            "give each one a value and a unit, or give none of them a unit."
        )
    return "arithmetic"


def _evaluate_dimensional(check: dict, variables: dict) -> float:
    """Evaluate in SI and return the result in the declared unit.

    Each recorded value is converted from its own unit before any arithmetic,
    so a reading taken in degF is checked as degF.  That is what catches a
    value the student converted wrongly by hand: the check does the conversion
    itself instead of trusting the converted number.
    """
    si, dimensions = {}, {}
    for name, spec in variables.items():
        if "value" not in spec or "unit" not in spec:
            raise ValueError(f"Variable {name} needs both a value and a unit.")
        value = spec["value"]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Variable {name} must have a numeric value.")
        unit = parse_unit(spec["unit"])
        si[name] = unit.to_si(float(value))
        dimensions[name] = unit.dimension
    declared = parse_unit(check.get("unit"))
    found = expression_dimension(check["expression"], dimensions)
    if not same_dimension(found, declared.dimension):
        raise ValueError(
            f"The result has dimension {describe(found)}, but the declared unit "
            f"{check['unit']!r} has dimension {describe(declared.dimension)}."
        )
    return declared.from_si(evaluate(check["expression"], si))


def check_calculation(check: dict) -> dict:
    result = {"id": check.get("id"), "kind": "arithmetic", "passed": False}
    try:
        variables = check.get("variables", {})
        mode = _mode(variables)
        # Say which check ran.  A pass in arithmetic mode says nothing about
        # units, and a reader must be able to tell that from the result alone.
        result["mode"] = mode
        # A supplied constant wins, and says so: see shadowed_constants.
        shadows = shadowed_constants(variables)
        if shadows:
            result["shadowed_constants"] = shadows
        if mode == "dimensional":
            actual = _evaluate_dimensional(check, variables)
        else:
            actual = evaluate(check["expression"], variables)
        expected = check["expected"]
        tolerance = check.get("tolerance", 1e-8)
        if isinstance(expected, bool) or not isinstance(expected, (int, float)) or not math.isfinite(expected):
            raise ValueError("Expected result must be finite.")
        if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or not math.isfinite(tolerance) or tolerance < 0:
            raise ValueError("Tolerance must be finite and nonnegative.")
        if not isinstance(check.get("unit"), str) or not check["unit"].strip():
            raise ValueError("Specify a result unit (or 'dimensionless').")
        result.update(actual=actual, expected=expected, tolerance=tolerance,
                      unit=check["unit"], passed=abs(actual - expected) <= tolerance)
    except (ValueError, KeyError, TypeError, SyntaxError, ZeroDivisionError, OverflowError) as exc:
        result["error"] = str(exc)
    return result

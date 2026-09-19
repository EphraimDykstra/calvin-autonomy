"""Units and dimensions for calculation checks.

Every quantity is converted to SI at substitution, so arithmetic runs in
absolute units and a temperature offset is applied exactly once.  That is what
makes a Fahrenheit reading carried into a Kelvin formula detectable: the check
converts the recorded value itself instead of trusting the number the student
wrote down.

The registry holds the units that actually appear in the course material, not
a general engineering list.  An unrecognised unit refuses rather than guesses,
because a guessed unit is how a wrong conversion comes to look correct.
"""

from __future__ import annotations

import ast
import math
import re
from dataclasses import dataclass


class UnitError(ValueError):
    """A unit string that cannot be read, or cannot be used where it appears."""


# Base dimensions: mass, length, time, temperature, current, amount.
_BASE_SYMBOLS = ("kg", "m", "s", "K", "A", "mol")
DIMENSIONLESS = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


def _d(M=0, L=0, T=0, Th=0, I=0, N=0):
    return (float(M), float(L), float(T), float(Th), float(I), float(N))


_MASS = _d(M=1)
_LENGTH = _d(L=1)
_TIME = _d(T=1)
_TEMP = _d(Th=1)
_FORCE = _d(M=1, L=1, T=-2)
_ENERGY = _d(M=1, L=2, T=-2)
_POWER = _d(M=1, L=2, T=-3)
_PRESSURE = _d(M=1, L=-1, T=-2)
_VOLUME = _d(L=3)
_VOLTAGE = _d(M=1, L=2, T=-3, I=-1)
_RESISTANCE = _d(M=1, L=2, T=-3, I=-2)

_PSI = 6894.757293168

# symbol -> (factor to SI, dimension, affine offset to SI or None)
#
# An affine unit has an offset as well as a scale.  Celsius and Fahrenheit are
# the only ones here, and they may only stand alone; see _refuse_affine.
_REGISTRY: dict[str, tuple[float, tuple, float | None]] = {
    "dimensionless": (1.0, DIMENSIONLESS, None),
    "percent": (0.01, DIMENSIONLESS, None),
    "%": (0.01, DIMENSIONLESS, None),
    "rad": (1.0, DIMENSIONLESS, None),
    "rev": (2 * math.pi, DIMENSIONLESS, None),
    # mass
    "kg": (1.0, _MASS, None),
    "g": (1e-3, _MASS, None),
    "lbm": (0.45359237, _MASS, None),
    # length
    "m": (1.0, _LENGTH, None),
    "cm": (1e-2, _LENGTH, None),
    "mm": (1e-3, _LENGTH, None),
    "km": (1e3, _LENGTH, None),
    # US customary length, used throughout the mechanics and design courses.
    "in": (0.0254, _LENGTH, None),
    "ft": (0.3048, _LENGTH, None),
    # time
    "s": (1.0, _TIME, None),
    "min": (60.0, _TIME, None),
    "h": (3600.0, _TIME, None),
    "hr": (3600.0, _TIME, None),
    # temperature: absolute scales
    "K": (1.0, _TEMP, None),
    "R": (5.0 / 9.0, _TEMP, None),
    # temperature: affine scales.  "C" means Celsius, not the coulomb: EES
    # writes it that way and it appears 159 times across the course files,
    # never once as a charge.
    "degC": (1.0, _TEMP, 273.15),
    "C": (1.0, _TEMP, 273.15),
    "degF": (5.0 / 9.0, _TEMP, 459.67 * 5.0 / 9.0),
    "F": (5.0 / 9.0, _TEMP, 459.67 * 5.0 / 9.0),
    # temperature differences: the same scale with no offset
    "deltaC": (1.0, _TEMP, None),
    "deltaF": (5.0 / 9.0, _TEMP, None),
    # current and amount
    "A": (1.0, _d(I=1), None),
    "mol": (1.0, _d(N=1), None),
    "kmol": (1e3, _d(N=1), None),
    # force
    "N": (1.0, _FORCE, None),
    "kN": (1e3, _FORCE, None),
    # Pound-force and pound-mass are registered separately and a bare "lb" is
    # not registered at all: in engineering it names either, and a guessed
    # reading is exactly how a wrong conversion comes to look right.
    "lbf": (4.4482216152605, _FORCE, None),
    "kip": (4448.2216152605, _FORCE, None),
    # energy
    "J": (1.0, _ENERGY, None),
    "kJ": (1e3, _ENERGY, None),
    "MJ": (1e6, _ENERGY, None),
    # power
    "W": (1.0, _POWER, None),
    "kW": (1e3, _POWER, None),
    "MW": (1e6, _POWER, None),
    # pressure
    "Pa": (1.0, _PRESSURE, None),
    "kPa": (1e3, _PRESSURE, None),
    "MPa": (1e6, _PRESSURE, None),
    "bar": (1e5, _PRESSURE, None),
    "mbar": (1e2, _PRESSURE, None),
    "psi": (_PSI, _PRESSURE, None),
    "psia": (_PSI, _PRESSURE, None),
    "mmHg": (133.322387415, _PRESSURE, None),
    "mmH2O": (9.80665, _PRESSURE, None),
    "GPa": (1e9, _PRESSURE, None),
    "ksi": (1e3 * _PSI, _PRESSURE, None),
    # volume
    "L": (1e-3, _VOLUME, None),
    "mL": (1e-6, _VOLUME, None),
    # electrical
    "V": (1.0, _VOLTAGE, None),
    "ohm": (1.0, _RESISTANCE, None),
    "ohms": (1.0, _RESISTANCE, None),
    # frequency and rotation
    "Hz": (1.0, _d(T=-1), None),
    "RPM": (2 * math.pi / 60.0, _d(T=-1), None),
}

_TOKEN = r"[A-Za-z%][A-Za-z0-9_%]*(?:\^-?\d+(?:\.\d+)?)?"
_SIDE = re.compile(rf"{_TOKEN}(?:[-*]{_TOKEN})*")
_FACTOR = re.compile(r"([A-Za-z%][A-Za-z0-9_%]*)(?:\^(-?\d+(?:\.\d+)?))?")


@dataclass(frozen=True)
class Unit:
    """A parsed unit: its scale to SI, its dimension, and any affine offset."""

    text: str
    factor: float
    dimension: tuple
    offset: float | None = None

    def to_si(self, value: float) -> float:
        return value * self.factor + (self.offset or 0.0)

    def from_si(self, value: float) -> float:
        return (value - (self.offset or 0.0)) / self.factor


def _factors(side: str, where: str) -> list[tuple[str, float]]:
    side = side.strip()
    if side in ("", "1"):
        return []
    if not _SIDE.fullmatch(side):
        raise UnitError(f"Cannot read unit {where!r}.")
    return [(symbol, float(power) if power else 1.0) for symbol, power in _FACTOR.findall(side)]


def _refuse_affine(text: str, factors: list[tuple[str, float, bool]]) -> None:
    """Refuse an offset scale anywhere it would be multiplied.

    Multiplying by Celsius multiplies by an offset, which silently produces a
    wrong number that looks entirely plausible.  A specific heat written
    kJ/kg-degC means per degree of difference, so the author meant deltaC.
    """
    affine = [symbol for symbol, _, _ in factors if _REGISTRY[symbol][2] is not None]
    if not affine:
        return
    standalone = len(factors) == 1 and factors[0][1] == 1.0 and not factors[0][2]
    if not standalone:
        symbol = affine[0]
        delta = "deltaF" if symbol in ("degF", "F") else "deltaC"
        raise UnitError(
            f"{text!r} uses {symbol}, a scale with an offset, inside a compound unit. "
            f"A temperature inside a compound is a difference: write {delta}, or K."
        )


def parse_unit(text: str) -> Unit:
    """Parse a unit such as ``kJ/kg-K`` or ``kg^0.5-m^1.5/s``.

    EES notation is supported: a hyphen or asterisk multiplies, and everything
    after the first slash is the denominator, so ``kJ/kg-K`` is kJ/(kg*K).
    """
    if not isinstance(text, str) or not text.strip():
        raise UnitError("A unit is required.")
    text = text.strip()
    numerator, _, denominator = text.partition("/")
    parts = [(s, p, False) for s, p in _factors(numerator, text)]
    parts += [(s, p, True) for s, p in _factors(denominator.replace("/", "-"), text)]
    if not parts and text not in ("1", "dimensionless"):
        raise UnitError(f"Cannot read unit {text!r}.")

    for symbol, _, _ in parts:
        if symbol not in _REGISTRY:
            raise UnitError(
                f"Unrecognised unit {symbol!r} in {text!r}. It is refused rather than "
                "guessed, because a guessed unit is how a wrong conversion looks right."
            )
    _refuse_affine(text, parts)

    if len(parts) == 1 and not parts[0][2] and parts[0][1] == 1.0:
        factor, dimension, offset = _REGISTRY[parts[0][0]]
        return Unit(text, factor, dimension, offset)

    factor = 1.0
    dimension = list(DIMENSIONLESS)
    for symbol, power, below in parts:
        scale, dims, _ = _REGISTRY[symbol]
        sign = -1.0 if below else 1.0
        factor *= scale ** (sign * power)
        for i, d in enumerate(dims):
            dimension[i] += sign * power * d
    return Unit(text, factor, tuple(dimension))


def dimension_of(text: str) -> tuple:
    return parse_unit(text).dimension


def same_dimension(a: tuple, b: tuple) -> bool:
    return all(math.isclose(x, y, abs_tol=1e-9) for x, y in zip(a, b))


def describe(dimension: tuple) -> str:
    """Render a dimension in SI base units, e.g. ``kg m^2 s^-3``."""
    parts = []
    for symbol, power in zip(_BASE_SYMBOLS, dimension):
        if math.isclose(power, 0.0, abs_tol=1e-9):
            continue
        if math.isclose(power, 1.0):
            parts.append(symbol)
        else:
            text = f"{power:g}"
            parts.append(f"{symbol}^{text}")
    return " ".join(parts) or "dimensionless"


def convert(value: float, source: str, target: str) -> float:
    """Convert ``value`` between two units of the same dimension."""
    a, b = parse_unit(source), parse_unit(target)
    # A difference has no absolute value, so it cannot become a reading on an
    # offset scale, nor a reading become a difference.  Converting 10 deltaF
    # to degF would return a plausible absolute temperature that means nothing.
    deltas, affine = {"deltaC", "deltaF"}, (a.offset is not None, b.offset is not None)
    if (a.text in deltas and affine[1]) or (b.text in deltas and affine[0]):
        raise UnitError(
            f"Cannot convert {source} to {target}: one is a temperature difference and the "
            "other a reading on an offset scale. Use deltaC, deltaF or K for a difference."
        )
    if not same_dimension(a.dimension, b.dimension):
        raise UnitError(
            f"Cannot convert {source} ({describe(a.dimension)}) "
            f"to {target} ({describe(b.dimension)}): different dimensions."
        )
    return b.from_si(a.to_si(value))


def _literal(node: ast.AST) -> float | None:
    """Return a numeric literal, including a negated one, else None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        inner = _literal(node.operand)
        if inner is not None:
            return -inner if isinstance(node.op, ast.USub) else inner
    return None


def expression_dimension(expression: str, dimensions: dict[str, tuple]) -> tuple:
    """Return the dimension of ``expression``, or raise on an inconsistent one."""
    tree = ast.parse(expression, mode="eval")

    def visit(node: ast.AST) -> tuple:
        if isinstance(node, ast.Constant):
            return DIMENSIONLESS
        if isinstance(node, ast.Name):
            if node.id not in dimensions:
                raise UnitError(f"Missing variable: {node.id}")
            return dimensions[node.id]
        if isinstance(node, ast.UnaryOp):
            return visit(node.operand)
        if isinstance(node, ast.BinOp):
            left = visit(node.left)
            if isinstance(node.op, ast.Pow):
                power = _literal(node.right)
                if power is None:
                    if same_dimension(left, DIMENSIONLESS) and same_dimension(visit(node.right), DIMENSIONLESS):
                        return DIMENSIONLESS
                    raise UnitError("An exponent on a dimensioned quantity must be a number.")
                return tuple(d * power for d in left)
            right = visit(node.right)
            if isinstance(node.op, (ast.Add, ast.Sub)):
                if not same_dimension(left, right):
                    raise UnitError(
                        f"Cannot add or subtract quantities of different dimension: "
                        f"{describe(left)} and {describe(right)}."
                    )
                return left
            if isinstance(node.op, ast.Mult):
                return tuple(a + b for a, b in zip(left, right))
            if isinstance(node.op, ast.Div):
                return tuple(a - b for a, b in zip(left, right))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and len(node.args) == 1:
            argument = visit(node.args[0])
            if node.func.id == "sqrt":
                return tuple(d * 0.5 for d in argument)
            if node.func.id == "abs":
                return argument
            if node.func.id in ("exp", "log"):
                if not same_dimension(argument, DIMENSIONLESS):
                    raise UnitError(
                        f"{node.func.id}() needs a dimensionless argument, "
                        f"not {describe(argument)}."
                    )
                return DIMENSIONLESS
        raise UnitError("Unsupported expression for dimensional checking.")

    return visit(tree.body)


__all__ = [
    "DIMENSIONLESS",
    "Unit",
    "UnitError",
    "convert",
    "describe",
    "dimension_of",
    "expression_dimension",
    "parse_unit",
    "same_dimension",
]

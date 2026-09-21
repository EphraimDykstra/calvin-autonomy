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

# Names an expression may use without being given them.  A review of any
# geometry or rotation problem needs pi, and failing with "Missing variable:
# pi" before it reaches the student's actual mistake is a check that gets in
# the way of the thing it exists to do.
#
# The list is one entry long on purpose, because a built-in is not free: it
# turns a loud "Missing variable" into a silent default, so it is only worth
# it for a name nobody writes meaning something else.  "pi" qualifies.  "e"
# does not: it is ordinary notation for eccentricity, a void ratio or an error
# term, so a host that meant its own variable and forgot to supply it would
# silently compute with 2.718, and exp() already covers the exponential.  "g"
# is impossible: it is already the symbol for the gram, and a dimensioned
# gravity that varies by unit system is exactly the kind of prior this project
# does not hold on a student's behalf.
BUILTIN_CONSTANTS: dict[str, float] = {"pi": math.pi}


def power_notation_hint(expression) -> str:
    """Name the caret mistake, because the notation really is inconsistent.

    A unit string writes a power with a caret, "in^2", and an expression
    writes one with two stars, "d**2".  A host that has just typed the first
    naturally types the second the same way, and Python reads that caret as a
    bitwise operator on a quantity that is not an integer, so the check
    refuses with a message about unsupported expressions that says nothing
    about powers.

    The caret is never reinterpreted as a power.  Silently changing what an
    operator means is how a wrong answer gets certified; this only explains
    the refusal.
    """
    if not isinstance(expression, str) or "^" not in expression:
        return ""
    return (
        " A power in an expression is written '**', not '^', which reads as a bitwise "
        f"operator here: write {expression.replace('^', '**')!r}. Unit strings are the "
        "other way round and do use '^', as in 'in^2'."
    )


def shadowed_constants(variables) -> list[dict]:
    """Report a supplied value that stands in for a built-in.

    A step may legitimately supply its own pi: a course can say to use 3.14,
    and the check must then use 3.14, because checking a student against a
    number they did not use is not checking their work.  So the supplied value
    wins.  But it wins visibly.  Preferring it in silence would hide the other
    case, where the value is 3 because somebody mistyped it, and the check
    would confirm an answer computed from a wrong constant.

    There is no materiality threshold here on purpose.  Any difference is
    reported and the reader judges it; a cutoff would be an invented number
    the check would then be quietly enforcing.  An exactly equal value reports
    nothing, so a step that passes math.pi is not noise.
    """
    if not isinstance(variables, dict):
        return []
    shadows = []
    for name, builtin in BUILTIN_CONSTANTS.items():
        if name not in variables:
            continue
        supplied = variables[name]
        # Both shapes: a bare number in arithmetic mode, {value, unit} where
        # units are declared.
        if isinstance(supplied, dict):
            supplied = supplied.get("value")
        if isinstance(supplied, bool) or not isinstance(supplied, (int, float)):
            continue
        if float(supplied) == builtin:
            continue
        shadows.append({
            "name": name,
            "supplied": float(supplied),
            "builtin": builtin,
            "relative_difference": abs(float(supplied) - builtin) / abs(builtin),
        })
    return shadows


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
_CAPACITANCE = _d(M=-1, L=-2, T=4, I=2)
_INDUCTANCE = _d(M=1, L=2, T=-2, I=-2)
_CHARGE = _d(T=1, I=1)

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
    # A phasor angle is written in degrees throughout the circuits course.
    # "deg" is the angle; "degC" and "degF" are temperatures, and the three
    # are separate symbols so neither can be read as the other.
    "deg": (math.pi / 180.0, DIMENSIONLESS, None),
    # "krad/s" is how the circuits course writes a corner frequency.
    "krad": (1e3, DIMENSIONLESS, None),
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
    # "us" is the ASCII spelling of the microsecond, the way "deltaC" spells a
    # Celsius difference: course files are plain text and do not carry the
    # micro sign reliably.
    "us": (1e-6, _TIME, None),
    "ms": (1e-3, _TIME, None),
    # The circuits course writes an angular frequency as "200 rad/sec".
    "sec": (1.0, _TIME, None),
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
    "mA": (1e-3, _d(I=1), None),
    "uA": (1e-6, _d(I=1), None),
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
    "mW": (1e-3, _POWER, None),
    "uW": (1e-6, _POWER, None),
    "kW": (1e3, _POWER, None),
    "MW": (1e6, _POWER, None),
    # Apparent power (VA) and reactive power (var) carry the watt's dimension,
    # so the engine reads an apparent power given in W as dimensionally fine.
    # It is: the three differ by which part of the complex power they name,
    # not by dimension, and no linear registry can tell them apart.  The
    # circuits pack carries that as a method pitfall, where a host can catch
    # it; registering them at least lets a student write what the course
    # writes instead of being refused.
    "VA": (1.0, _POWER, None),
    "var": (1.0, _POWER, None),
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
    "mV": (1e-3, _VOLTAGE, None),
    "kV": (1e3, _VOLTAGE, None),
    "ohm": (1.0, _RESISTANCE, None),
    "ohms": (1.0, _RESISTANCE, None),
    "kohm": (1e3, _RESISTANCE, None),
    "kohms": (1e3, _RESISTANCE, None),
    # Capacitance and inductance.  The farad and the coulomb are spelled out
    # because their symbols are taken: "F" is Fahrenheit and "C" is Celsius
    # here, decided by the thermodynamics files where they appear constantly
    # and never as an electrical unit.  Changing either would break those
    # courses, so the circuits course gets the prefixed forms it actually
    # writes, plus a spelled-out name for the base unit.
    "farad": (1.0, _CAPACITANCE, None),
    "mF": (1e-3, _CAPACITANCE, None),
    "uF": (1e-6, _CAPACITANCE, None),
    "nF": (1e-9, _CAPACITANCE, None),
    "pF": (1e-12, _CAPACITANCE, None),
    "fF": (1e-15, _CAPACITANCE, None),
    "H": (1.0, _INDUCTANCE, None),
    "mH": (1e-3, _INDUCTANCE, None),
    "coulomb": (1.0, _CHARGE, None),
    "uC": (1e-6, _CHARGE, None),
    # frequency and rotation
    "Hz": (1.0, _d(T=-1), None),
    "kHz": (1e3, _d(T=-1), None),
    "MHz": (1e6, _d(T=-1), None),
    "RPM": (2 * math.pi / 60.0, _d(T=-1), None),
    "rpm": (2 * math.pi / 60.0, _d(T=-1), None),
}

# The electrical symbols the registry deliberately does not hold, and what a
# student who typed one meant.  Consulted only when a conversion fails, so a
# thermodynamics file that means Fahrenheit is never second-guessed.
_ELECTRICAL_SPELLING: dict[str, tuple[tuple, str]] = {
    "F": (_CAPACITANCE, "farads are written uF, nF, pF, mF or 'farad' here, because 'F' is Fahrenheit"),
    "C": (_CHARGE, "coulombs are written uC or 'coulomb' here, because 'C' is Celsius"),
}

# The decibel is deliberately absent, and this note is here so it is not added
# as an oversight.  dB is logarithmic, and every unit here is (factor,
# dimension, offset) read linearly as value*factor + offset, so registering it
# would make wrong conversions look right: 20 dB would convert to 20 V/V
# rather than 10, and 6 dB to 600 percent.  Those two could be stopped with a
# guard in `convert`, like the one that refuses a temperature difference on an
# offset scale.  The one that cannot be stopped here is arithmetic: a review
# takes an input's unit standalone and adds it linearly, so "3 dB + 3 dB = 6
# dB" would be checked as correct, and the dimension comparison that would
# have to catch it lives in review.py and calculations.py, not in this file.
# Refusing dB is therefore the honest answer until it can be given a dimension
# nothing else matches; a unit that parses and then converts wrongly is worse
# than one that does not parse.

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


def _electrical_spelling_hint(a: Unit, b: Unit) -> str:
    """Explain a bare F or C that was meant as an electrical unit.

    "10 F" parses, as Fahrenheit, so nothing refuses it and a student who
    meant farads gets a temperature.  The mistake only becomes visible when
    the conversion fails against the unit on the other side, and that is the
    one place where the intended meaning can be read off rather than guessed:
    the other unit is a capacitance, or a charge.
    """
    for one, other in ((a, b), (b, a)):
        if one.text not in _ELECTRICAL_SPELLING:
            continue
        dimension, advice = _ELECTRICAL_SPELLING[one.text]
        if same_dimension(other.dimension, dimension):
            return f" If {one.text!r} was meant as an electrical unit: {advice}."
    return ""


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
            + _electrical_spelling_hint(a, b)
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
                # A supplied variable of the same name has already won: it is
                # in `dimensions`, so this is only reached when nothing was
                # supplied.  Every built-in is a pure number.
                if node.id in BUILTIN_CONSTANTS:
                    return DIMENSIONLESS
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
        raise UnitError(
            "Unsupported expression for dimensional checking." + power_notation_hint(expression)
        )

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

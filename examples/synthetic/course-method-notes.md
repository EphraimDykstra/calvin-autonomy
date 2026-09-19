# Synthetic Engineering 101 - Beam Analysis Method Notes

These notes are invented teaching material for testing this framework.
They define the method this synthetic course requires for cantilever beam problems.

## Required method for maximum bending stress

Compute the maximum bending moment at the fixed support as M = P * L.
Compute the rectangular section modulus as S = b * h^2 / 6.
Report the maximum bending stress as sigma = M / S converted to megapascals.

## Required method for maximum free-end deflection

Compute the second moment of area as I = b * h^3 / 12.
Compute the free-end deflection as delta = P * L^3 / (3 * E * I).
Report the free-end deflection converted to millimetres.

## Reporting conventions

State every input with its unit before substituting numbers.
Show the symbolic equation, then the numeric substitution, then the result.
Round only in the reported result, never in an intermediate value.

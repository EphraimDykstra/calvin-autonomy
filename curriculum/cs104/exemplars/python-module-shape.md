# Exemplar: CS 104 Python module (shape only)

Derived from the structure of the course's completed lab and homework files. The program below is invented, and its task matches none in the archive. Nothing here is a real answer.

This repo cannot run the program. The student runs it and confirms that it behaves as the prompt asks.

---

## Header (every file)

```python
"""CS [course number from the student's current template] - Lab [N.M]

[One to three plain sentences: what the program asks for, what it computes,
and what it does with invalid input.]

@author: [Student Name]
@author: [Partner Name]      (delete this line if working solo)
@date: [Season], [Year]
"""
```

- The first line carries the course number and the exercise label exactly as the prompt gives them. The archive shows both "CS 104" and "CS 108" here, and headers that disagree with their own file names. Check both against the current prompt.
- Homework files use the same header with `Homework [N.MM]` as the label.

## Short lab exercise (top-level script)

```python
"""CS [course number] - Lab [N.M]

Reads a [quantity] in [unit] and prints it converted to [other unit].
Rejects negative input.

@author: [Student Name]
@date: [Season], [Year]
"""

value = float(input())                 # prompt text only if the lab's example shows it

if value < 0:                          # validate before computing
    print("[message the prompt specifies]")
else:
    converted = value * [FACTOR]       # named intermediate, not one long line
    print([output in the exact format the prompt shows])
```

## Homework program (functions and a main guard, once taught)

```python
"""CS [course number] - Homework [N.MM]

[What the program does, including its edge-case behaviour, e.g. what happens
when the first input is already the stop value.]

@author: [Student Name]
@date: [Season], [Year]
"""

import math


def [compute_something](terms):
    """Return [what], using the first `terms` terms of [series]."""
    total = [initial value]
    for k in range(terms):
        total += [term k]
    return total


def main():
    """Read input, run the computation, report the result."""
    ...


if __name__ == "__main__":
    main()
```

## Small class (later labs)

```python
class [Thing]:
    def __init__(self, [a], [b]):
        """Store and validate the attributes; mark invalid input instead of crashing."""

    def __str__(self):
        """Return the printable form."""

    def [operation](self, other):
        """Return a new [Thing]; never modify self."""
```

## Before calling it done

- The student has run it on the prompt's example input and got the prompt's example output.
- The header's course number, exercise label, author line(s) and term are right.
- Invalid-input and boundary cases the prompt names each behave as described.

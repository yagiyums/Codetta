"""Shared exact numeric rules and the v0.1 note vocabulary."""

from fractions import Fraction


class CodettaError(ValueError):
    """A source, score, evaluation, or performance error."""


class DivisionByZero(CodettaError):
    pass


# One quarter note is one unit. Integer literals need only these four forms.
NOTE_BEATS = {"quarter": 1, "half": 2, "dotted-half": 3, "whole": 4}


def scale_value(body: Fraction, factor: Fraction, *, inverse: bool = False) -> Fraction:
    if inverse:
        if factor == 0:
            raise DivisionByZero("Division by zero in an inverse-scale enclosure")
        return body / factor
    return body * factor


def format_value(value: Fraction) -> str:
    return str(value)

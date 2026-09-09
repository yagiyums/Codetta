"""Shared errors and exact numeric formatting for Codetta v0.1."""

from fractions import Fraction


class CodettaError(ValueError):
    """A source, score, analysis, rendering, or performance error."""


class DivisionByZero(CodettaError):
    """Raised when a reciprocal phrase evaluates to zero."""


def format_value(value: Fraction) -> str:
    return str(value)

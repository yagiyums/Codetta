"""Shared errors and deterministic Codetta value formatting."""

from fractions import Fraction


class CodettaError(ValueError):
    """A source, score, analysis, rendering, or performance error."""


class DivisionByZero(CodettaError):
    """Raised when a reciprocal phrase evaluates to zero."""


def format_value(value: object) -> str:
    if type(value) is bool:
        return "true" if value else "false"
    if isinstance(value, list):
        return "[" + ", ".join(format_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{key}: {format_value(item)}" for key, item in value.items()) + "}"
    return str(value)

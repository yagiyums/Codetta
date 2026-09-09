"""Evaluate musical phrases using exact rational arithmetic."""

from fractions import Fraction

from codetta import ir
from codetta.semantics import CodettaError, DivisionByZero, scale_value


def _evaluate(node: ir.Phrase | ir.Emit, location: str) -> Fraction:
    if isinstance(node, ir.Emit):
        return _evaluate(node.body, location + "/output")
    if isinstance(node, ir.Span):
        return Fraction(node.beats)
    if isinstance(node, ir.Zero):
        return Fraction(0)
    if isinstance(node, ir.Sequence):
        return sum((_evaluate(child, f"{location}/phrase[{i}]")
                    for i, child in enumerate(node.children, 1)), Fraction(0))
    if isinstance(node, ir.Invert):
        return -_evaluate(node.body, location + "/invert")
    if isinstance(node, (ir.Scale, ir.Unscale)):
        factor = _evaluate(node.factor, location + "/control")
        body = _evaluate(node.body, location + "/body")
        try:
            return scale_value(body, factor, inverse=isinstance(node, ir.Unscale))
        except DivisionByZero as exc:
            raise DivisionByZero(f"{exc} at {location}") from exc
    raise TypeError(f"Unsupported IR node: {type(node).__name__}")


def evaluate(program: ir.Emit | ir.Phrase) -> Fraction:
    try:
        return _evaluate(program, "score")
    except RecursionError as exc:
        raise CodettaError("Score nesting is too deep to evaluate") from exc

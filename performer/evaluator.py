"""Evaluate Codetta execution IR with exact rational arithmetic."""

from fractions import Fraction

from codetta import ir
from codetta.semantics import CodettaError, DivisionByZero


def _evaluate(node: ir.Value, location: str) -> Fraction:
    if isinstance(node, ir.Constant):
        return node.value
    if isinstance(node, ir.Add):
        return sum((_evaluate(term, f"{location}/term[{index}]")
                    for index, term in enumerate(node.terms, 1)), Fraction(0))
    if isinstance(node, ir.Multiply):
        result = Fraction(1)
        for index, factor in enumerate(node.factors, 1):
            result *= _evaluate(factor, f"{location}/factor[{index}]")
        return result
    if isinstance(node, ir.Negate):
        return -_evaluate(node.body, location + "/negate")
    if isinstance(node, ir.Reciprocal):
        value = _evaluate(node.body, location + "/reciprocal")
        if value == 0:
            raise DivisionByZero(f"Division by zero at {location}")
        return Fraction(1, 1) / value
    raise TypeError(f"Unsupported IR node: {type(node).__name__}")


def evaluate(program: ir.Program) -> Fraction:
    if not isinstance(program, ir.Program) or not program.blocks:
        raise CodettaError("Performer needs a nonempty execution program")
    try:
        result = Fraction(0)
        for index, block in enumerate(program.blocks, 1):
            result = _evaluate(block.body, f"block[{index}]")
        return result
    except RecursionError as exc:
        raise CodettaError("Program nesting is too deep to evaluate") from exc

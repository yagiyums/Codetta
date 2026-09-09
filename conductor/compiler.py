"""Lower syntax to phrases without constant folding or evaluating expressions."""

from codetta import ast, ir
from codetta.semantics import CodettaError
from conductor.parser import parse


def _lower(node: ast.Expression) -> ir.Phrase:
    if isinstance(node, ast.Integer):
        if node.value == 0:
            return ir.Zero()
        return ir.Span(node.value) if node.value > 0 else ir.Invert(ir.Span(-node.value))
    if isinstance(node, ast.Negate):
        return ir.Invert(_lower(node.body))
    if isinstance(node, ast.Add):
        return ir.Sequence((_lower(node.left), _lower(node.right)))
    if isinstance(node, ast.Subtract):
        return ir.Sequence((_lower(node.left), ir.Invert(_lower(node.right))))
    if isinstance(node, ast.Multiply):
        return ir.Scale(_lower(node.left), _lower(node.right))
    if isinstance(node, ast.Divide):
        return ir.Unscale(_lower(node.left), _lower(node.right))
    raise TypeError(f"Unsupported AST node: {type(node).__name__}")


def compile_ast(tree: ast.Output) -> ir.Emit:
    try:
        return ir.Emit(_lower(tree.body))
    except RecursionError as exc:
        raise CodettaError("Expression nesting is too deep to compile") from exc


def compile_expression(source: str) -> ir.Emit:
    return compile_ast(parse(source))

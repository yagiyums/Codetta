"""Validate score-derived AST and lower it to exact execution IR."""

from __future__ import annotations

from fractions import Fraction

from codetta import ast, ir
from codetta.semantics import CodettaError


class SemanticError(CodettaError):
    pass


def _lower(node: ast.Expression, depth: int = 0) -> ir.Value:
    if depth > 128:
        raise SemanticError("Expression exceeds 128 semantic nesting levels")
    if isinstance(node, ast.Integer):
        if type(node.value) is not int or node.value < 0:
            raise SemanticError("Score-derived integers must be nonnegative")
        return ir.Constant(Fraction(node.value))
    if isinstance(node, ast.Sum):
        if len(node.terms) < 2:
            raise SemanticError("A Sum needs at least two terms")
        return ir.Add(tuple(_lower(term, depth + 1) for term in node.terms))
    if isinstance(node, ast.Product):
        if len(node.factors) < 2:
            raise SemanticError("A Product needs at least two factors")
        return ir.Multiply(tuple(_lower(factor, depth + 1) for factor in node.factors))
    if isinstance(node, ast.Negate):
        return ir.Negate(_lower(node.body, depth + 1))
    if isinstance(node, ast.Reciprocal):
        return ir.Reciprocal(_lower(node.body, depth + 1))
    raise SemanticError(f"Unsupported AST node {type(node).__name__}")


def analyze(program: ast.Program) -> ir.Program:
    if not isinstance(program, ast.Program) or not program.blocks:
        raise SemanticError("A Codetta program needs at least one block")
    return ir.Program(tuple(ir.Block(_lower(block.expression)) for block in program.blocks))

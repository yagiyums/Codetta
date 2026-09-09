"""Safe, deliberately small Python projection for Composer."""

from __future__ import annotations

import ast as python_ast

from codetta import ast
from codetta.semantics import CodettaError


class PythonProjectionError(CodettaError):
    """A Python draft is outside the Composer v0.1 subset."""


def _error(node: python_ast.AST, message: str) -> PythonProjectionError:
    line = getattr(node, "lineno", 1)
    column = getattr(node, "col_offset", 0) + 1
    return PythonProjectionError(f"{message} at line {line}, column {column}")


def _integer(node: python_ast.AST) -> int:
    if isinstance(node, python_ast.Constant) and type(node.value) is int and node.value >= 0:
        return node.value
    raise _error(node, "Fraction arguments must be nonnegative integer literals")


def _expression(node: python_ast.AST) -> ast.Expression:
    if isinstance(node, python_ast.Constant):
        if type(node.value) is not int or node.value < 0:
            raise _error(node, "Only nonnegative integer literals are supported; use unary '-'")
        return ast.Integer(node.value)
    if isinstance(node, python_ast.UnaryOp) and isinstance(node.op, python_ast.USub):
        return ast.Negate(_expression(node.operand))
    if isinstance(node, python_ast.BinOp):
        left, right = _expression(node.left), _expression(node.right)
        if isinstance(node.op, python_ast.Add):
            values = left.terms + (right,) if isinstance(left, ast.Sum) else (left, right)
            return ast.Sum(values)
        if isinstance(node.op, python_ast.Sub):
            values = left.terms + (ast.Negate(right),) if isinstance(left, ast.Sum) else (left, ast.Negate(right))
            return ast.Sum(values)
        if isinstance(node.op, python_ast.Mult):
            values = left.factors + (right,) if isinstance(left, ast.Product) else (left, right)
            return ast.Product(values)
        if isinstance(node.op, python_ast.Div):
            values = left.factors + (ast.Reciprocal(right),) if isinstance(left, ast.Product) else (left, ast.Reciprocal(right))
            return ast.Product(values)
        raise _error(node, "Only +, -, * and / operators are supported")
    if (isinstance(node, python_ast.Call) and isinstance(node.func, python_ast.Name)
            and node.func.id == "Fraction" and not node.keywords and len(node.args) in (1, 2)):
        numerator = _integer(node.args[0])
        denominator = _integer(node.args[1]) if len(node.args) == 2 else 1
        if denominator == 0:
            raise _error(node, "Fraction denominator cannot be zero")
        if denominator == 1:
            return ast.Integer(numerator)
        return ast.Product((ast.Integer(numerator), ast.Reciprocal(ast.Integer(denominator))))
    raise _error(node, "Unsupported Python syntax in Codetta Composer")


def parse_python(source: str) -> ast.Program:
    """Parse Python without executing it and return the Codetta AST."""
    try:
        module = python_ast.parse(source, mode="exec")
    except SyntaxError as exc:
        raise PythonProjectionError(
            f"{exc.msg} at line {exc.lineno or 1}, column {exc.offset or 1}"
        ) from exc
    statements = list(module.body)
    if statements and isinstance(statements[0], python_ast.ImportFrom):
        imported = statements.pop(0)
        if not (imported.module == "fractions" and imported.level == 0
                and len(imported.names) == 1 and imported.names[0].name == "Fraction"
                and imported.names[0].asname is None):
            raise _error(imported, "Only 'from fractions import Fraction' is allowed")
    if len(statements) != 1:
        raise PythonProjectionError("Enter one expression or one assignment to result")
    statement = statements[0]
    if isinstance(statement, python_ast.Expr):
        value = statement.value
    elif (isinstance(statement, python_ast.Assign) and len(statement.targets) == 1
          and isinstance(statement.targets[0], python_ast.Name)
          and statement.targets[0].id == "result"):
        value = statement.value
    else:
        raise _error(statement, "The program must be an expression or an assignment to result")
    return ast.Program((ast.Block(_expression(value)),))


def _has_reciprocal(node: ast.Expression) -> bool:
    if isinstance(node, ast.Reciprocal):
        return True
    if isinstance(node, (ast.Negate,)):
        return _has_reciprocal(node.body)
    if isinstance(node, ast.Sum):
        return any(_has_reciprocal(item) for item in node.terms)
    if isinstance(node, ast.Product):
        return any(_has_reciprocal(item) for item in node.factors)
    return False


def _emit(node: ast.Expression, parent: int, fractions: bool) -> str:
    if isinstance(node, ast.Integer):
        return f"Fraction({node.value})" if fractions else str(node.value)
    if isinstance(node, ast.Negate):
        text = "-" + _emit(node.body, 30, fractions)
        return f"({text})" if parent > 30 else text
    if isinstance(node, ast.Reciprocal):
        text = f"Fraction(1) / {_emit(node.body, 21, fractions)}"
        return f"({text})" if parent > 20 else text
    if isinstance(node, ast.Product):
        text = " * ".join(_emit(item, 20, fractions) for item in node.factors)
        return f"({text})" if parent > 20 else text
    if isinstance(node, ast.Sum):
        pieces: list[str] = []
        for index, item in enumerate(node.terms):
            if isinstance(item, ast.Negate) and index:
                pieces.append("- " + _emit(item.body, 11, fractions))
            else:
                pieces.append(("+ " if index else "") + _emit(item, 10, fractions))
        text = " ".join(pieces)
        return f"({text})" if parent > 10 else text
    raise TypeError(type(node).__name__)


def emit_python(program: ast.Program) -> str:
    if len(program.blocks) != 1:
        raise PythonProjectionError("Python projection supports one expression block")
    expression = program.blocks[0].expression
    fractions = _has_reciprocal(expression)
    prefix = "from fractions import Fraction\n\n" if fractions else ""
    return f"{prefix}result = {_emit(expression, 0, fractions)}\n"

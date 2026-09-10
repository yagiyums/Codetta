"""Safe, deliberately small Python projection for Composer."""

from __future__ import annotations

import ast as python_ast
import math

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
    try:
        return _parse_v01_statements(statements)
    except PythonProjectionError:
        return _parse_v02_module(module)


def _parse_v01_statements(source_statements: list[python_ast.stmt]) -> ast.Program:
    statements = list(source_statements)
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


def _v02_expression(node: python_ast.AST) -> ast.ExpressionV02:
    if isinstance(node, python_ast.Constant):
        if type(node.value) is bool:
            return ast.BoolLiteral(node.value)
        if type(node.value) is int and node.value >= 0:
            return ast.Integer(node.value)
        if type(node.value) is float:
            if not math.isfinite(node.value):
                raise _error(node, "Float literal must be finite")
            text = repr(node.value).lower()
            if "e" in text:
                mantissa, exponent_text = text.split("e")
                exponent = int(exponent_text)
            else:
                mantissa, exponent = text, 0
            if "." in mantissa:
                whole, fraction = mantissa.split(".")
                exponent -= len(fraction)
                significand = int(whole + fraction)
            else:
                significand = int(mantissa)
            return ast.FloatLiteral(significand, exponent)
        if isinstance(node.value, str):
            raise _error(node, "String values are only supported as Struct field names")
        raise _error(node, "Unsupported literal")
    if isinstance(node, python_ast.Name):
        return ast.VariableRef(node.id)
    if isinstance(node, python_ast.UnaryOp):
        if isinstance(node.op, python_ast.USub):
            return ast.UnaryExpr("-", _v02_expression(node.operand))
        if isinstance(node.op, python_ast.Not):
            return ast.UnaryExpr("not", _v02_expression(node.operand))
        raise _error(node, "Only unary '-' and 'not' are supported")
    if isinstance(node, python_ast.BinOp):
        operators = {
            python_ast.Add: "+", python_ast.Sub: "-",
            python_ast.Mult: "*", python_ast.Div: "/",
        }
        operator = next((text for kind, text in operators.items() if isinstance(node.op, kind)), None)
        if operator is None:
            raise _error(node, "Only +, -, * and / operators are supported")
        return ast.BinaryExpr(operator, _v02_expression(node.left), _v02_expression(node.right))
    if isinstance(node, python_ast.Compare):
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise _error(node, "Chained comparisons are not supported")
        operators = {python_ast.Lt: "<", python_ast.Gt: ">", python_ast.Eq: "=="}
        operator = next((text for kind, text in operators.items() if isinstance(node.ops[0], kind)), None)
        if operator is None:
            raise _error(node, "Only <, > and == comparisons are supported")
        return ast.Comparison(operator, _v02_expression(node.left),
                              _v02_expression(node.comparators[0]))
    if isinstance(node, (python_ast.List, python_ast.Tuple)):
        return ast.ArrayLiteral(tuple(_v02_expression(item) for item in node.elts))
    if isinstance(node, python_ast.Dict):
        fields = []
        for key, value in zip(node.keys, node.values):
            if not isinstance(key, python_ast.Constant) or not isinstance(key.value, str):
                raise _error(node, "Struct fields need string literal names")
            fields.append((key.value, _v02_expression(value)))
        return ast.StructLiteral(tuple(fields))
    if isinstance(node, python_ast.Subscript):
        value = _v02_expression(node.value)
        if isinstance(node.slice, python_ast.Constant) and isinstance(node.slice.value, str):
            return ast.FieldAccess(value, node.slice.value)
        return ast.ArrayAccess(value, _v02_expression(node.slice))
    if isinstance(node, python_ast.Attribute):
        return ast.FieldAccess(_v02_expression(node.value), node.attr)
    if isinstance(node, python_ast.Call):
        if not isinstance(node.func, python_ast.Name) or node.keywords:
            raise _error(node, "Calls need a simple function or section name and positional arguments")
        if node.func.id == "Fraction" and len(node.args) in (1, 2):
            numerator = _integer(node.args[0])
            denominator = _integer(node.args[1]) if len(node.args) == 2 else 1
            if denominator == 0:
                raise _error(node, "Fraction denominator cannot be zero")
            return ast.BinaryExpr("/", ast.Integer(numerator), ast.Integer(denominator))
        return ast.FunctionCall(node.func.id, tuple(_v02_expression(item) for item in node.args))
    raise _error(node, "Unsupported Python syntax in Codetta Composer")


def _v02_statements(nodes: list[python_ast.stmt], *, in_function: bool) -> tuple[ast.Statement, ...]:
    result: list[ast.Statement] = []
    for node in nodes:
        if isinstance(node, python_ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if not isinstance(target, python_ast.Name):
                raise _error(target, "Assignment target must be a Voice name")
            result.append(ast.Assignment(target.id, _v02_expression(node.value)))
        elif isinstance(node, python_ast.AugAssign) and isinstance(node.target, python_ast.Name):
            operators = {python_ast.Add: "+", python_ast.Sub: "-",
                         python_ast.Mult: "*", python_ast.Div: "/"}
            operator = next((text for kind, text in operators.items() if isinstance(node.op, kind)), None)
            if operator is None:
                raise _error(node, "Unsupported augmented assignment")
            result.append(ast.Assignment(node.target.id, ast.BinaryExpr(
                operator, ast.VariableRef(node.target.id), _v02_expression(node.value))))
        elif isinstance(node, python_ast.If):
            result.append(ast.If(_v02_expression(node.test),
                                 _v02_statements(node.body, in_function=in_function),
                                 _v02_statements(node.orelse, in_function=in_function)))
        elif isinstance(node, python_ast.For):
            if not isinstance(node.target, python_ast.Name) or node.orelse:
                raise _error(node, "for needs one iterator Voice and no else clause")
            if not (isinstance(node.iter, python_ast.Call)
                    and isinstance(node.iter.func, python_ast.Name)
                    and node.iter.func.id == "range" and not node.iter.keywords
                    and len(node.iter.args) == 1):
                raise _error(node, "for must use range(count) or range(length(array))")
            result.append(ast.For(node.target.id, _v02_expression(node.iter.args[0]),
                                  _v02_statements(node.body, in_function=in_function)))
        elif isinstance(node, python_ast.While):
            if node.orelse:
                raise _error(node, "while else is not supported")
            result.append(ast.While(_v02_expression(node.test),
                                    _v02_statements(node.body, in_function=in_function)))
        elif isinstance(node, python_ast.Return):
            if not in_function:
                raise _error(node, "return is only valid in a function section")
            result.append(ast.Return(None if node.value is None else _v02_expression(node.value)))
        elif isinstance(node, python_ast.Pass):
            continue
        else:
            raise _error(node, "Unsupported statement in Codetta v0.2")
    return tuple(result)


def _parse_v02_module(module: python_ast.Module) -> ast.Program:
    body = list(module.body)
    if body and isinstance(body[0], python_ast.ImportFrom):
        imported = body.pop(0)
        if not (imported.module == "fractions" and imported.level == 0
                and len(imported.names) == 1 and imported.names[0].name == "Fraction"
                and imported.names[0].asname is None):
            raise _error(imported, "Only 'from fractions import Fraction' is allowed")
    functions: list[ast.FunctionDecl] = []
    statements: list[python_ast.stmt] = []
    for node in body:
        if isinstance(node, python_ast.FunctionDef):
            if node.decorator_list or node.returns is not None or node.args.vararg or node.args.kwarg:
                raise _error(node, "Function sections do not support decorators, annotations or variadic arguments")
            if node.args.posonlyargs or node.args.kwonlyargs or node.args.defaults or node.args.kw_defaults:
                raise _error(node, "Function parameters must be simple required positional Voices")
            functions.append(ast.FunctionDecl(
                node.name, tuple(argument.arg for argument in node.args.args),
                _v02_statements(node.body, in_function=True),
            ))
        else:
            statements.append(node)
    if not statements:
        raise PythonProjectionError("A Codetta v0.2 program needs top-level statements")
    program = ast.Program(statements=_v02_statements(statements, in_function=False),
                          functions=tuple(functions), language_version="0.2")
    _validate_v02_calls(program)
    return program


def _walk_v02_expression(node: ast.ExpressionV02):
    yield node
    if isinstance(node, (ast.Negate, ast.Reciprocal, ast.UnaryExpr)):
        yield from _walk_v02_expression(node.body)
    elif isinstance(node, (ast.BinaryExpr, ast.Comparison)):
        yield from _walk_v02_expression(node.left)
        yield from _walk_v02_expression(node.right)
    elif isinstance(node, ast.Sum):
        for item in node.terms:
            yield from _walk_v02_expression(item)
    elif isinstance(node, ast.Product):
        for item in node.factors:
            yield from _walk_v02_expression(item)
    elif isinstance(node, ast.ArrayLiteral):
        for item in node.elements:
            yield from _walk_v02_expression(item)
    elif isinstance(node, ast.ArrayAccess):
        yield from _walk_v02_expression(node.array)
        yield from _walk_v02_expression(node.index)
    elif isinstance(node, ast.StructLiteral):
        for _, item in node.fields:
            yield from _walk_v02_expression(item)
    elif isinstance(node, ast.FieldAccess):
        yield from _walk_v02_expression(node.value)
    elif isinstance(node, ast.FunctionCall):
        for item in node.arguments:
            yield from _walk_v02_expression(item)


def _walk_v02_statements(nodes: tuple[ast.Statement, ...]):
    for node in nodes:
        yield node
        if isinstance(node, ast.Assignment):
            yield from _walk_v02_expression(node.value)
        elif isinstance(node, ast.If):
            yield from _walk_v02_expression(node.condition)
            yield from _walk_v02_statements(node.true_body)
            yield from _walk_v02_statements(node.false_body)
        elif isinstance(node, ast.For):
            yield from _walk_v02_expression(node.iterable)
            yield from _walk_v02_statements(node.body)
        elif isinstance(node, ast.While):
            yield from _walk_v02_expression(node.condition)
            yield from _walk_v02_statements(node.body)
        elif isinstance(node, ast.Return) and node.value is not None:
            yield from _walk_v02_expression(node.value)


def _validate_v02_calls(program: ast.Program) -> None:
    allowed = {function.name for function in program.functions} | {"len", "length"}
    nodes = list(_walk_v02_statements(program.statements))
    for function in program.functions:
        nodes.extend(_walk_v02_statements(function.body))
    for node in nodes:
        if isinstance(node, ast.FunctionCall) and node.function_name not in allowed:
            raise PythonProjectionError(f"Unknown function section {node.function_name!r}")


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
    if program.language_version == "0.2":
        return _emit_v02_program(program)
    if len(program.blocks) != 1:
        raise PythonProjectionError("Python projection supports one expression block")
    expression = program.blocks[0].expression
    fractions = _has_reciprocal(expression)
    prefix = "from fractions import Fraction\n\n" if fractions else ""
    return f"{prefix}result = {_emit(expression, 0, fractions)}\n"


def _emit_v02_expression(node: ast.ExpressionV02, parent: int = 0) -> str:
    if isinstance(node, ast.Integer):
        return str(node.value)
    if isinstance(node, ast.FloatLiteral):
        return repr(float(f"{node.significand}e{node.exponent}"))
    if isinstance(node, ast.BoolLiteral):
        return "True" if node.value else "False"
    if isinstance(node, ast.VariableRef):
        return node.name
    if isinstance(node, (ast.Negate, ast.UnaryExpr)):
        operator = "-" if isinstance(node, ast.Negate) else node.operator
        text = f"{operator} {_emit_v02_expression(node.body, 40)}" if operator == "not" else f"-{_emit_v02_expression(node.body, 40)}"
        return f"({text})" if parent > 40 else text
    if isinstance(node, ast.Reciprocal):
        text = f"1 / {_emit_v02_expression(node.body, 31)}"
        return f"({text})" if parent > 30 else text
    if isinstance(node, (ast.Sum, ast.Product)):
        values = node.terms if isinstance(node, ast.Sum) else node.factors
        operator, precedence = (" + ", 20) if isinstance(node, ast.Sum) else (" * ", 30)
        text = operator.join(_emit_v02_expression(value, precedence) for value in values)
        return f"({text})" if parent > precedence else text
    if isinstance(node, ast.BinaryExpr):
        precedence = 20 if node.operator in ("+", "-") else 30
        text = (f"{_emit_v02_expression(node.left, precedence)} {node.operator} "
                f"{_emit_v02_expression(node.right, precedence + 1)}")
        return f"({text})" if parent > precedence else text
    if isinstance(node, ast.Comparison):
        text = (f"{_emit_v02_expression(node.left, 11)} {node.operator} "
                f"{_emit_v02_expression(node.right, 11)}")
        return f"({text})" if parent > 10 else text
    if isinstance(node, ast.ArrayLiteral):
        return "[" + ", ".join(_emit_v02_expression(item) for item in node.elements) + "]"
    if isinstance(node, ast.ArrayAccess):
        return f"{_emit_v02_expression(node.array, 50)}[{_emit_v02_expression(node.index)}]"
    if isinstance(node, ast.StructLiteral):
        return "{" + ", ".join(
            f"{name!r}: {_emit_v02_expression(value)}" for name, value in node.fields
        ) + "}"
    if isinstance(node, ast.FieldAccess):
        return f"{_emit_v02_expression(node.value, 50)}[{node.field_name!r}]"
    if isinstance(node, ast.FunctionCall):
        name = "len" if node.function_name == "length" else node.function_name
        return f"{name}(" + ", ".join(_emit_v02_expression(arg) for arg in node.arguments) + ")"
    raise TypeError(f"Unsupported v0.2 node {type(node).__name__}")


def _emit_v02_statements(nodes: tuple[ast.Statement, ...], indent: int) -> list[str]:
    prefix = "    " * indent
    result: list[str] = []
    for node in nodes:
        if isinstance(node, ast.Assignment):
            result.append(f"{prefix}{node.target} = {_emit_v02_expression(node.value)}")
        elif isinstance(node, ast.If):
            result.append(f"{prefix}if {_emit_v02_expression(node.condition)}:")
            result.extend(_emit_v02_statements(node.true_body, indent + 1) or [prefix + "    pass"])
            if node.false_body:
                result.append(f"{prefix}else:")
                result.extend(_emit_v02_statements(node.false_body, indent + 1))
        elif isinstance(node, ast.For):
            result.append(f"{prefix}for {node.iterator} in range({_emit_v02_expression(node.iterable)}):")
            result.extend(_emit_v02_statements(node.body, indent + 1) or [prefix + "    pass"])
        elif isinstance(node, ast.While):
            result.append(f"{prefix}while {_emit_v02_expression(node.condition)}:")
            result.extend(_emit_v02_statements(node.body, indent + 1) or [prefix + "    pass"])
        elif isinstance(node, ast.Return):
            suffix = "" if node.value is None else " " + _emit_v02_expression(node.value)
            result.append(f"{prefix}return{suffix}")
        else:
            raise TypeError(f"Unsupported statement {type(node).__name__}")
    return result


def _emit_v02_program(program: ast.Program) -> str:
    lines: list[str] = []
    for function in program.functions:
        lines.append(f"def {function.name}({', '.join(function.parameters)}):")
        lines.extend(_emit_v02_statements(function.body, 1) or ["    pass"])
        lines.append("")
    lines.extend(_emit_v02_statements(program.statements, 0))
    return "\n".join(lines).rstrip() + "\n"

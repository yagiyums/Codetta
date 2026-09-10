"""Validate score-derived AST and lower it to exact execution IR."""

from __future__ import annotations

from fractions import Fraction
from dataclasses import dataclass
import math

from codetta import ast, ir
from codetta.semantics import CodettaError
from codetta.type_system import (ArrayType, BOOL, FLOAT, INT,
                                 RATIONAL, StructType, Type, VOID, compatible,
                                 is_numeric, numeric_result)


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
        if isinstance(program, ast.Program) and program.language_version == "0.2":
            return _Analyzer(program).lower()
        raise SemanticError("A Codetta program needs at least one block")
    return ir.Program(tuple(ir.Block(_lower(block.expression)) for block in program.blocks))


@dataclass(frozen=True)
class _Symbol:
    identifier: str
    value_type: Type


def _unify(left: Type, right: Type) -> Type | None:
    if left == right:
        return left
    if is_numeric(left) and is_numeric(right):
        return numeric_result(left, right)
    if isinstance(left, ArrayType) and isinstance(right, ArrayType):
        element = _unify(left.element, right.element)
        return ArrayType(element) if element is not None else None
    return None


class _Analyzer:
    """Resolve v0.2 symbols, infer types and produce structured typed IR."""

    def __init__(self, program: ast.Program):
        self.program = program
        self.declarations: dict[str, ast.FunctionDecl] = {}
        self.compiled: dict[str, ir.Function] = {}
        self.compiling: set[str] = set()
        self.loop_number = 0
        self.return_types: list[Type] | None = None
        for declaration in program.functions:
            if not declaration.name.isidentifier() or declaration.name in self.declarations:
                raise SemanticError(f"Duplicate or invalid function name {declaration.name!r}")
            if len(set(declaration.parameters)) != len(declaration.parameters):
                raise SemanticError(f"Function {declaration.name} has duplicate parameters")
            self.declarations[declaration.name] = declaration

    def lower(self) -> ir.Program:
        environment: dict[str, _Symbol] = {}
        main = self._statements(self.program.statements, environment, "main")
        result = environment.get("result")
        return ir.Program((), main, tuple(self.compiled.values()),
                          result.identifier if result else None)

    def _define(self, environment: dict[str, _Symbol], scope: str,
                name: str, value_type: Type) -> _Symbol:
        if not name.isidentifier():
            raise SemanticError(f"Invalid Voice or variable name {name!r}")
        current = environment.get(name)
        if current is not None:
            if not compatible(current.value_type, value_type):
                raise SemanticError(
                    f"Cannot assign {value_type} to {name}, which has type {current.value_type}"
                )
            return current
        symbol = _Symbol(f"{scope}:{name}", value_type)
        environment[name] = symbol
        return symbol

    def _expression(self, node: ast.ExpressionV02,
                    environment: dict[str, _Symbol], scope: str) -> tuple[ir.ValueV02, Type]:
        if isinstance(node, ast.Integer):
            if type(node.value) is not int or node.value < 0:
                raise SemanticError("Score-derived integers must be nonnegative")
            return ir.TypedConstant(node.value, INT), INT
        if isinstance(node, ast.FloatLiteral):
            if type(node.significand) is not int or type(node.exponent) is not int:
                raise SemanticError("Float components must be integers")
            try:
                value = float(f"{node.significand}e{node.exponent}")
            except (OverflowError, ValueError) as exc:
                raise SemanticError("Float value is outside the supported range") from exc
            if not math.isfinite(value):
                raise SemanticError("Float value must be finite")
            return ir.TypedConstant(value, FLOAT), FLOAT
        if isinstance(node, ast.BoolLiteral):
            if type(node.value) is not bool:
                raise SemanticError("Bool literal must be true or false")
            return ir.TypedConstant(node.value, BOOL), BOOL
        if isinstance(node, ast.VariableRef):
            symbol = environment.get(node.name)
            if symbol is None:
                raise SemanticError(f"Voice {node.name!r} is not live in this scope")
            return ir.Load(symbol.identifier, symbol.value_type), symbol.value_type
        if isinstance(node, ast.Negate):
            body, kind = self._expression(node.body, environment, scope)
            if not is_numeric(kind):
                raise SemanticError(f"Negation needs a number, not {kind}")
            return ir.Unary("-", body, kind), kind
        if isinstance(node, ast.Reciprocal):
            body, kind = self._expression(node.body, environment, scope)
            if not is_numeric(kind):
                raise SemanticError(f"Reciprocal needs a number, not {kind}")
            result = FLOAT if kind == FLOAT else RATIONAL
            return ir.Unary("reciprocal", body, result), result
        if isinstance(node, ast.UnaryExpr):
            body, kind = self._expression(node.body, environment, scope)
            if node.operator == "-" and is_numeric(kind):
                return ir.Unary("-", body, kind), kind
            if node.operator == "not" and kind == BOOL:
                return ir.Unary("not", body, BOOL), BOOL
            raise SemanticError(f"Operator {node.operator!r} does not accept {kind}")
        if isinstance(node, (ast.Sum, ast.Product)):
            values = node.terms if isinstance(node, ast.Sum) else node.factors
            operator = "+" if isinstance(node, ast.Sum) else "*"
            if len(values) < 2:
                raise SemanticError(f"A {type(node).__name__} needs at least two values")
            result, kind = self._expression(values[0], environment, scope)
            for value_node in values[1:]:
                right, right_kind = self._expression(value_node, environment, scope)
                combined = numeric_result(kind, right_kind)
                if combined is None:
                    raise SemanticError(f"Operator {operator} needs numeric operands")
                result, kind = ir.Binary(operator, result, right, combined), combined
            return result, kind
        if isinstance(node, ast.BinaryExpr):
            left, left_kind = self._expression(node.left, environment, scope)
            right, right_kind = self._expression(node.right, environment, scope)
            if node.operator not in ("+", "-", "*", "/"):
                raise SemanticError(f"Unsupported binary operator {node.operator!r}")
            kind = numeric_result(left_kind, right_kind, division=node.operator == "/")
            if kind is None:
                raise SemanticError(f"Operator {node.operator} needs numeric operands")
            return ir.Binary(node.operator, left, right, kind), kind
        if isinstance(node, ast.Comparison):
            left, left_kind = self._expression(node.left, environment, scope)
            right, right_kind = self._expression(node.right, environment, scope)
            if node.operator not in ("<", ">", "=="):
                raise SemanticError(f"Unsupported comparison {node.operator!r}")
            if node.operator in ("<", ">") and (
                    not is_numeric(left_kind) or not is_numeric(right_kind)):
                raise SemanticError(f"Comparison {node.operator} needs numeric operands")
            if node.operator == "==" and _unify(left_kind, right_kind) is None:
                raise SemanticError(f"Cannot compare {left_kind} and {right_kind}")
            return ir.Compare(node.operator, left, right, BOOL), BOOL
        if isinstance(node, ast.ArrayLiteral):
            if not node.elements:
                raise SemanticError("An empty Array needs an inferred element type")
            lowered = [self._expression(item, environment, scope) for item in node.elements]
            element_type = lowered[0][1]
            for _, item_type in lowered[1:]:
                merged = _unify(element_type, item_type)
                if merged is None:
                    raise SemanticError(f"Array elements cannot mix {element_type} and {item_type}")
                element_type = merged
            kind = ArrayType(element_type)
            return ir.MakeArray(tuple(item for item, _ in lowered), kind), kind
        if isinstance(node, ast.ArrayAccess):
            array, array_kind = self._expression(node.array, environment, scope)
            index, index_kind = self._expression(node.index, environment, scope)
            if not isinstance(array_kind, ArrayType) or index_kind != INT:
                raise SemanticError("Array access needs Array<T> and Int")
            return ir.Index(array, index, array_kind.element), array_kind.element
        if isinstance(node, ast.StructLiteral):
            if (not node.fields or len({name for name, _ in node.fields}) != len(node.fields)
                    or any(not isinstance(name, str) or not name.isidentifier()
                           for name, _ in node.fields)):
                raise SemanticError("A Struct needs unique identifier field names")
            lowered = tuple((name, *self._expression(value, environment, scope))
                            for name, value in node.fields)
            kind = StructType(tuple((name, value_type) for name, _, value_type in lowered))
            return ir.MakeStruct(tuple((name, value) for name, value, _ in lowered), kind), kind
        if isinstance(node, ast.FieldAccess):
            value, value_kind = self._expression(node.value, environment, scope)
            if not isinstance(value_kind, StructType):
                raise SemanticError(f"Field access needs a Struct, not {value_kind}")
            field_type = value_kind.field(node.field_name)
            if field_type is None:
                raise SemanticError(f"Struct has no field {node.field_name!r}")
            return ir.GetField(value, node.field_name, field_type), field_type
        if isinstance(node, ast.FunctionCall):
            arguments = tuple(self._expression(arg, environment, scope) for arg in node.arguments)
            if node.function_name in ("len", "length"):
                if len(arguments) != 1 or not isinstance(arguments[0][1], ArrayType):
                    raise SemanticError("length needs exactly one Array")
                return ir.Call("@length", (arguments[0][0],), INT), INT
            function = self._compile_function(node.function_name,
                                              tuple(kind for _, kind in arguments))
            return ir.Call(function.name, tuple(value for value, _ in arguments),
                           function.result_type), function.result_type
        raise SemanticError(f"Unsupported v0.2 AST node {type(node).__name__}")

    def _statements(self, nodes: tuple[ast.Statement, ...],
                    environment: dict[str, _Symbol], scope: str) -> tuple[ir.Instruction, ...]:
        result: list[ir.Instruction] = []
        for node in nodes:
            if isinstance(node, ast.Assignment):
                value, kind = self._expression(node.value, environment, scope)
                symbol = self._define(environment, scope, node.target, kind)
                result.append(ir.Store(symbol.identifier, value, symbol.value_type))
            elif isinstance(node, ast.If):
                condition, condition_type = self._expression(node.condition, environment, scope)
                if condition_type != BOOL:
                    raise SemanticError(f"if condition must be Bool, not {condition_type}")
                true_environment = dict(environment)
                false_environment = dict(environment)
                true_body = self._statements(node.true_body, true_environment, scope)
                false_body = self._statements(node.false_body, false_environment, scope)
                for name in set(true_environment) & set(false_environment):
                    left, right = true_environment[name], false_environment[name]
                    merged = _unify(left.value_type, right.value_type)
                    if merged is None or left.identifier != right.identifier:
                        raise SemanticError(f"Branches assign incompatible values to {name}")
                    environment[name] = _Symbol(left.identifier, merged)
                result.append(ir.Branch(condition, true_body, false_body))
            elif isinstance(node, ast.For):
                iterable, iterable_type = self._expression(node.iterable, environment, scope)
                if iterable_type != INT and not isinstance(iterable_type, ArrayType):
                    raise SemanticError("for needs an Int count or Array")
                self.loop_number += 1
                loop_scope = f"{scope}/for{self.loop_number}"
                body_environment = dict(environment)
                iterator = self._define(body_environment, loop_scope, node.iterator, INT)
                body = self._statements(node.body, body_environment, loop_scope)
                result.append(ir.ForLoop(iterator.identifier, iterable, body))
            elif isinstance(node, ast.While):
                condition, condition_type = self._expression(node.condition, environment, scope)
                if condition_type != BOOL:
                    raise SemanticError(f"while condition must be Bool, not {condition_type}")
                body = self._statements(node.body, dict(environment), scope)
                # Lower the condition again so it observes values updated by the body.
                condition, _ = self._expression(node.condition, environment, scope)
                result.append(ir.WhileLoop(condition, body, node.test_at_end))
            elif isinstance(node, ast.Return):
                if self.return_types is None:
                    raise SemanticError("return is only valid inside a function section")
                if node.value is None:
                    value, kind = None, VOID
                else:
                    value, kind = self._expression(node.value, environment, scope)
                self.return_types.append(kind)
                result.append(ir.ReturnValue(value))
            else:
                raise SemanticError(f"Unsupported statement {type(node).__name__}")
        return tuple(result)

    def _compile_function(self, name: str, argument_types: tuple[Type, ...]) -> ir.Function:
        existing = self.compiled.get(name)
        if existing is not None:
            expected = tuple(kind for _, kind in existing.parameters)
            if len(expected) != len(argument_types) or any(
                    not compatible(wanted, actual) for wanted, actual in zip(expected, argument_types)):
                raise SemanticError(f"Function {name} called with incompatible argument types")
            return existing
        declaration = self.declarations.get(name)
        if declaration is None:
            raise SemanticError(f"Unknown function section {name!r}")
        if name in self.compiling:
            raise SemanticError("Recursive function inference is not supported in Codetta v0.2")
        if len(declaration.parameters) != len(argument_types):
            raise SemanticError(
                f"Function {name} expects {len(declaration.parameters)} arguments, got {len(argument_types)}"
            )
        self.compiling.add(name)
        try:
            scope = f"function:{name}"
            environment = {
                parameter: _Symbol(f"{scope}:{parameter}", kind)
                for parameter, kind in zip(declaration.parameters, argument_types)
            }
            previous_returns = self.return_types
            self.return_types = []
            body = self._statements(declaration.body, environment, scope)
            returns = self.return_types
            self.return_types = previous_returns
            if not returns:
                result_type = VOID
            else:
                result_type = returns[0]
                for return_type in returns[1:]:
                    merged = _unify(result_type, return_type)
                    if merged is None:
                        raise SemanticError(f"Function {name} has incompatible return types")
                    result_type = merged
            function = ir.Function(name, tuple(
                (environment[parameter].identifier, kind)
                for parameter, kind in zip(declaration.parameters, argument_types)
            ), body, result_type)
            self.compiled[name] = function
            return function
        finally:
            self.compiling.remove(name)

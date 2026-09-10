"""Evaluate Codetta execution IR with typed lexical environments."""

from dataclasses import dataclass
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


@dataclass(frozen=True)
class TraceEvent:
    kind: str
    name: str | None
    value: object


@dataclass(frozen=True)
class Evaluation:
    value: object
    trace: tuple[TraceEvent, ...]


def evaluate(program: ir.Program) -> object:
    if isinstance(program, ir.Program) and program.main:
        return evaluate_with_trace(program).value
    if not isinstance(program, ir.Program) or not program.blocks:
        raise CodettaError("Performer needs a nonempty execution program")
    try:
        result = Fraction(0)
        for index, block in enumerate(program.blocks, 1):
            result = _evaluate(block.body, f"block[{index}]")
        return result
    except RecursionError as exc:
        raise CodettaError("Program nesting is too deep to evaluate") from exc


def evaluate_with_trace(program: ir.Program, *, max_iterations: int = 10_000,
                        max_steps: int = 100_000, max_call_depth: int = 128) -> Evaluation:
    if not isinstance(program, ir.Program) or not program.main:
        return Evaluation(evaluate(program), ())
    evaluator = _Evaluator(program, max_iterations=max_iterations, max_steps=max_steps,
                           max_call_depth=max_call_depth)
    value = evaluator.run()
    return Evaluation(value, tuple(TraceEvent(kind, name, item) for kind, name, item in evaluator.trace))


class _Returned(Exception):
    def __init__(self, value: object):
        self.value = value


class _Evaluator:
    def __init__(self, program: ir.Program, *, max_iterations: int = 10_000,
                 max_steps: int = 100_000, max_call_depth: int = 128):
        self.program = program
        self.functions = {function.name: function for function in program.functions}
        self.max_iterations = max_iterations
        self.max_steps = max_steps
        self.max_call_depth = max_call_depth
        self.iterations = 0
        self.steps = 0
        self.call_depth = 0
        self.trace: list[list[object]] = []

    def _step(self) -> None:
        self.steps += 1
        if self.steps > self.max_steps:
            raise CodettaError(f"Execution exceeded {self.max_steps:,} steps")

    def value(self, node: ir.ValueV02, environment: dict[str, object]) -> object:
        self._step()
        if isinstance(node, ir.TypedConstant):
            return node.value
        if isinstance(node, ir.Load):
            if node.symbol not in environment:
                raise CodettaError(f"Variable {node.symbol} is not initialized")
            return environment[node.symbol]
        if isinstance(node, ir.Unary):
            value = self.value(node.body, environment)
            if node.operator == "-":
                return -value
            if node.operator == "not":
                return not value
            if node.operator == "reciprocal":
                if value == 0:
                    raise DivisionByZero("Division by zero in reciprocal")
                return 1.0 / value if isinstance(value, float) else Fraction(1, 1) / value
        if isinstance(node, ir.Binary):
            left = self.value(node.left, environment)
            right = self.value(node.right, environment)
            if node.operator == "+":
                return left + right
            if node.operator == "-":
                return left - right
            if node.operator == "*":
                return left * right
            if node.operator == "/":
                if right == 0:
                    raise DivisionByZero("Division by zero")
                return left / right if isinstance(left, float) or isinstance(right, float) else Fraction(left, right)
        if isinstance(node, ir.Compare):
            left = self.value(node.left, environment)
            right = self.value(node.right, environment)
            return {"<": left < right, ">": left > right, "==": left == right}[node.operator]
        if isinstance(node, ir.MakeArray):
            return [self.value(item, environment) for item in node.elements]
        if isinstance(node, ir.Index):
            array = self.value(node.array, environment)
            index = self.value(node.index, environment)
            try:
                return array[index]
            except IndexError as exc:
                raise CodettaError(f"Array index {index} is out of range") from exc
        if isinstance(node, ir.MakeStruct):
            return {name: self.value(value, environment) for name, value in node.fields}
        if isinstance(node, ir.GetField):
            value = self.value(node.value, environment)
            return value[node.field_name]
        if isinstance(node, ir.Call):
            arguments = tuple(self.value(argument, environment) for argument in node.arguments)
            if node.function == "@length":
                return len(arguments[0])
            self.trace.append(["call", node.function, None])
            return self.call(node.function, arguments)
        raise TypeError(f"Unsupported typed IR value: {type(node).__name__}")

    def instructions(self, nodes: tuple[ir.Instruction, ...],
                     environment: dict[str, object]) -> None:
        for node in nodes:
            self._step()
            if isinstance(node, ir.Store):
                environment[node.symbol] = self.value(node.value, environment)
            elif isinstance(node, ir.Branch):
                selected = bool(self.value(node.condition, environment))
                self.trace.append(["branch", None, selected])
                body = node.true_body if selected else node.false_body
                self.instructions(body, environment)
            elif isinstance(node, ir.ForLoop):
                source = self.value(node.iterable, environment)
                count = len(source) if isinstance(source, list) else source
                if type(count) is not int or count < 0:
                    raise CodettaError("Counted repeat needs a nonnegative Int")
                trace = ["loop", None, count]
                self.trace.append(trace)
                for index in range(count):
                    self.iterations += 1
                    if self.iterations > self.max_iterations:
                        raise CodettaError(f"Execution exceeded {self.max_iterations:,} loop iterations")
                    environment[node.iterator] = index
                    self.instructions(node.body, environment)
            elif isinstance(node, ir.WhileLoop):
                trace = ["loop", None, 0]
                self.trace.append(trace)
                first = True
                while (node.test_at_end and first) or self.value(node.condition, environment):
                    first = False
                    self.iterations += 1
                    if self.iterations > self.max_iterations:
                        raise CodettaError(f"Execution exceeded {self.max_iterations:,} loop iterations")
                    trace[2] = int(trace[2]) + 1
                    self.instructions(node.body, environment)
            elif isinstance(node, ir.ReturnValue):
                raise _Returned(None if node.value is None else self.value(node.value, environment))
            else:
                raise TypeError(f"Unsupported typed IR instruction: {type(node).__name__}")

    def call(self, name: str, arguments: tuple[object, ...]) -> object:
        function = self.functions.get(name)
        if function is None:
            raise CodettaError(f"Unknown function {name}")
        self.call_depth += 1
        if self.call_depth > self.max_call_depth:
            raise CodettaError(f"Call depth exceeds {self.max_call_depth}")
        try:
            environment = {
                symbol: value for (symbol, _), value in zip(function.parameters, arguments)
            }
            try:
                self.instructions(function.body, environment)
            except _Returned as returned:
                return returned.value
            return None
        finally:
            self.call_depth -= 1

    def run(self) -> object:
        environment: dict[str, object] = {}
        try:
            self.instructions(self.program.main, environment)
        except _Returned as returned:
            return returned.value
        if self.program.result_symbol is not None:
            return environment.get(self.program.result_symbol)
        return None

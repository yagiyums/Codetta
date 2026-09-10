import unittest

from codetta import ast
from codetta.semantic_analyzer import SemanticError, analyze
from performer.evaluator import evaluate, evaluate_with_trace
from codetta.semantics import CodettaError


def run(statements, functions=()):
    program = ast.Program(statements=tuple(statements), functions=tuple(functions),
                          language_version="0.2")
    return evaluate(analyze(program))


class V02RuntimeTests(unittest.TestCase):
    def test_process_e2e_program_returns_ten(self):
        process = ast.FunctionDecl("process", ("values",), (
            ast.Assignment("total", ast.Integer(0)),
            ast.For("i", ast.FunctionCall("length", (ast.VariableRef("values"),)), (
                ast.Assignment("x", ast.ArrayAccess(ast.VariableRef("values"), ast.VariableRef("i"))),
                ast.If(ast.Comparison(">", ast.VariableRef("x"), ast.Integer(3)), (
                    ast.Assignment("total", ast.BinaryExpr(
                        "+", ast.VariableRef("total"), ast.VariableRef("x"))),
                )),
            )),
            ast.Return(ast.VariableRef("total")),
        ))
        result = run((
            ast.Assignment("values", ast.ArrayLiteral(tuple(map(ast.Integer, (1, 2, 4, 6))))),
            ast.Assignment("result", ast.FunctionCall("process", (ast.VariableRef("values"),))),
        ), (process,))
        self.assertEqual(result, 10)

    def test_float_bool_while_struct_and_access(self):
        result = run((
            ast.Assignment("point", ast.StructLiteral((
                ("height", ast.FloatLiteral(1785, -1)),
                ("active", ast.BoolLiteral(True)),
            ))),
            ast.Assignment("height", ast.FieldAccess(ast.VariableRef("point"), "height")),
            ast.Assignment("keep", ast.FieldAccess(ast.VariableRef("point"), "active")),
            ast.Assignment("n", ast.Integer(0)),
            ast.While(ast.Comparison("<", ast.VariableRef("n"), ast.Integer(3)), (
                ast.Assignment("n", ast.BinaryExpr("+", ast.VariableRef("n"), ast.Integer(1))),
            )),
            ast.If(ast.VariableRef("keep"), (
                ast.Assignment("result", ast.BinaryExpr("+", ast.VariableRef("height"),
                                                        ast.VariableRef("n"))),
            ), (
                ast.Assignment("result", ast.FloatLiteral(0, 0)),
            )),
        ))
        self.assertAlmostEqual(result, 181.5)

    def test_type_errors_are_rejected(self):
        with self.assertRaisesRegex(SemanticError, "if condition must be Bool"):
            run((ast.If(ast.Integer(1), ()), ast.Assignment("result", ast.Integer(0))))
        with self.assertRaisesRegex(SemanticError, "Array access needs"):
            run((ast.Assignment("result", ast.ArrayAccess(ast.Integer(1), ast.Integer(0))),))

    def test_configurable_iteration_limit_stops_runaway_loops(self):
        program = ast.Program(statements=(
            ast.Assignment("keep", ast.BoolLiteral(True)),
            ast.While(ast.VariableRef("keep"), ()),
            ast.Assignment("result", ast.Integer(0)),
        ), language_version="0.2")
        with self.assertRaisesRegex(CodettaError, "2 loop iterations"):
            evaluate_with_trace(analyze(program), max_iterations=2)


if __name__ == "__main__":
    unittest.main()

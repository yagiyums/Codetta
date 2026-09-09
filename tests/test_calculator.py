from fractions import Fraction
import random
import unittest

from codetta import ast, ir
from codetta.semantics import DivisionByZero
from conductor.compiler import compile_expression
from conductor.parser import ParseError, parse
from conductor.score_writer import to_svg
from performer.evaluator import evaluate
from performer.score_reader import from_svg


class CalculatorTests(unittest.TestCase):
    def test_precedence_and_grouping(self):
        self.assertEqual(parse("(3 + 5) * 2"), ast.Output(
            ast.Multiply(ast.Add(ast.Integer(3), ast.Integer(5)), ast.Integer(2))))
        self.assertEqual(parse("3 + 5 * 2"), ast.Output(
            ast.Add(ast.Integer(3), ast.Multiply(ast.Integer(5), ast.Integer(2)))))

    def test_structure_is_not_constant_folded(self):
        program = compile_expression("(3 + 5) * 2")
        self.assertEqual(program, ir.Emit(ir.Scale(ir.Sequence((ir.Span(3), ir.Span(5))), ir.Span(2))))
        self.assertNotEqual(program, compile_expression("16"))

    def test_arithmetic_round_trips(self):
        cases = {
            "(3 + 5) * 2": 16, "3 + 5 * 2": 13, "3 - 5": -2,
            "8 / 4 / 2": 1, "8 / (4 / 2)": 4, "10 - 3 - 2": 5,
            "3 / 2": Fraction(3, 2), "-3 / 2": Fraction(-3, 2),
            "1 / 3 + 1 / 6": Fraction(1, 2), "-(3 + 5)": -8,
            "--3": 3, "3--5": 8, "(1 + 2) * (5 - 3)": 6,
            "3 / -2": Fraction(-3, 2), "-3 * -2": 6,
            "0": 0, "0 / 5": 0, "5 * 0": 0, "-0": 0,
            " 3\n +\t5 ": 8, "0003 + 005": 8,
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                original = compile_expression(source)
                restored = from_svg(to_svg(original))
                self.assertEqual(restored, original)
                self.assertEqual(evaluate(restored), expected)
                self.assertIsInstance(evaluate(restored), Fraction)

    def test_invalid_input(self):
        for source in ("", " ", "()", "1+", "1 2", "2(3)", "1.5", "1//2",
                       "1**2", "(1+2", "1+2)", "x", "print(3)", "+3", "３"):
            with self.subTest(source=source), self.assertRaises(ParseError):
                parse(source)

    def test_parser_reports_position(self):
        with self.assertRaisesRegex(ParseError, "line 2, column 2"):
            parse("1 +\n ?")

    def test_division_by_zero_is_a_runtime_error(self):
        for source in ("1 / 0", "1 / (3 - 3)", "0 * (1 / 0)", "0 / 0"):
            with self.subTest(source=source):
                score = to_svg(compile_expression(source))
                with self.assertRaisesRegex(DivisionByZero, "score"):
                    evaluate(from_svg(score))

    def test_random_expressions_against_independent_fraction_arithmetic(self):
        rng = random.Random(42)

        def expression(depth):
            if depth == 0:
                value = rng.randrange(0, 8)
                return str(value), Fraction(value)
            left, a = expression(depth - 1)
            right, b = expression(depth - 1)
            op = rng.choice(("+", "-", "*", "/") if b else ("+", "-", "*"))
            if op == "+":
                value = a + b
            elif op == "-":
                value = a - b
            elif op == "*":
                value = a * b
            else:
                value = a / b
            return f"({left} {op} {right})", value

        for _ in range(80):
            source, expected = expression(3)
            with self.subTest(source=source):
                self.assertEqual(evaluate(from_svg(to_svg(compile_expression(source)))), expected)


if __name__ == "__main__":
    unittest.main()

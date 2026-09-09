from dataclasses import replace
from fractions import Fraction
import random
import unittest

from codetta import ast
from codetta.score_parser import parse_score
from codetta.semantic_analyzer import analyze
from codetta.semantics import DivisionByZero
from conductor.compiler import compile_expression
from conductor.parser import ParseError, parse
from performer.evaluator import evaluate


def execute(score):
    return evaluate(analyze(parse_score(score)))


class LanguageTests(unittest.TestCase):
    def test_parser_precedence_and_structure(self):
        self.assertEqual(parse("(3 + 5) * 2"), ast.Program((ast.Block(ast.Product((
            ast.Sum((ast.Integer(3), ast.Integer(5))), ast.Integer(2)))),)))
        self.assertEqual(parse("3 + 5 * 2"), ast.Program((ast.Block(ast.Sum((
            ast.Integer(3), ast.Product((ast.Integer(5), ast.Integer(2)))))),)))

    def test_all_v01_operations_survive_score_round_trip(self):
        cases = {
            "(3 + 5) * 2": 16,
            "3 - 5": -2,
            "8 / 4 / 2": 1,
            "8 / (4 / 2)": 4,
            "3 / 2": Fraction(3, 2),
            "1 / 3 + 1 / 6": Fraction(1, 2),
            "-(3 + 5)": -8,
            "--3": 3,
            "3--5": 8,
            "(1 + 2) * (5 - 3)": 6,
            "0": 0,
            "5 * 0": 0,
            "0 / 5": 0,
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(execute(compile_expression(source)), expected)

    def test_random_expressions_match_fraction_arithmetic(self):
        generator = random.Random(42)

        def make(depth):
            if depth == 0:
                value = generator.randrange(0, 8)
                return str(value), Fraction(value)
            left, left_value = make(depth - 1)
            right, right_value = make(depth - 1)
            operator = generator.choice(("+", "-", "*", "/") if right_value else ("+", "-", "*"))
            expected = {"+": left_value + right_value, "-": left_value - right_value,
                        "*": left_value * right_value}.get(operator)
            if operator == "/":
                expected = left_value / right_value
            return f"({left} {operator} {right})", expected

        for _ in range(40):
            source, expected = make(3)
            with self.subTest(source=source):
                self.assertEqual(execute(compile_expression(source)), expected)

    def test_editing_visible_duration_changes_the_program(self):
        score = compile_expression("(3 + 5) * 2")
        part = score.parts[0]
        staff = part.staves[0]
        measure = staff.measures[0]
        voice = measure.voices[0]
        first = replace(voice.events[0], duration=Fraction(2, 4))
        changed_voice = replace(voice, events=(first,) + voice.events[1:])
        changed_measure = replace(measure, voices=(changed_voice,))
        changed_staff = replace(staff, measures=(changed_measure,))
        changed = replace(score, parts=(replace(part, staves=(changed_staff,) + part.staves[1:]),))
        self.assertEqual(execute(changed), 14)

    def test_division_by_zero_is_runtime_error(self):
        with self.assertRaisesRegex(DivisionByZero, "Division by zero"):
            execute(compile_expression("1 / (3 - 3)"))

    def test_invalid_text_is_rejected_with_a_position(self):
        for source in ("", "1+", "1.5", "1//2", "x", "print(3)", "+3"):
            with self.subTest(source=source), self.assertRaises(ParseError):
                parse(source)
        with self.assertRaisesRegex(ParseError, "line 2, column 2"):
            parse("1 +\n ?")


if __name__ == "__main__":
    unittest.main()

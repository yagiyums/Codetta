import unittest

from codetta.score_parser import parse_score
from codetta.semantic_analyzer import analyze
from codetta.semantics import CodettaError
from composer.projection import emit_python, parse_python
from conductor.compiler import compile_ast
from performer.evaluator import evaluate

try:
    import verovio  # noqa: F401
except ImportError:
    verovio = None


class ComposerProjectionTests(unittest.TestCase):
    def value(self, source: str):
        program = parse_python(source)
        score = compile_ast(program)
        return evaluate(analyze(parse_score(score)))

    def test_python_projection_round_trip_is_exact(self):
        source = "result = (7 - 2) / 5"
        program = parse_python(source)
        normalized = emit_python(parse_score(compile_ast(program)))
        self.assertIn("from fractions import Fraction", normalized)
        self.assertEqual(self.value(source), self.value(normalized))
        self.assertEqual(str(self.value(normalized)), "1")

    def test_comments_and_expression_form_are_accepted(self):
        self.assertEqual(str(self.value("# draft\n(3 + 5) * 2")), "16")

    def test_arbitrary_python_is_never_accepted(self):
        rejected = (
            "import os\nresult = 1",
            "result = open('secret')",
            "result = thing.attribute",
            "for item in items:\n    result = item",
        )
        for source in rejected:
            with self.subTest(source=source), self.assertRaises(CodettaError):
                parse_python(source)


@unittest.skipIf(verovio is None, "Verovio is not installed")
class ComposerApplicationTests(unittest.TestCase):
    def test_invalid_draft_does_not_replace_committed_score(self):
        from composer.server import ComposerApplication

        application = ComposerApplication.open()
        before = application.payload()
        with self.assertRaises(CodettaError):
            application.sync_python("result = (3 +", 1)
        self.assertEqual(application.payload()["json"], before["json"])
        self.assertEqual(application.payload()["result"], "16")

    def test_python_and_json_can_both_commit(self):
        from composer.server import ComposerApplication

        application = ComposerApplication.open()
        original = application.payload()["json"]
        changed = application.sync_python("result = 9 / 4", 1)
        self.assertEqual(changed["result"], "9/4")
        self.assertTrue(changed["relaid"])
        restored = application.sync_json(original, 2)
        self.assertEqual(restored["result"], "16")


if __name__ == "__main__":
    unittest.main()

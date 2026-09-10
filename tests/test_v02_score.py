import json
import unittest

from codetta.score_parser import parse_score
from codetta.semantic_analyzer import analyze
from codetta.serialization import dumps, loads
from composer.projection import emit_python, parse_python
from conductor.compiler import compile_ast
from performer.evaluator import evaluate
from rendering.musicxml import to_musicxml


PROCESS = """def process(values):
    total = 0
    for i in range(len(values)):
        x = values[i]
        if x > 3:
            total = total + x
    return total

values = [1, 2, 4, 6]
result = process(values)
"""


class V02ScoreTests(unittest.TestCase):
    def round_trip(self, source):
        score = compile_ast(parse_python(source), title="Codetta v0.2 E2E")
        restored = loads(dumps(score))
        program = parse_score(restored)
        return score, restored, program, evaluate(analyze(program))

    def test_process_survives_notation_serialization_and_returns_ten(self):
        score, restored, program, result = self.round_trip(PROCESS)
        self.assertEqual(result, 10)
        self.assertEqual(restored, score)
        self.assertEqual(evaluate(analyze(parse_python(emit_python(program)))), 10)
        self.assertTrue(score.phrases)
        self.assertTrue(score.repeats)
        self.assertTrue(score.voltas)
        self.assertTrue(score.sections)
        self.assertTrue(score.section_references)

        data = dumps(score).lower()
        for forbidden in ('"opcode"', '"operation"', '"meaning"'):
            self.assertNotIn(forbidden, data)
        parsed = json.loads(data)
        self.assertEqual(parsed["language_version"], "0.2")

        musicxml = to_musicxml(score, debug=True)
        self.assertIn('<repeat direction="forward"', musicxml)
        self.assertIn('<ending number="1" type="start"', musicxml)
        self.assertIn("<rehearsal", musicxml)
        self.assertIn("<cue", musicxml)

    def test_float_struct_field_and_while_survive_score(self):
        source = """point = {'height': 3.14, 'active': True}
height = point.height
n = 0
while n < 3:
    n = n + 1
if point.active:
    result = height + n
else:
    result = 0.0
"""
        score, _, program, result = self.round_trip(source)
        self.assertAlmostEqual(result, 6.14)
        repeat = score.repeats[0]
        self.assertTrue(repeat.test_at_end)
        condition_measure = next(
            measure.number
            for staff in score.parts[0].staves
            for measure in staff.measures
            for voice in measure.voices
            if voice.id == repeat.condition_voice_id and voice.events
        )
        canonical = score.parts[0].staves[0].measures[condition_measure - 1]
        self.assertEqual(repeat.end_measure, canonical.id)
        self.assertIn("while n < 3:", emit_python(program))
        self.assertNotIn("if n < 3:", emit_python(program))

    def test_pretest_while_can_execute_zero_times_after_score_round_trip(self):
        source = """n = 0
while n < 0:
    n = n + 1
result = n
"""
        score, _, program, result = self.round_trip(source)
        self.assertEqual(result, 0)
        self.assertTrue(score.repeats[0].test_at_end)
        self.assertTrue(score.voltas)
        self.assertEqual(emit_python(program), source)

    def test_array_of_struct_uses_horizontal_phrase_and_vertical_groups(self):
        source = """people = [
    {'age': 28, 'score': 95},
    {'age': 31, 'score': 88},
    {'age': 25, 'score': 91},
]
person = people[1]
result = person.score
"""
        score, _, _, result = self.round_trip(source)
        self.assertEqual(result, 88)
        self.assertEqual(len(score.phrases), 1)
        self.assertEqual(len(score.voice_groups), 3)


if __name__ == "__main__":
    unittest.main()

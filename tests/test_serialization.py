from dataclasses import replace
from fractions import Fraction
import json
import unittest

from codetta.score_model import Chord, Pitch
from codetta.score_parser import ScoreSyntaxError, parse_score
from codetta.serialization import SerializationError, dumps, loads
from conductor.compiler import compile_expression
from performer.evaluator import evaluate
from codetta.semantic_analyzer import analyze


class SerializationTests(unittest.TestCase):
    def test_codetta_round_trip_contains_notation_but_no_meaning(self):
        score = compile_expression("(3 + 5) * 2", title="Calculator")
        source = dumps(score)
        restored = loads(source)
        self.assertEqual(restored, score)
        self.assertEqual(evaluate(analyze(parse_score(restored))), 16)
        data = json.loads(source)
        self.assertEqual(data["format"], "codetta-score")
        self.assertIn('"pitch"', source)
        self.assertIn('"duration"', source)
        for forbidden in ('"meaning"', '"operation"', '"result"', '"integer"', '"multiply"'):
            self.assertNotIn(forbidden, source.lower())

    def test_rationals_are_reduced_and_exact(self):
        score = compile_expression("3")
        data = json.loads(dumps(score))
        duration = data["score"]["parts"][0]["staves"][0]["measures"][0]["voices"][0]["events"][0]["duration"]
        self.assertEqual(duration, {"n": 3, "d": 4})
        self.assertEqual(loads(dumps(score)).parts[0].staves[0].measures[0].voices[0].events[0].duration,
                         Fraction(3, 4))

    def test_unknown_fields_and_bad_references_are_rejected(self):
        data = json.loads(dumps(compile_expression("3 + 5")))
        data["score"]["meaning"] = "add"
        with self.assertRaisesRegex(SerializationError, "unknown meaning"):
            loads(json.dumps(data))
        data = json.loads(dumps(compile_expression("5")))
        data["score"]["spanners"][0]["end_anchor"] = "missing"
        with self.assertRaisesRegex(SerializationError, "missing event"):
            loads(json.dumps(data))
        data = json.loads(dumps(compile_expression("3")))
        data["score"]["metadata"]["result"] = "3"
        with self.assertRaisesRegex(SerializationError, "metadata supports only"):
            loads(json.dumps(data))

    def test_chords_are_preserved_but_not_executable_in_v01(self):
        score = compile_expression("3")
        part = score.parts[0]
        staff = part.staves[0]
        measure = staff.measures[0]
        voice = measure.voices[0]
        note = voice.events[0]
        chord = Chord(note.id, note.start, note.duration,
                      (note.pitch, Pitch.from_midi(note.pitch.midi + 4)))
        modified = replace(score, parts=(replace(part, staves=(replace(staff, measures=(replace(
            measure, voices=(replace(voice, events=(chord,)),)),)),)),))
        restored = loads(dumps(modified))
        self.assertIsInstance(restored.parts[0].staves[0].measures[0].voices[0].events[0], Chord)
        with self.assertRaisesRegex(ScoreSyntaxError, "no computational meaning"):
            parse_score(restored)


if __name__ == "__main__":
    unittest.main()

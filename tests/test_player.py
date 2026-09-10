from pathlib import Path
import tempfile
import unittest
import wave

from conductor.compiler import compile_expression
from composer.projection import parse_python
from conductor.compiler import compile_ast
from performer.evaluator import evaluate, evaluate_with_trace
from performer.player import SAMPLE_RATE, plan, write_wav
from codetta.score_parser import parse_score
from codetta.semantic_analyzer import analyze


class PlayerTests(unittest.TestCase):
    def test_voices_play_simultaneously_as_notated(self):
        score = compile_expression("(3 + 5) * 2")
        result = evaluate(analyze(parse_score(score)))
        performance = plan(score, result)
        self.assertEqual([(sound.start, sound.beats) for sound in performance.sounds],
                         [(0, 3), (0, 2), (3, 5)])
        self.assertEqual(performance.beats, 8)
        self.assertEqual(performance.result, 16)

    def test_wav_uses_score_duration_and_contains_audio(self):
        score = compile_expression("(3 + 5) * 2")
        performance = plan(score, evaluate(analyze(parse_score(score))))
        with tempfile.TemporaryDirectory() as folder:
            path = write_wav(performance, Path(folder) / "demo.wav", bpm=600)
            with wave.open(str(path), "rb") as audio:
                self.assertEqual(audio.getframerate(), SAMPLE_RATE)
                self.assertEqual(audio.getnframes(), round(8 * SAMPLE_RATE / 10))
                self.assertTrue(any(audio.readframes(audio.getnframes())))

    def test_v02_follows_function_loop_and_branch_execution_order(self):
        source = """def process(values):
    total = 0
    for i in range(len(values)):
        x = values[i]
        if x > 3:
            total = total + x
    return total

values = [1, 2, 4, 6]
result = process(values)
"""
        score = compile_ast(parse_python(source))
        evaluated = evaluate_with_trace(analyze(parse_score(score)))
        self.assertEqual([(item.kind, item.name, item.value) for item in evaluated.trace], [
            ("call", "process", None),
            ("loop", None, 4),
            ("branch", None, False),
            ("branch", None, False),
            ("branch", None, True),
            ("branch", None, True),
        ])
        linear = plan(score, evaluated.value)
        performed = plan(score, evaluated.value, trace=evaluated.trace)
        self.assertEqual(performed.result, 10)
        self.assertNotEqual(performed.beats, linear.beats)
        self.assertGreater(len(performed.sounds), len(linear.sounds))


if __name__ == "__main__":
    unittest.main()

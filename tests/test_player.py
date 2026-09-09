from pathlib import Path
import tempfile
import unittest
import wave

from conductor.compiler import compile_expression
from performer.evaluator import evaluate
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


if __name__ == "__main__":
    unittest.main()

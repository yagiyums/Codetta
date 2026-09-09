from fractions import Fraction
from pathlib import Path
import tempfile
import unittest
import wave

from codetta.semantics import CodettaError, DivisionByZero
from conductor.compiler import compile_expression
from performer.player import SAMPLE_RATE, plan, write_wav


class PlayerTests(unittest.TestCase):
    def test_control_plays_before_scaled_body(self):
        performance = plan(compile_expression("(3 + 5) * 2"))
        self.assertEqual([sound.beats for sound in performance.sounds], [2, 6, 10])
        self.assertEqual([sound.role for sound in performance.sounds], ["control", "body", "body"])
        self.assertEqual(performance.beats, 18)
        self.assertEqual(performance.result, 16)

    def test_negative_contribution_keeps_positive_duration(self):
        performance = plan(compile_expression("3 - 5"))
        self.assertEqual([sound.beats for sound in performance.sounds], [3, 5])
        self.assertEqual([sound.sign for sound in performance.sounds], [1, -1])
        self.assertEqual(performance.result, -2)

    def test_inverse_scale_and_negative_factor(self):
        performance = plan(compile_expression("3 / -2"))
        self.assertEqual([sound.beats for sound in performance.sounds], [2, Fraction(3, 2)])
        self.assertEqual([sound.sign for sound in performance.sounds], [-1, -1])
        self.assertEqual(performance.result, Fraction(-3, 2))

    def test_nested_scale_stretches_inner_control_and_body(self):
        performance = plan(compile_expression("(3 * 2) * 4"))
        self.assertEqual([sound.beats for sound in performance.sounds], [4, 8, 24])
        self.assertEqual(performance.result, 24)

    def test_zero_factor_skips_body_but_keeps_control(self):
        performance = plan(compile_expression("5 * (3 - 3)"))
        self.assertEqual([sound.beats for sound in performance.sounds], [3, 3])
        self.assertEqual(performance.result, 0)
        self.assertEqual(plan(compile_expression("0")).sounds, ())

    def test_invalid_body_is_not_hidden_by_zero_factor(self):
        with self.assertRaises(DivisionByZero):
            plan(compile_expression("(1 / 0) * 0"))

    def test_wav_has_expected_duration_and_nonzero_samples(self):
        performance = plan(compile_expression("1 / 3"))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sound.wav"
            write_wav(performance, path, bpm=600)
            with wave.open(str(path), "rb") as audio:
                self.assertEqual(audio.getnchannels(), 1)
                self.assertEqual(audio.getsampwidth(), 2)
                self.assertEqual(audio.getframerate(), SAMPLE_RATE)
                self.assertEqual(audio.getnframes(), round(Fraction(10, 3) * SAMPLE_RATE / 10))
                self.assertTrue(any(audio.readframes(audio.getnframes())))
            write_wav(performance, path, bpm=1200)
            with wave.open(str(path), "rb") as audio:
                self.assertEqual(audio.getnframes(), round(Fraction(10, 3) * SAMPLE_RATE / 20))
        self.assertEqual(performance.result, Fraction(1, 3))

    def test_zero_wav_is_valid_and_empty(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "zero.wav"
            write_wav(plan(compile_expression("0")), path)
            with wave.open(str(path), "rb") as audio:
                self.assertEqual(audio.getnframes(), 0)

    def test_audio_limits_do_not_limit_calculation(self):
        performance = plan(compile_expression("1000 * 1000"))
        self.assertEqual(performance.result, 1000000)
        with self.assertRaisesRegex(CodettaError, "exceeds"):
            write_wav(performance, "should-not-exist.wav")
        with self.assertRaisesRegex(CodettaError, "Tempo"):
            write_wav(performance, "should-not-exist.wav", bpm=0)


if __name__ == "__main__":
    unittest.main()

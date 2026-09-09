from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CommandLineTests(unittest.TestCase):
    def run_module(self, module, *args):
        return subprocess.run([sys.executable, "-m", module, *map(str, args)],
                              cwd=ROOT, capture_output=True, text=True, encoding="utf-8")

    def test_compile_and_perform_in_separate_processes(self):
        with tempfile.TemporaryDirectory() as folder:
            score = Path(folder) / "score.svg"
            source = Path(folder) / "expression.txt"
            source.write_text("(3 + 5) * 2", encoding="utf-8")
            compiled = self.run_module("conductor", "--input", source, "--format", "executable-svg", "-o", score)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            source.unlink()  # Performer must work without access to the input expression.
            performed = self.run_module("performer", score, "--no-play")
            self.assertEqual(performed.returncode, 0, performed.stderr)
            self.assertEqual(performed.stdout.strip(), "16")

    def test_invalid_source_does_not_create_a_score(self):
        with tempfile.TemporaryDirectory() as folder:
            score = Path(folder) / "score.svg"
            result = self.run_module("conductor", "1 +", "-o", score)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("column", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertFalse(score.exists())

    def test_runtime_error_is_reported_without_a_traceback(self):
        with tempfile.TemporaryDirectory() as folder:
            score = Path(folder) / "score.svg"
            compiled = self.run_module("conductor", "1 / (2 - 2)", "--format", "executable-svg", "-o", score)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            result = self.run_module("performer", score, "--no-play")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Division by zero", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()

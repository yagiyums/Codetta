from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CommandLineTests(unittest.TestCase):
    def run_module(self, module, *arguments):
        return subprocess.run([sys.executable, "-m", module, *map(str, arguments)], cwd=ROOT,
                              capture_output=True, text=True, encoding="utf-8")

    def test_compile_perform_and_export_in_separate_processes(self):
        with tempfile.TemporaryDirectory() as folder:
            score = Path(folder) / "program.codetta"
            xml = Path(folder) / "score.musicxml"
            source = Path(folder) / "expression.txt"
            source.write_text("(3 + 5) * 2", encoding="utf-8")
            compiled = self.run_module("conductor", "--input", source, "-o", score)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            source.unlink()
            performed = self.run_module("performer", score, "--no-play")
            self.assertEqual(performed.returncode, 0, performed.stderr)
            self.assertEqual(performed.stdout.strip(), "16")
            exported = self.run_module("conductor", "(3 + 5) * 2", "-o", xml)
            self.assertEqual(exported.returncode, 0, exported.stderr)
            self.assertIn("score-partwise", xml.read_text(encoding="utf-8"))

    def test_invalid_source_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as folder:
            score = Path(folder) / "program.codetta"
            result = self.run_module("conductor", "1 +", "-o", score)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("column", result.stderr)
            self.assertFalse(score.exists())

    def test_performer_rejects_old_executable_svg(self):
        result = self.run_module("performer", "legacy.codetta.svg", "--no-play")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must be a .codetta file", result.stderr)


if __name__ == "__main__":
    unittest.main()

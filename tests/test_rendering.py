import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

from codetta.semantics import CodettaError
from conductor.compiler import compile_expression
from rendering.renderer import (RenderOptions, read_musicxml, render_ir, render_musicxml,
                                to_html, write_rendered)

ROOT = Path(__file__).resolve().parents[1]
HAS_VEROVIO = importlib.util.find_spec("verovio") is not None


def classes(svg):
    return {value for element in ET.fromstring(svg).iter() for value in element.get("class", "").split()}


@unittest.skipUnless(HAS_VEROVIO, "Install requirements-rendering.txt to run engraving integration tests")
class RenderingTests(unittest.TestCase):
    def test_actual_renderer_emits_conventional_music_glyphs(self):
        rendered = render_ir(compile_expression("(3 + 5) * 2"))
        self.assertEqual(len(rendered.pages), 1)
        found = classes(rendered.pages[0])
        self.assertTrue({"staff", "clef", "meterSig", "note", "stem", "barLine", "tie", "slur", "rest", "bracketSpan"} <= found)
        self.assertNotIn("Span=", rendered.pages[0])
        self.assertNotIn("data-codetta", rendered.pages[0])

    def test_musicxml_fixture_supports_chords_voices_keys_and_accidentals(self):
        rendered = render_musicxml(read_musicxml(ROOT / "examples/notation/features.musicxml"))
        found = classes(rendered.pages[0])
        self.assertTrue({"chord", "layer", "keySig", "accid", "beam", "clef", "rest", "meterSig"} <= found)
        self.assertEqual(rendered.diagnostics, "")

    def test_debug_mode_is_separate_and_html_is_offline(self):
        program = compile_expression("(3 + 5) * 2")
        normal, debug = render_ir(program), render_ir(program, debug=True)
        self.assertNotIn("Span=", normal.pages[0])
        self.assertIn("Span=3", debug.pages[0])
        html = to_html(normal, debug_score=debug)
        self.assertIn('id="debug" type="checkbox">', html)
        self.assertIn('.debug-score { display: none; }', html)
        self.assertNotIn('<script src=', html)
        self.assertNotIn('<link ', html)
        self.assertIn('window.print()', html)
        self.assertIn('xlink:href="#normal-p1-', html)
        self.assertIn('xlink:href="#debug-p1-', html)
        self.assertNotIn('ns1:href', html)
        original_root_id = ET.fromstring(normal.pages[0]).get("id")
        self.assertIn(f"#normal-p1-{original_root_id} ", html)
        self.assertNotIn(f"#{original_root_id} ", html)

    def test_multipage_svg_output_does_not_drop_pages(self):
        program = compile_expression(" + ".join(["3"] * 25))
        rendered = render_ir(program, options=RenderOptions(900, 800))
        self.assertGreater(len(rendered.pages), 1)
        with tempfile.TemporaryDirectory() as folder:
            paths = write_rendered(rendered, Path(folder) / "score.svg")
            self.assertEqual(len(paths), len(rendered.pages))
            self.assertTrue(all(p.exists() for p in paths))
            self.assertEqual(paths[1].name, "score-2.svg")
            html = to_html(rendered)
            self.assertEqual(html.count('<section class="page"'), len(rendered.pages))

    def test_ir_display_does_not_import_performer(self):
        script = ("import sys; from conductor.compiler import compile_expression; "
                  "from rendering.renderer import render_ir; render_ir(compile_expression('1 / 0')); "
                  "assert not any(m == 'performer' or m.startswith('performer.') for m in sys.modules)")
        result = subprocess.run([sys.executable, "-c", script], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_cli_svg_defaults_to_staff_notation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "score.svg"
            result = subprocess.run([sys.executable, "-m", "conductor", "(3 + 5) * 2", "-o", str(path)],
                                    cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("clef", classes(path.read_text(encoding="utf-8")))
            self.assertNotIn("data-codetta", path.read_text(encoding="utf-8"))


class MusicXMLInputTests(unittest.TestCase):
    def test_compressed_musicxml(self):
        fixture = (ROOT / "examples/notation/features.musicxml").read_bytes()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "score.mxl"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("META-INF/container.xml", '<container><rootfiles><rootfile full-path="music/score.xml"/></rootfiles></container>')
                archive.writestr("music/score.xml", fixture)
            self.assertIn("score-partwise", read_musicxml(path))

    def test_invalid_documents_fail_before_renderer(self):
        for xml in ("<svg/>", "<score-partwise/>", "not XML", '<!DOCTYPE x [<!ENTITY a "x">]><score-partwise/>'):
            with self.subTest(xml=xml), self.assertRaises(CodettaError):
                render_musicxml(xml)


if __name__ == "__main__":
    unittest.main()

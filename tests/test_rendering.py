import importlib.util
import unittest
import xml.etree.ElementTree as ET

from conductor.compiler import compile_expression
from rendering.musicxml import DIVISIONS, to_musicxml
from rendering.renderer import render_score, to_html

HAS_VEROVIO = importlib.util.find_spec("verovio") is not None


class MusicXMLTests(unittest.TestCase):
    def test_score_model_exports_conventional_notation(self):
        xml = to_musicxml(compile_expression("(3 + 5) * 2"))
        root = ET.fromstring(xml)
        self.assertEqual(root.tag, "score-partwise")
        self.assertTrue(root.findall(".//note"))
        self.assertTrue(root.findall(".//rest"))
        self.assertTrue(root.findall(".//tie"))
        self.assertTrue(root.findall(".//slur"))
        self.assertTrue(root.findall(".//bracket"))
        self.assertEqual(root.findtext(".//divisions"), str(DIVISIONS))
        self.assertEqual(root.findtext(".//bar-style"), "light-heavy")
        self.assertEqual(root.findall(".//words"), [])
        for forbidden in ("data-codetta", "Integer", "Product", "result=16"):
            self.assertNotIn(forbidden, xml)

    def test_debug_information_is_a_separate_export(self):
        score = compile_expression("(3 + 5) * 2")
        self.assertNotIn("Product", to_musicxml(score))
        self.assertIn("Product", to_musicxml(score, debug=True))

    def test_rendering_does_not_evaluate_invalid_runtime_arithmetic(self):
        xml = to_musicxml(compile_expression("1 / (3 - 3)"))
        self.assertIn("score-partwise", xml)
        self.assertNotIn("Division by zero", xml)


@unittest.skipUnless(HAS_VEROVIO, "Install requirements-rendering.txt")
class VerovioTests(unittest.TestCase):
    def test_renderer_outputs_normal_staff_svg_and_offline_html(self):
        score = compile_expression("(3 + 5) * 2")
        normal = render_score(score)
        debug = render_score(score, debug=True)
        classes = {name for element in ET.fromstring(normal.pages[0]).iter()
                   for name in element.get("class", "").split()}
        self.assertTrue({"staff", "clef", "meterSig", "note", "stem", "barLine",
                         "tie", "slur", "rest", "bracketSpan"} <= classes)
        html = to_html(normal, debug_score=debug)
        self.assertIn("Debug mode", html)
        self.assertIn("window.print()", html)
        self.assertNotIn("<script src=", html)


if __name__ == "__main__":
    unittest.main()

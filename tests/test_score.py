from copy import deepcopy
import unittest
import xml.etree.ElementTree as ET

from codetta import ir
from codetta.notation import SVG_NS, VERSION, add_glyphs, element, tag
from codetta.semantics import CodettaError
from conductor.compiler import compile_expression
from conductor.score_writer import to_svg
from performer.evaluator import evaluate
from performer.score_reader import ScoreError, from_svg


def musical(root, kind):
    return next(item for item in root.iter() if item.get("data-codetta") == kind)


class ScoreTests(unittest.TestCase):
    def test_reader_accepts_independently_constructed_score(self):
        root = ET.Element(tag("svg"), {"data-codetta-version": VERSION})
        add_glyphs(root)
        output = element(root, "g", data_codetta="emit")
        span = element(output, "g", data_codetta="span")
        note = element(span, "g", data_codetta="note", data_pitch=60)
        element(note, "use", href="#note-dotted-half")
        self.assertEqual(evaluate(from_svg(ET.tostring(root, encoding="unicode"))), 3)

    def test_editing_visible_note_glyph_changes_calculation(self):
        root = ET.fromstring(to_svg(compile_expression("3 + 5")))
        note = musical(root, "note")
        note.find(tag("use")).set("href", "#note-half")
        # 3 becomes 2: a reader relying on a hidden literal or result would return 8.
        self.assertEqual(evaluate(from_svg(ET.tostring(root, encoding="unicode"))), 7)

    def test_pitch_is_preserved_but_never_changes_the_value(self):
        for pitch in (0, 48, 60, 61, 72, 127):
            program = ir.Emit(ir.Span(5, pitch))
            restored = from_svg(to_svg(program))
            self.assertEqual(restored, program)
            self.assertEqual(evaluate(restored), 5)

    def test_decorative_text_does_not_override_music(self):
        root = ET.fromstring(to_svg(compile_expression("3 + 5")))
        for text in root.iter(tag("text")):
            text.text = "999"
        self.assertEqual(evaluate(from_svg(ET.tostring(root, encoding="unicode"))), 8)

    def test_malformed_structures_are_rejected(self):
        base = ET.fromstring(to_svg(compile_expression("(3 + 5) * 2")))

        def check(mutator):
            root = deepcopy(base)
            mutator(root)
            with self.assertRaises(ScoreError):
                from_svg(ET.tostring(root, encoding="unicode"))

        check(lambda root: root.set("data-codetta-version", "9.9"))
        check(lambda root: musical(root, "voice").set("data-role", "unknown"))
        check(lambda root: musical(root, "scale").append(deepcopy(musical(root, "voice"))))
        check(lambda root: musical(root, "note").find(tag("use")).set("href", "#note-eighth"))
        check(lambda root: musical(root, "note").set("data-pitch", "200"))
        check(lambda root: musical(root, "span").set("data-codetta", "rest"))
        check(lambda root: root.append(deepcopy(musical(root, "emit"))))
        check(lambda root: musical(root, "span").set("data-codetta", "emit"))
        check(lambda root: root.remove(root.find(tag("defs"))))

    def test_missing_tie_is_rejected(self):
        root = ET.fromstring(to_svg(compile_expression("5")))
        musical(root, "span").remove(musical(root, "tie"))
        with self.assertRaises(ScoreError):
            from_svg(ET.tostring(root, encoding="unicode"))

    def test_zero_must_not_have_notes(self):
        root = ET.fromstring(to_svg(compile_expression("0")))
        element(musical(root, "zero"), "g", data_codetta="note")
        with self.assertRaises(ScoreError):
            from_svg(ET.tostring(root, encoding="unicode"))

    def test_bad_xml_and_external_entities_are_rejected(self):
        for svg in ("<svg", "<svg />", '<!DOCTYPE svg [<!ENTITY x SYSTEM "file:///secret">]><svg/>'):
            with self.subTest(svg=svg), self.assertRaises(ScoreError):
                from_svg(svg)

    def test_large_literal_has_an_explicit_render_limit(self):
        with self.assertRaisesRegex(CodettaError, "note glyphs"):
            to_svg(compile_expression("100000000000000000000000"))


if __name__ == "__main__":
    unittest.main()

from fractions import Fraction
from pathlib import Path
import os
import unittest
import xml.etree.ElementTree as ET

from codetta import ir
from codetta.semantics import CodettaError
from conductor.compiler import compile_expression
from rendering.model import DisplayNote, DisplayScore, NotationOptions, project
from rendering.musicxml import DIVISIONS, score_to_musicxml, to_musicxml


class MusicXMLTests(unittest.TestCase):
    def assert_balanced(self, xml):
        root = ET.fromstring(xml)
        capacity = 0
        for measure in root.findall("part/measure"):
            time = measure.find("attributes/time")
            if time is not None:
                capacity = Fraction(int(time.findtext("beats")) * 4, int(time.findtext("beat-type"))) * DIVISIONS
            cursor, lanes = 0, {}
            for item in measure:
                if item.tag == "backup":
                    self.assertEqual(cursor, capacity)
                    cursor -= int(item.findtext("duration"))
                    self.assertEqual(cursor, 0)
                elif item.tag == "note" and item.find("chord") is None:
                    length = int(item.findtext("duration"))
                    cursor += length
                    lane = (item.findtext("staff"), item.findtext("voice"))
                    lanes[lane] = lanes.get(lane, 0) + length
            self.assertEqual(cursor, capacity)
            self.assertTrue(all(length == capacity for length in lanes.values()))

    def test_projection_preserves_written_values_and_input(self):
        program = compile_expression("(3 + 5) * 2")
        snapshot = repr(program)
        score = project(program)
        self.assertEqual([note.duration for note in score.notes], [3, 5, 2])
        self.assertEqual([note.staff for note in score.notes], [1, 1, 2])
        self.assertEqual(score.duration, 8)
        self.assertEqual(repr(program), snapshot)

    def test_measure_splitting_ties_and_padding(self):
        xml = to_musicxml(compile_expression("(3 + 5) * 2"))
        self.assert_balanced(xml)
        root = ET.fromstring(xml)
        notes = root.findall("part/measure/note")
        main = [n for n in notes if n.findtext("staff") == "1"]
        self.assertEqual([int(n.findtext("duration")) / DIVISIONS for n in main], [3, 1, 4])
        self.assertEqual(len(root.findall(".//tie[@type='start']")), 1)
        self.assertEqual(len(root.findall(".//tie[@type='stop']")), 1)
        self.assertTrue(root.findall(".//rest"))
        self.assertEqual(root.findtext(".//bar-style"), "light-heavy")

    def test_nondefault_time_signatures_have_complete_measures(self):
        for beats, denominator in ((3, 4), (6, 8), (3, 8), (5, 16), (1, 32)):
            with self.subTest(meter=(beats, denominator)):
                self.assert_balanced(to_musicxml(compile_expression("(3 + 5) * (2 - 1)"),
                                                NotationOptions(beats, denominator)))

    def test_rendering_does_not_evaluate_division_by_zero(self):
        xml = to_musicxml(compile_expression("1 / (3 - 3)"))
        self.assert_balanced(xml)
        root = ET.fromstring(xml)
        self.assertTrue(root.findall(".//bracket[@line-type='dashed']"))
        self.assertTrue(root.findall(".//direction[@placement='below']"))

    def test_normal_output_has_no_debug_labels(self):
        xml = to_musicxml(compile_expression("(3 + 5) * 2"))
        self.assertEqual(ET.fromstring(xml).findall(".//words"), [])
        for marker in ("Scale", "Sequence", "Span=", "output/body", "VALUE", "data-codetta"):
            self.assertNotIn(marker, xml)
        debug = to_musicxml(compile_expression("(3 + 5) * 2"), debug=True)
        self.assertIn("Span=3", debug)
        self.assertIn("Scale", debug)

    def test_key_signature_spelling_and_cancellation(self):
        score = DisplayScore((DisplayNote(Fraction(0), Fraction(1), (66,)),
                              DisplayNote(Fraction(1), Fraction(1), (65,)),
                              DisplayNote(Fraction(2), Fraction(1), (65,)),
                              DisplayNote(Fraction(3), Fraction(1), (66,))), (), 1, Fraction(4), NotationOptions(fifths=1))
        root = ET.fromstring(score_to_musicxml(score))
        self.assertEqual([n.findtext("accidental") for n in root.findall(".//note")],
                         [None, "natural", None, "sharp"])
        flat = ET.fromstring(to_musicxml(ir.Emit(ir.Span(1, 61)), NotationOptions(fifths=-2)))
        self.assertEqual(flat.findtext(".//pitch/step"), "D")
        self.assertEqual(flat.findtext(".//pitch/alter"), "-1")

    def test_chords_and_two_voices_in_display_model(self):
        score = DisplayScore((DisplayNote(Fraction(0), Fraction(4), (60, 64, 67)),
                              DisplayNote(Fraction(0), Fraction(2), (48,), voice=2),
                              DisplayNote(Fraction(2), Fraction(2), (), voice=2)),
                             (), 1, Fraction(4), NotationOptions())
        xml = score_to_musicxml(score)
        self.assert_balanced(xml)
        root = ET.fromstring(xml)
        self.assertEqual(len(root.findall(".//chord")), 2)
        self.assertEqual({n.findtext("voice") for n in root.findall(".//note")}, {"1", "2"})

    def test_accidentals_follow_time_across_voices(self):
        score = DisplayScore((DisplayNote(Fraction(0), Fraction(2), (66,)),
                              DisplayNote(Fraction(2), Fraction(2), (65,)),
                              DisplayNote(Fraction(1), Fraction(1), (65,), voice=2)),
                             (), 1, Fraction(4), NotationOptions())
        root = ET.fromstring(score_to_musicxml(score))
        voice2 = [n for n in root.findall(".//note") if n.findtext("voice") == "2" and n.find("pitch") is not None]
        self.assertEqual(voice2[0].findtext("accidental"), "natural")

    def test_zero_has_no_computational_note(self):
        score = project(compile_expression("0"))
        self.assertEqual(score.notes, ())
        root = ET.fromstring(score_to_musicxml(score))
        self.assertIsNotNone(root.find(".//coda"))
        self.assertEqual(root.findall(".//pitch"), [])

    def test_invalid_options_and_overlapping_notes_are_rejected(self):
        for kwargs in ({"beats": 0}, {"beat_type": 3}, {"fifths": 8}, {"clef": "alto"}):
            with self.assertRaises(CodettaError):
                NotationOptions(**kwargs)
        score = DisplayScore((DisplayNote(Fraction(0), Fraction(3), (60,)),
                              DisplayNote(Fraction(2), Fraction(2), (60,))),
                             (), 1, Fraction(4), NotationOptions())
        with self.assertRaisesRegex(CodettaError, "overlap"):
            score_to_musicxml(score)

    @unittest.skipUnless(os.environ.get("CODETTA_MUSICXML_SCHEMA"), "Set CODETTA_MUSICXML_SCHEMA to the official MusicXML 4.0 schema directory")
    def test_official_musicxml_schema(self):
        from lxml import etree

        folder = Path(os.environ["CODETTA_MUSICXML_SCHEMA"])

        class LocalSchemas(etree.Resolver):
            def resolve(self, url, public_id, context):
                return self.resolve_filename(str(folder / url.rsplit("/", 1)[-1]), context)

        parser = etree.XMLParser(no_network=True, resolve_entities=False)
        parser.resolvers.add(LocalSchemas())
        schema = etree.XMLSchema(etree.parse(str(folder / "musicxml.xsd"), parser))
        for expression in ("(3 + 5) * 2", "1 / (3 - 3)", "0", "-5", "(2 * 3) / (1 + 1)"):
            for debug in (False, True):
                for options in (NotationOptions(), NotationOptions(3, 8, -2, "bass")):
                    with self.subTest(expression=expression, debug=debug, options=options):
                        xml = to_musicxml(compile_expression(expression), options, debug=debug)
                        schema.assertValid(etree.fromstring(xml.encode("utf-8")))
        fixture = Path(__file__).resolve().parents[1] / "examples/notation/features.musicxml"
        schema.assertValid(etree.parse(str(fixture)))


if __name__ == "__main__":
    unittest.main()

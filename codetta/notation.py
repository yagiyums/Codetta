"""Shared SVG vocabulary. Musical glyph references carry note durations."""

import xml.etree.ElementTree as ET

from codetta.semantics import NOTE_BEATS

SVG_NS = "http://www.w3.org/2000/svg"
VERSION = "0.1"
GLYPH_BEATS = {f"note-{name}": beats for name, beats in NOTE_BEATS.items()}


def tag(name: str) -> str:
    return f"{{{SVG_NS}}}{name}"


def element(parent: ET.Element, name: str, **attributes: object) -> ET.Element:
    return ET.SubElement(parent, tag(name), {key.replace("_", "-"): str(value)
                                           for key, value in attributes.items()})


def add_glyphs(root: ET.Element) -> None:
    defs = element(root, "defs")
    for name in GLYPH_BEATS:
        group = element(defs, "g", id=name)
        element(group, "ellipse", cx=0, cy=0, rx=7, ry=4.5,
                transform="rotate(-20)", fill="currentColor" if name == "note-quarter" else "white",
                stroke="currentColor", stroke_width=2)
        if name != "note-whole":
            element(group, "line", x1=6, x2=6, y1=-2, y2=-32,
                    stroke="currentColor", stroke_width=2)
        if name == "note-dotted-half":
            element(group, "circle", cx=14, cy=-2, r=2.2, fill="currentColor")


def pitch_position(pitch: int) -> tuple[int, bool, str]:
    """Diatonic steps above C4, sharp accidental, and visible pitch name."""
    octave, semitone = divmod(pitch, 12)
    steps = (0, 0, 1, 1, 2, 3, 3, 4, 4, 5, 5, 6)
    names = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
    return (octave - 5) * 7 + steps[semitone], "#" in names[semitone], f"{names[semitone]}{octave - 1}"

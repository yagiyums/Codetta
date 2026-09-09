"""Render IR as a visible, machine-readable Codetta SVG score.

No source string, AST dump, precomputed value, or numeric Span value is embedded.
Span values are reconstructed from the displayed note glyph references and ties.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ET

from codetta import ir
from codetta.notation import SVG_NS, VERSION, add_glyphs, element, pitch_position, tag
from codetta.semantics import CodettaError

ET.register_namespace("", SVG_NS)
MAX_NOTES = 4096


@dataclass
class _Box:
    node: ir.Phrase | ir.Emit
    width: int
    height: int
    children: tuple[_Box, ...] = ()
    notes: tuple[str, ...] = ()


def _layout(node: ir.Phrase | ir.Emit, remaining: list[int]) -> _Box:
    if isinstance(node, ir.Span):
        count, remainder = divmod(node.beats, 4)
        remaining[0] -= count + bool(remainder)
        if remaining[0] < 0:
            raise CodettaError(f"Score exceeds the v0.1 limit of {MAX_NOTES} note glyphs")
        tail = {0: (), 1: ("quarter",), 2: ("half",), 3: ("dotted-half",)}[remainder]
        notes = ("whole",) * count + tail
        steps, _, _ = pitch_position(node.pitch)
        shift = max(0, 65 - (112 - steps * 5))
        height = max(160, 152 - steps * 5 + shift, 147 + shift)
        return _Box(node, max(150, 60 + 56 * len(notes)), height, notes=notes)
    if isinstance(node, ir.Zero):
        return _Box(node, 150, 160)
    if isinstance(node, (ir.Emit, ir.Invert)):
        child = _layout(node.body, remaining)
        return _Box(node, child.width + 40, child.height + 66, (child,))
    if isinstance(node, ir.Sequence):
        children = tuple(_layout(child, remaining) for child in node.children)
        width = sum(child.width for child in children) + 28 * (len(children) - 1) + 32
        return _Box(node, width, max(child.height for child in children) + 58, children)
    if isinstance(node, (ir.Scale, ir.Unscale)):
        body, factor = _layout(node.body, remaining), _layout(node.factor, remaining)
        return _Box(node, max(body.width, factor.width) + 110,
                    body.height + factor.height + 84, (body, factor))
    raise TypeError(f"Unsupported IR node: {type(node).__name__}")


def _text(parent: ET.Element, x: int, y: int, text: str, size: int = 12, **attrs: object) -> None:
    element(parent, "text", x=x, y=y, font_size=size, **attrs).text = text


def _draw(box: _Box, parent: ET.Element, x: int, y: int) -> None:
    node = box.node
    kind = type(node).__name__.lower()
    group = element(parent, "g", data_codetta=kind, transform=f"translate({x},{y})")
    color = "#a45636" if isinstance(node, ir.Invert) else "#335f72"
    element(group, "rect", x=0, y=0, width=box.width, height=box.height,
            rx=8, fill="#ffffff", stroke=color, stroke_width=1.5)
    labels = {"span": "VALUE", "zero": "ZERO", "sequence": "PHRASE / consecutive",
              "invert": "INVERT / negative contribution", "scale": "SCALE / multiply",
              "unscale": "INVERSE SCALE / divide", "emit": "OUTPUT / final cadence"}
    _text(group, 12, 22, labels[kind], fill=color, font_weight="bold")

    if isinstance(node, ir.Span):
        steps, sharp, pitch_name = pitch_position(node.pitch)
        # Shift the complete staff for high notes, retaining all five staff lines.
        shift = max(0, 65 - (112 - steps * 5))
        note_y = 112 - steps * 5 + shift
        staff_bottom = 102 + shift
        for offset in range(5):
            staff_y = staff_bottom - offset * 10
            element(group, "line", x1=10, x2=box.width - 10, y1=staff_y, y2=staff_y,
                    stroke="#d2dadd", stroke_width=1)
        _text(group, box.width - 38, 22, pitch_name, 11, fill="#64747a")
        for i, note_type in enumerate(box.notes):
            note_x = 32 + i * 56
            if i:
                element(group, "path", data_codetta="tie",
                        d=f"M {note_x - 50} {note_y + 12} Q {note_x - 28} {note_y + 28} {note_x - 6} {note_y + 12}",
                        fill="none", stroke="#335f72", stroke_width=1.5)
            note = element(group, "g", data_codetta="note", data_pitch=node.pitch)
            ledger_lines = list(range(staff_bottom + 10, note_y + 1, 10))
            ledger_lines += list(range(staff_bottom - 50, note_y - 1, -10))
            for ledger_y in ledger_lines:
                element(note, "line", x1=note_x - 11, x2=note_x + 11,
                        y1=ledger_y, y2=ledger_y, stroke="#83969d")
            if sharp:
                _text(note, note_x - 19, note_y + 4, "#", 15)
            element(note, "use", href=f"#note-{note_type}", x=note_x, y=note_y)
        _text(group, 12, box.height - 15, "1 quarter note = 1 unit", 10, fill="#64747a")
    elif isinstance(node, ir.Zero):
        _text(group, 61, 94, "0", 38, fill="#335f72")
        _text(group, 22, 137, "no duration", 11, fill="#64747a")
    elif isinstance(node, ir.Sequence):
        child_x = 16
        for i, child in enumerate(box.children):
            if i:
                _text(group, child_x - 22, 40 + child.height // 2, "→", 19, fill="#64747a")
            _draw(child, group, child_x, 40)
            child_x += child.width + 28
    elif isinstance(node, (ir.Scale, ir.Unscale)):
        child_y = 40
        for role, child in zip(("body", "control"), box.children):
            voice = element(group, "g", data_codetta="voice", data_role=role)
            _text(voice, 12, child_y + 22, role.upper(), 11, fill=color)
            _draw(child, voice, 90, child_y)
            child_y += child.height + 24
    else:
        _draw(box.children[0], group, 16, 40)
        if isinstance(node, ir.Emit):
            for offset, width in ((12, 1.5), (6, 4)):
                element(group, "line", x1=box.width - offset, x2=box.width - offset,
                        y1=40, y2=box.height - 14, stroke=color, stroke_width=width)


def to_svg(program: ir.Emit) -> str:
    if not isinstance(program, ir.Emit):
        raise CodettaError("A score must have one top-level Emit")
    try:
        box = _layout(program, [MAX_NOTES])
        width = max(640, box.width + 64)
        root = ET.Element(tag("svg"), {"version": "1.1", "data-codetta-version": VERSION,
                                      "viewBox": f"0 0 {width} {box.height + 152}",
                                      "width": str(width), "height": str(box.height + 152),
                                      "font-family": "Segoe UI, Arial, sans-serif", "color": "#243c47"})
        add_glyphs(root)
        element(root, "rect", width="100%", height="100%", fill="#f5f2e9")
        _text(root, 32, 38, "CODETTA", 25, font_weight="bold", fill="#243c47")
        _text(root, 32, 62, "v0.1 / executable score / quarter note = 1", 12, fill="#64747a")
        _draw(box, root, 32, 82)
        _text(root, 32, box.height + 116,
              "Read left to right. Control voices play first; their value stretches the body.",
              11, fill="#64747a")
        ET.indent(root)
        return ET.tostring(root, encoding="unicode", xml_declaration=True)
    except RecursionError as exc:
        raise CodettaError("Score nesting is too deep to render") from exc


def write_score(program: ir.Emit, path: str | Path) -> Path:
    destination = Path(path)
    svg = to_svg(program)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(svg, encoding="utf-8")
    return destination

"""Read the documented Codetta SVG subset, independently of Conductor."""

from pathlib import Path
import xml.etree.ElementTree as ET

from codetta import ir
from codetta.notation import GLYPH_BEATS, VERSION, add_glyphs, tag
from codetta.semantics import CodettaError


class ScoreError(CodettaError):
    pass


def _children(group: ET.Element) -> list[ET.Element]:
    """Only immediate musical children count; nested enclosures own their contents."""
    return [child for child in group if "data-codetta" in child.attrib]


def _read(group: ET.Element, location: str) -> ir.Phrase | ir.Emit:
    kind = group.get("data-codetta")
    if group.tag != tag("g"):
        raise ScoreError(f"Expected a musical group at {location}")
    children = _children(group)
    if kind == "span":
        notes = [child for child in children if child.get("data-codetta") == "note"]
        ties = [child for child in children if child.get("data-codetta") == "tie"]
        if not notes or len(ties) != len(notes) - 1 or len(children) != len(notes) + len(ties):
            raise ScoreError(f"A value needs notes joined by ties at {location}")
        if any(child.get("data-codetta") != ("note" if i % 2 == 0 else "tie")
               for i, child in enumerate(children)):
            raise ScoreError(f"Notes and ties must alternate at {location}")
        beats, pitches = 0, set()
        for note in notes:
            if note.tag != tag("g") or _children(note):
                raise ScoreError(f"Invalid note at {location}")
            uses = note.findall(tag("use"))
            if len(uses) != 1 or uses[0].get("href", "")[1:] not in GLYPH_BEATS:
                raise ScoreError(f"Unknown or missing note glyph at {location}")
            href = uses[0].get("href", "")
            if not href.startswith("#"):
                raise ScoreError(f"Only local note glyphs are supported at {location}")
            beats += GLYPH_BEATS[href[1:]]
            try:
                pitch = int(note.attrib["data-pitch"])
            except (KeyError, ValueError) as exc:
                raise ScoreError(f"Missing or invalid pitch at {location}") from exc
            if not 0 <= pitch <= 127:
                raise ScoreError(f"Pitch out of range at {location}")
            pitches.add(pitch)
        if len(pitches) != 1 or any(tie.tag != tag("path") for tie in ties):
            raise ScoreError(f"A tied value must sustain one pitch at {location}")
        return ir.Span(beats, pitches.pop())
    if kind == "zero":
        if children:
            raise ScoreError(f"Zero must not contain a phrase at {location}")
        return ir.Zero()
    if kind in ("emit", "invert"):
        if len(children) != 1:
            raise ScoreError(f"{kind} needs exactly one phrase at {location}")
        child = _phrase(children[0], location + "/" + kind)
        return ir.Emit(child) if kind == "emit" else ir.Invert(child)
    if kind == "sequence":
        if len(children) < 2:
            raise ScoreError(f"A sequence needs at least two phrases at {location}")
        return ir.Sequence(tuple(_phrase(child, f"{location}/phrase[{i}]")
                                 for i, child in enumerate(children, 1)))
    if kind in ("scale", "unscale"):
        voices: dict[str, ir.Phrase] = {}
        for child in children:
            role = child.get("data-role", "")
            contents = _children(child)
            if (child.tag != tag("g") or child.get("data-codetta") != "voice"
                    or role not in ("body", "control") or role in voices or len(contents) != 1):
                raise ScoreError(f"Invalid or duplicate voice at {location}")
            voices[role] = _phrase(contents[0], location + "/" + role)
        if set(voices) != {"body", "control"}:
            raise ScoreError(f"Scale needs a body and a control voice at {location}")
        constructor = ir.Scale if kind == "scale" else ir.Unscale
        return constructor(voices["body"], voices["control"])
    raise ScoreError(f"Unknown musical structure {kind!r} at {location}")


def _phrase(group: ET.Element, location: str) -> ir.Phrase:
    node = _read(group, location)
    if isinstance(node, ir.Emit):
        raise ScoreError(f"Output is only allowed at the score root, at {location}")
    return node


def _glyph_signature(element: ET.Element) -> tuple:
    return (element.tag, sorted(element.attrib.items()),
            tuple(_glyph_signature(child) for child in element))


def from_svg(svg: str) -> ir.Emit:
    if "<!DOCTYPE" in svg.upper() or "<!ENTITY" in svg.upper():
        raise ScoreError("Document type declarations and entities are not supported")
    try:
        root = ET.fromstring(svg)
        if root.tag != tag("svg") or root.get("data-codetta-version") != VERSION:
            raise ScoreError("Expected a Codetta v0.1 SVG score")
        # Note names must continue to refer to the actual v0.1 visible glyphs.
        expected = ET.Element(tag("svg"))
        add_glyphs(expected)
        defs = root.findall(tag("defs"))
        if len(defs) != 1 or _glyph_signature(defs[0]) != _glyph_signature(expected[0]):
            raise ScoreError("The score's note glyph definitions are missing or modified")
        groups = _children(root)
        if len(groups) != 1 or groups[0].get("data-codetta") != "emit":
            raise ScoreError("A score needs exactly one output enclosure")
        # Reject musical elements hidden inside non-musical wrappers.
        for parent in root.iter():
            if parent is not root and "data-codetta" not in parent.attrib and _children(parent):
                raise ScoreError("Musical elements must belong directly to a musical enclosure")
        result = _read(groups[0], "score")
        assert isinstance(result, ir.Emit)
        return result
    except ET.ParseError as exc:
        raise ScoreError(f"Invalid SVG/XML: {exc}") from exc
    except RecursionError as exc:
        raise ScoreError("Score nesting is too deep") from exc


def read_score(path: str | Path) -> ir.Emit:
    return from_svg(Path(path).read_text(encoding="utf-8-sig"))

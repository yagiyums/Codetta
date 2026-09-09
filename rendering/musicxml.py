"""Export display notation as standard, uncompressed MusicXML 4.0."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from math import ceil
from pathlib import Path
import xml.etree.ElementTree as ET

from codetta import ir
from codetta.semantics import CodettaError
from rendering.model import DisplayNote, DisplayScore, NotationOptions, project

DIVISIONS = 8
MAX_MEASURES = 1024
DURATIONS = ((Fraction(4), "whole", False), (Fraction(3), "half", True),
             (Fraction(2), "half", False), (Fraction(3, 2), "quarter", True),
             (Fraction(1), "quarter", False), (Fraction(3, 4), "eighth", True),
             (Fraction(1, 2), "eighth", False), (Fraction(3, 8), "16th", True),
             (Fraction(1, 4), "16th", False), (Fraction(1, 8), "32nd", False))


def _el(parent: ET.Element, tag: str, value: object | None = None, **attrs: object) -> ET.Element:
    child = ET.SubElement(parent, tag, {k.replace("_", "-"): str(v) for k, v in attrs.items()})
    if value is not None:
        child.text = str(value)
    return child


def _ticks(beats: Fraction) -> int:
    ticks = beats * DIVISIONS
    if ticks.denominator != 1:
        raise CodettaError("IR notation export supports durations in multiples of 1/8 quarter note")
    return ticks.numerator


@dataclass(frozen=True)
class _Piece:
    event: DisplayNote
    start: Fraction
    duration: Fraction
    note_type: str
    dotted: bool
    measure: int
    identifier: str


def _pieces(score: DisplayScore, measures: int) -> list[_Piece]:
    capacity = score.options.measure_beats
    lanes = {(note.staff, note.voice) for note in score.notes}
    lanes.update((staff, 1) for staff in range(1, score.staves + 1))
    result: list[_Piece] = []
    for staff, voice in sorted(lanes):
        events = sorted((n for n in score.notes if (n.staff, n.voice) == (staff, voice)),
                        key=lambda n: n.start)
        previous_end = Fraction(0)
        for event in events:
            if event.duration <= 0 or event.start < previous_end:
                raise CodettaError("Notes in one voice must have positive durations and may not overlap")
            if any(type(p) is not int or not 12 <= p <= 127 for p in event.pitches):
                raise CodettaError("MusicXML pitch export supports MIDI pitches 12 through 127")
            _ticks(event.start)
            _ticks(event.duration)
            previous_end = event.start + event.duration
            if previous_end > score.duration:
                raise CodettaError("A note extends beyond the display score")
        for measure_index in range(measures):
            begin, end = measure_index * capacity, (measure_index + 1) * capacity
            cursor = begin
            segments: list[tuple[DisplayNote, Fraction, Fraction]] = []
            for event in events:
                if event.start >= end or event.start + event.duration <= begin:
                    continue
                first, last = max(event.start, begin), min(event.start + event.duration, end)
                if first > cursor:
                    segments.append((DisplayNote(cursor, first - cursor, (), staff, voice), cursor, first))
                segments.append((event, first, last))
                cursor = last
            if cursor < end:
                segments.append((DisplayNote(cursor, end - cursor, (), staff, voice), cursor, end))
            index = 0
            for event, cursor, end in segments:
                while cursor < end:
                    remaining = end - cursor
                    for duration, note_type, dotted in DURATIONS:
                        if duration <= remaining:
                            break
                    else:
                        raise CodettaError("Cannot spell this duration with the supported note values")
                    index += 1
                    result.append(_Piece(event, cursor, duration, note_type, dotted, measure_index,
                                         f"n-s{staff}-v{voice}-m{measure_index + 1}-{index}"))
                    if len(result) > 16384:
                        raise CodettaError("Notation exceeds 16,384 note/rest fragments")
                    cursor += duration
    return result


def _pitch(midi: int, fifths: int) -> tuple[str, int, int]:
    sharp = (("C", 0), ("C", 1), ("D", 0), ("D", 1), ("E", 0), ("F", 0),
             ("F", 1), ("G", 0), ("G", 1), ("A", 0), ("A", 1), ("B", 0))
    flat = (("C", 0), ("D", -1), ("D", 0), ("E", -1), ("E", 0), ("F", 0),
            ("G", -1), ("G", 0), ("A", -1), ("A", 0), ("B", -1), ("B", 0))
    step, alter = (flat if fifths < 0 else sharp)[midi % 12]
    return step, alter, midi // 12 - 1


def _scope_marks(score: DisplayScore, pieces: list[_Piece], *, debug: bool):
    directions: list[tuple[Fraction, int, str, dict[str, object]]] = []
    slurs: dict[str, list[dict[str, object]]] = {}
    active: dict[tuple[int, str], list[tuple[Fraction, int]]] = {}
    sequence_paths = {scope.path for scope in score.scopes if scope.kind == "Sequence"}
    for scope in sorted(score.scopes, key=lambda s: (s.start, -s.end, s.depth)):
        if debug:
            label = f"Span={scope.end - scope.start}" if scope.kind == "Span" else scope.kind
            directions.append((scope.start, scope.staff, "words",
                               {"text": label, "font_size": 8, "default_y": 55 + scope.depth * 22}))
        if scope.kind == "Zero":
            directions.append((scope.start, scope.staff, "coda", {}))
        if scope.kind not in ("Sequence", "Scale", "Unscale", "Invert") or scope.start == scope.end:
            continue
        # Associative chains of additions form one musical phrase. Keep every
        # original scope in Debug mode without stacking redundant nested slurs.
        if scope.kind == "Sequence" and scope.path.rsplit("/phrase[", 1)[0] in sequence_paths and "/phrase[" in scope.path:
            continue
        category = "slur" if scope.kind == "Sequence" else "bracket"
        target = [p for p in pieces if p.event.staff == scope.staff and p.event.pitches
                  and (p.event.path == scope.path or p.event.path.startswith(scope.path + "/"))]
        target.sort(key=lambda p: p.start)
        if category == "slur" and len(target) < 2:
            continue
        key = (scope.staff, category)
        occupied = [(end, number) for end, number in active.get(key, []) if end > scope.start]
        available = set(range(1, 17)) - {number for _, number in occupied}
        if not available:
            raise CodettaError("More than 16 overlapping notation scopes on one staff")
        number = min(available)
        active[key] = occupied + [(scope.end, number)]
        if category == "slur":
            slurs.setdefault(target[0].identifier, []).append({"type": "start", "number": number,
                                                              "placement": "above"})
            slurs.setdefault(target[-1].identifier, []).insert(0, {"type": "stop", "number": number})
        else:
            attrs = {"number": number, "line_type": "dashed" if scope.kind == "Unscale" else "solid",
                     "line_end": "up" if scope.kind == "Invert" else "down",
                     "placement": "below" if scope.kind == "Invert" else "above",
                     "default_y": -75 - scope.depth * 10 if scope.kind == "Invert" else 25 + scope.depth * 10}
            directions.append((scope.start, scope.staff, "bracket", dict(attrs, type="start")))
            directions.append((scope.end, scope.staff, "bracket", dict(attrs, type="stop")))
    return directions, slurs


def score_to_musicxml(score: DisplayScore, *, debug: bool = False) -> str:
    if not 1 <= score.staves <= 32 or score.duration < 0:
        raise CodettaError("Invalid display score extent")
    for note in score.notes:
        if not 1 <= note.staff <= score.staves or not 1 <= note.voice <= 4:
            raise CodettaError("Notation needs a valid staff and a voice between 1 and 4")
    capacity = score.options.measure_beats
    measures = max(1, ceil(score.duration / capacity))
    if measures > MAX_MEASURES:
        raise CodettaError(f"Notation exceeds {MAX_MEASURES} measures")
    pieces = _pieces(score, measures)
    directions, slurs = _scope_marks(score, pieces, debug=debug)
    root = ET.Element("score-partwise", {"version": "4.0"})
    encoding = _el(_el(root, "identification"), "encoding")
    _el(encoding, "software", "Codetta")
    scaling = _el(_el(root, "defaults"), "scaling")
    _el(scaling, "millimeters", 7)
    _el(scaling, "tenths", 40)
    part_list = _el(root, "part-list")
    score_part = _el(part_list, "score-part", id="P1")
    _el(score_part, "part-name", "")
    part = _el(root, "part", id="P1")
    key_alters = {step: (1 if score.options.fifths > 0 else -1)
                  for step in ("FCGDAEB" if score.options.fifths > 0 else "BEADGCF")[:abs(score.options.fifths)]}
    for index in range(measures):
        measure = _el(part, "measure", number=index + 1)
        if index == 0:
            attributes = _el(measure, "attributes")
            _el(attributes, "divisions", DIVISIONS)
            _el(_el(attributes, "key"), "fifths", score.options.fifths)
            time = _el(attributes, "time")
            _el(time, "beats", score.options.beats)
            _el(time, "beat-type", score.options.beat_type)
            if score.staves > 1:
                _el(attributes, "staves", score.staves)
                _el(attributes, "part-symbol", "bracket", top_staff=1, bottom_staff=score.staves)
            for staff in range(1, score.staves + 1):
                clef = _el(attributes, "clef", number=staff)
                _el(clef, "sign", "G" if score.options.clef == "treble" else "F")
                _el(clef, "line", 2 if score.options.clef == "treble" else 4)
        for when, staff, kind, attributes in directions:
            # End markers exactly on a barline belong to the preceding measure.
            is_stop = attributes.get("type") == "stop"
            owner = max(0, ceil(when / capacity) - 1) if is_stop else int(when // capacity)
            owner = min(owner, measures - 1)
            if owner != index:
                continue
            attributes = dict(attributes)
            placement = str(attributes.pop("placement", "above"))
            direction = _el(measure, "direction", placement=placement)
            dtype = _el(direction, "direction-type")
            text = attributes.pop("text", None)
            _el(dtype, kind, text, **attributes)
            _el(direction, "offset", _ticks(when - index * capacity))
            _el(direction, "staff", staff)
        lanes = sorted({(p.event.staff, p.event.voice) for p in pieces if p.measure == index})
        accidental_state: dict[tuple[int, str, int], int] = {}
        accidentals: dict[tuple[str, int], str] = {}
        # MusicXML serializes complete voices with backups; accidental state
        # must instead follow musical time across all voices on each staff.
        for piece in sorted((p for p in pieces if p.measure == index),
                            key=lambda p: (p.start, p.event.staff, p.event.voice)):
            for chord_index, midi in enumerate(piece.event.pitches):
                step, alter, octave = _pitch(midi, score.options.fifths)
                state_key = (piece.event.staff, step, octave)
                prior = accidental_state.get(state_key, key_alters.get(step, 0))
                if prior != alter and piece.start == piece.event.start:
                    accidentals[(piece.identifier, chord_index)] = {-1: "flat", 0: "natural", 1: "sharp"}[alter]
                accidental_state[state_key] = alter
        for lane_index, (staff, voice) in enumerate(lanes):
            if lane_index:
                _el(_el(measure, "backup"), "duration", _ticks(capacity))
            for piece in (p for p in pieces if p.measure == index and (p.event.staff, p.event.voice) == (staff, voice)):
                event = piece.event
                tie_stop = bool(event.pitches) and piece.start > event.start
                tie_start = bool(event.pitches) and piece.start + piece.duration < event.start + event.duration
                for chord_index, midi in enumerate(event.pitches or (None,)):
                    note = _el(measure, "note", id=piece.identifier + (f"-ch{chord_index}" if chord_index else ""))
                    if chord_index:
                        _el(note, "chord")
                    accidental = accidentals.get((piece.identifier, chord_index))
                    if midi is None:
                        _el(note, "rest")
                    else:
                        step, alter, octave = _pitch(midi, score.options.fifths)
                        pitch = _el(note, "pitch")
                        _el(pitch, "step", step)
                        if alter:
                            _el(pitch, "alter", alter)
                        _el(pitch, "octave", octave)
                    _el(note, "duration", _ticks(piece.duration))
                    for tied, kind in ((tie_stop, "stop"), (tie_start, "start")):
                        if tied:
                            _el(note, "tie", type=kind)
                    _el(note, "voice", (staff - 1) * 4 + voice)
                    _el(note, "type", piece.note_type)
                    if piece.dotted:
                        _el(note, "dot")
                    if accidental:
                        _el(note, "accidental", accidental)
                    _el(note, "staff", staff)
                    marks = slurs.get(piece.identifier, []) if chord_index == 0 else []
                    if tie_start or tie_stop or marks:
                        notations = _el(note, "notations")
                        for tied, kind in ((tie_stop, "stop"), (tie_start, "start")):
                            if tied:
                                _el(notations, "tied", type=kind)
                        for mark in marks:
                            _el(notations, "slur", **mark)
        if index == measures - 1:
            _el(_el(measure, "barline", location="right"), "bar-style", "light-heavy")
    ET.indent(root)
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def to_musicxml(program: ir.Emit, options: NotationOptions | None = None, *, debug: bool = False) -> str:
    return score_to_musicxml(project(program, options), debug=debug)


def write_musicxml(program: ir.Emit, path: str | Path, options: NotationOptions | None = None,
                   *, debug: bool = False) -> Path:
    xml = to_musicxml(program, options, debug=debug)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(xml, encoding="utf-8")
    return destination

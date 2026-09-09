"""Export Codetta Score Model notation as standard MusicXML 4.0."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from math import ceil
from pathlib import Path
import xml.etree.ElementTree as ET

from codetta.score_model import Score
from codetta.semantics import CodettaError
from rendering.model import DisplayNote, DisplayScore, from_score

DIVISIONS = 8
MAX_MEASURES = 1024
DURATIONS = ((Fraction(4), "whole", False), (Fraction(3), "half", True),
             (Fraction(2), "half", False), (Fraction(3, 2), "quarter", True),
             (Fraction(1), "quarter", False), (Fraction(3, 4), "eighth", True),
             (Fraction(1, 2), "eighth", False), (Fraction(3, 8), "16th", True),
             (Fraction(1, 4), "16th", False), (Fraction(1, 8), "32nd", False))


def _el(parent: ET.Element, tag: str, value: object | None = None, **attrs: object) -> ET.Element:
    child = ET.SubElement(parent, tag, {key.replace("_", "-"): str(item) for key, item in attrs.items()})
    if value is not None:
        child.text = str(value)
    return child


def _ticks(beats: Fraction) -> int:
    ticks = beats * DIVISIONS
    if ticks.denominator != 1:
        raise CodettaError("MusicXML export supports durations in multiples of 1/8 quarter note")
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
    lanes = {(event.staff, event.voice) for event in score.notes}
    lanes.update((staff, 1) for staff in range(1, score.staves + 1))
    pieces: list[_Piece] = []
    for staff, voice in sorted(lanes):
        events = sorted((event for event in score.notes if (event.staff, event.voice) == (staff, voice)),
                        key=lambda event: (event.start, event.event_id))
        previous_end = Fraction(0)
        for event in events:
            if event.duration <= 0 or event.start < previous_end:
                raise CodettaError("Notes in one voice must have positive durations and may not overlap")
            previous_end = event.start + event.duration
        for measure_index in range(measures):
            begin, end = capacity * measure_index, capacity * (measure_index + 1)
            cursor = begin
            segments: list[tuple[DisplayNote, Fraction, Fraction]] = []
            for event in events:
                if event.start >= end or event.start + event.duration <= begin:
                    continue
                first, last = max(event.start, begin), min(event.start + event.duration, end)
                if first > cursor:
                    segments.append((DisplayNote(cursor, first - cursor, (), staff, voice,
                                                 f"padding-{staff}-{voice}-{cursor}"), cursor, first))
                segments.append((event, first, last))
                cursor = last
            if cursor < end:
                segments.append((DisplayNote(cursor, end - cursor, (), staff, voice,
                                             f"padding-{staff}-{voice}-{cursor}"), cursor, end))
            index = 0
            for event, cursor, segment_end in segments:
                while cursor < segment_end:
                    remaining = segment_end - cursor
                    spelling = next((item for item in DURATIONS if item[0] <= remaining), None)
                    if spelling is None:
                        raise CodettaError("Cannot spell a score duration with supported note values")
                    duration, note_type, dotted = spelling
                    index += 1
                    pieces.append(_Piece(event, cursor, duration, note_type, dotted, measure_index,
                                         f"n-s{staff}-v{voice}-m{measure_index + 1}-{index}"))
                    if len(pieces) > 16_384:
                        raise CodettaError("Notation exceeds 16,384 note and rest fragments")
                    cursor += duration
    return pieces


def _pitch(midi: int, fifths: int) -> tuple[str, int, int]:
    sharp = (("C", 0), ("C", 1), ("D", 0), ("D", 1), ("E", 0), ("F", 0),
             ("F", 1), ("G", 0), ("G", 1), ("A", 0), ("A", 1), ("B", 0))
    flat = (("C", 0), ("D", -1), ("D", 0), ("E", -1), ("E", 0), ("F", 0),
            ("G", -1), ("G", 0), ("A", -1), ("A", 0), ("B", -1), ("B", 0))
    step, alter = (flat if fifths < 0 else sharp)[midi % 12]
    return step, alter, midi // 12 - 1


def _marks(score: DisplayScore, pieces: list[_Piece], *, debug: bool):
    directions: list[tuple[Fraction, int, str, dict[str, object]]] = []
    slurs: dict[str, list[dict[str, object]]] = {}
    by_event: dict[str, list[_Piece]] = {}
    for piece in pieces:
        by_event.setdefault(piece.event.event_id, []).append(piece)
    for event in score.notes:
        if debug and event.pitches:
            directions.append((event.start, event.staff, "words",
                               {"text": f"value duration={event.duration}", "font_size": 8,
                                "default_y": 55}))
    for scope in sorted(score.scopes, key=lambda item: (item.start, -item.end, item.depth)):
        label = {("slur", "solid"): "Sum", ("bracket", "solid"): "Product",
                 ("slur", "dashed"): "Negate", ("bracket", "dashed"): "Reciprocal"}[
                    (scope.kind, scope.line_style)]
        if debug:
            directions.append((scope.start, scope.top_staff, "words",
                               {"text": label, "font_size": 8,
                                "default_y": 75 + scope.depth * 18}))
        starts = sorted(by_event.get(scope.start_anchor, ()), key=lambda piece: piece.start)
        ends = sorted(by_event.get(scope.end_anchor, ()), key=lambda piece: piece.start)
        if not starts or not ends:
            raise CodettaError(f"Cannot locate spanner anchors for {scope.identifier}")
        first, last = starts[0], ends[-1]
        if scope.kind == "slur" and first.identifier != last.identifier:
            number = scope.depth % 16 + 1
            slurs.setdefault(first.identifier, []).append({"type": "start", "number": number,
                                                          "placement": "above",
                                                          "line_type": scope.line_style})
            slurs.setdefault(last.identifier, []).insert(0, {"type": "stop", "number": number})
        else:
            attributes = {"number": scope.depth % 16 + 1, "line_type": scope.line_style,
                          "line_end": "none" if scope.kind == "slur" else "down",
                          "placement": "below" if scope.line_style == "dashed" else "above",
                          "default_y": -70 - scope.depth * 10 if scope.line_style == "dashed"
                          else 25 + scope.depth * 10}
            directions.append((scope.start, scope.top_staff, "bracket", dict(attributes, type="start")))
            directions.append((scope.end, scope.top_staff, "bracket", dict(attributes, type="stop")))
    return directions, slurs


def display_to_musicxml(score: DisplayScore, *, debug: bool = False) -> str:
    capacity = score.options.measure_beats
    measures = max(1, ceil(score.duration / capacity))
    if measures > MAX_MEASURES:
        raise CodettaError(f"Notation exceeds {MAX_MEASURES} measures")
    pieces = _pieces(score, measures)
    directions, slurs = _marks(score, pieces, debug=debug)
    root = ET.Element("score-partwise", {"version": "4.0"})
    if score.title:
        _el(_el(root, "work"), "work-title", score.title)
    encoding = _el(_el(root, "identification"), "encoding")
    _el(encoding, "software", "Codetta")
    part_list = _el(root, "part-list")
    score_part = _el(part_list, "score-part", id="P1")
    _el(score_part, "part-name", "")
    part = _el(root, "part", id="P1")
    key_alters = {step: (1 if score.options.fifths > 0 else -1)
                  for step in ("FCGDAEB" if score.options.fifths > 0 else "BEADGCF")[:abs(score.options.fifths)]}
    for measure_index in range(measures):
        measure = _el(part, "measure", number=measure_index + 1)
        if measure_index == 0:
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
            is_stop = attributes.get("type") == "stop"
            owner = max(0, ceil(when / capacity) - 1) if is_stop else int(when // capacity)
            owner = min(owner, measures - 1)
            if owner != measure_index:
                continue
            attributes = dict(attributes)
            placement = str(attributes.pop("placement", "above"))
            direction = _el(measure, "direction", placement=placement)
            direction_type = _el(direction, "direction-type")
            text = attributes.pop("text", None)
            _el(direction_type, kind, text, **attributes)
            _el(direction, "offset", _ticks(when - measure_index * capacity))
            _el(direction, "staff", staff)
        lanes = sorted({(piece.event.staff, piece.event.voice) for piece in pieces
                        if piece.measure == measure_index})
        accidental_state: dict[tuple[int, str, int], int] = {}
        accidentals: dict[tuple[str, int], str] = {}
        for piece in sorted((piece for piece in pieces if piece.measure == measure_index),
                            key=lambda item: (item.start, item.event.staff, item.event.voice)):
            for chord_index, midi in enumerate(piece.event.pitches):
                step, alter, octave = (piece.event.spellings[chord_index]
                                       if piece.event.spellings else _pitch(midi, score.options.fifths))
                key = (piece.event.staff, step, octave)
                previous = accidental_state.get(key, key_alters.get(step, 0))
                if previous != alter and piece.start == piece.event.start:
                    accidentals[(piece.identifier, chord_index)] = {
                        -2: "flat-flat", -1: "flat", 0: "natural", 1: "sharp", 2: "double-sharp"
                    }[alter]
                accidental_state[key] = alter
        for lane_index, (staff, voice) in enumerate(lanes):
            if lane_index:
                _el(_el(measure, "backup"), "duration", _ticks(capacity))
            lane_pieces = (piece for piece in pieces if piece.measure == measure_index
                           and (piece.event.staff, piece.event.voice) == (staff, voice))
            for piece in lane_pieces:
                event = piece.event
                split_stop = piece.start > event.start
                split_start = piece.start + piece.duration < event.start + event.duration
                tie_stop = bool(event.pitches) and (split_stop or (piece.start == event.start and event.tie_stop))
                tie_start = bool(event.pitches) and (split_start or (
                    piece.start + piece.duration == event.start + event.duration and event.tie_start))
                for chord_index, midi in enumerate(event.pitches or (None,)):
                    note = _el(measure, "note", id=piece.identifier + (f"-ch{chord_index}" if chord_index else ""))
                    if chord_index:
                        _el(note, "chord")
                    if midi is None:
                        _el(note, "rest")
                    else:
                        step, alter, octave = (event.spellings[chord_index]
                                               if event.spellings else _pitch(midi, score.options.fifths))
                        pitch = _el(note, "pitch")
                        _el(pitch, "step", step)
                        if alter:
                            _el(pitch, "alter", alter)
                        _el(pitch, "octave", octave)
                    _el(note, "duration", _ticks(piece.duration))
                    for active, tie_type in ((tie_stop, "stop"), (tie_start, "start")):
                        if active:
                            _el(note, "tie", type=tie_type)
                    _el(note, "voice", (staff - 1) * 4 + voice)
                    _el(note, "type", piece.note_type)
                    if piece.dotted:
                        _el(note, "dot")
                    accidental = event.accidental or accidentals.get((piece.identifier, chord_index))
                    if accidental:
                        _el(note, "accidental", accidental)
                    if event.stem:
                        _el(note, "stem", event.stem)
                    _el(note, "staff", staff)
                    marks = slurs.get(piece.identifier, []) if chord_index == 0 else []
                    if tie_start or tie_stop or marks:
                        notations = _el(note, "notations")
                        for active, tie_type in ((tie_stop, "stop"), (tie_start, "start")):
                            if active:
                                _el(notations, "tied", type=tie_type)
                        for mark in marks:
                            mark = dict(mark)
                            placement = mark.pop("placement", None)
                            _el(notations, "slur", **mark, **({"placement": placement} if placement else {}))
        if measure_index == measures - 1:
            _el(_el(measure, "barline", location="right"), "bar-style", "light-heavy")
    ET.indent(root)
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def to_musicxml(score: Score, *, debug: bool = False) -> str:
    return display_to_musicxml(from_score(score), debug=debug)


def write_musicxml(score: Score, path: str | Path, *, debug: bool = False) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(to_musicxml(score, debug=debug), encoding="utf-8", newline="\n")
    return destination

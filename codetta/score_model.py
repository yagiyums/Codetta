"""Canonical notation model stored by the ``.codetta`` format.

The model deliberately contains notation, identifiers, and engraving choices,
but no precomputed values or operation names.  Programming meaning is derived
by :mod:`codetta.score_parser` from durations, voices, and spanners.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import TypeAlias

from codetta.semantics import CodettaError


FORMAT = "codetta-score"
FORMAT_VERSION = "0.1"
LANGUAGE_VERSION = "0.1"
MAX_SCORE_EVENTS = 16_384
METADATA_FIELDS = frozenset({"title", "composer", "description"})


@dataclass(frozen=True)
class Pitch:
    step: str
    alter: int
    octave: int

    def __post_init__(self) -> None:
        if not isinstance(self.step, str) or self.step not in "CDEFGAB" or type(self.alter) is not int or not -2 <= self.alter <= 2:
            raise CodettaError("Pitch needs a step C through B and an alter between -2 and 2")
        if type(self.octave) is not int or not -1 <= self.octave <= 9:
            raise CodettaError("Pitch octave must be between -1 and 9")
        if not 0 <= self.midi <= 127:
            raise CodettaError("Pitch is outside the MIDI range")

    @property
    def midi(self) -> int:
        semitone = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}[self.step]
        return (self.octave + 1) * 12 + semitone + self.alter

    @classmethod
    def from_midi(cls, midi: int) -> Pitch:
        if type(midi) is not int or not 0 <= midi <= 127:
            raise CodettaError("MIDI pitch must be an integer between 0 and 127")
        names = (("C", 0), ("C", 1), ("D", 0), ("D", 1), ("E", 0), ("F", 0),
                 ("F", 1), ("G", 0), ("G", 1), ("A", 0), ("A", 1), ("B", 0))
        step, alter = names[midi % 12]
        return cls(step, alter, midi // 12 - 1)


@dataclass(frozen=True)
class TimeSignature:
    beats: int
    beat_type: int

    def __post_init__(self) -> None:
        if type(self.beats) is not int or not 1 <= self.beats <= 256:
            raise CodettaError("Time signature numerator must be between 1 and 256")
        if self.beat_type not in (1, 2, 4, 8, 16, 32):
            raise CodettaError("Time signature denominator must be 1, 2, 4, 8, 16 or 32")

    @property
    def duration(self) -> Fraction:
        """Measure duration in whole-note units."""
        return Fraction(self.beats, self.beat_type)


@dataclass(frozen=True)
class KeySignature:
    fifths: int = 0

    def __post_init__(self) -> None:
        if type(self.fifths) is not int or not -7 <= self.fifths <= 7:
            raise CodettaError("Key signature fifths must be between -7 and 7")


@dataclass(frozen=True)
class Clef:
    sign: str = "G"
    line: int = 2

    def __post_init__(self) -> None:
        if not isinstance(self.sign, str) or type(self.line) is not int or (self.sign, self.line) not in (("G", 2), ("F", 4)):
            raise CodettaError("Codetta v0.1 supports treble G2 and bass F4 clefs")


@dataclass(frozen=True)
class Note:
    id: str
    start: Fraction
    duration: Fraction
    pitch: Pitch
    accidental: str | None = None
    stem: str | None = None
    type: str = field(default="note", init=False)


@dataclass(frozen=True)
class Rest:
    id: str
    start: Fraction
    duration: Fraction
    type: str = field(default="rest", init=False)


@dataclass(frozen=True)
class Chord:
    id: str
    start: Fraction
    duration: Fraction
    pitches: tuple[Pitch, ...]
    accidental: str | None = None
    stem: str | None = None
    type: str = field(default="chord", init=False)


Event: TypeAlias = Note | Rest | Chord


@dataclass(frozen=True)
class Voice:
    id: str
    staff: int
    events: tuple[Event, ...]


@dataclass(frozen=True)
class Measure:
    id: str
    number: int
    time_signature: TimeSignature
    key_signature: KeySignature
    clef: Clef
    voices: tuple[Voice, ...]
    barline: str = "regular"

    @property
    def duration(self) -> Fraction:
        return self.time_signature.duration


@dataclass(frozen=True)
class Staff:
    id: str
    measures: tuple[Measure, ...]


@dataclass(frozen=True)
class Part:
    id: str
    staves: tuple[Staff, ...]


@dataclass(frozen=True)
class Spanner:
    id: str
    type: str
    line_style: str
    start_anchor: str
    end_anchor: str
    staff_range: tuple[int, int] | None = None
    voice_range: tuple[int, int] | None = None
    nesting_level: int = 0


@dataclass(frozen=True)
class Score:
    metadata: dict[str, str]
    parts: tuple[Part, ...]
    spanners: tuple[Spanner, ...]
    format_version: str = FORMAT_VERSION
    language_version: str = LANGUAGE_VERSION


def iter_measures(score: Score):
    for part in score.parts:
        for staff_index, staff in enumerate(part.staves, 1):
            for measure in staff.measures:
                yield part, staff_index, staff, measure


def iter_events(score: Score):
    for part, staff_index, staff, measure in iter_measures(score):
        for voice in measure.voices:
            for event in voice.events:
                yield part, staff_index, staff, measure, voice, event


def validate_score(score: Score) -> Score:
    """Validate structural notation invariants without interpreting the program."""
    if not isinstance(score, Score):
        raise CodettaError("Expected a Codetta Score Model")
    if score.format_version != FORMAT_VERSION or score.language_version != LANGUAGE_VERSION:
        raise CodettaError("Only Codetta score and language version 0.1 are supported")
    if len(score.parts) != 1 or not score.parts[0].staves:
        raise CodettaError("Codetta v0.1 needs exactly one part with at least one staff")
    if (not all(isinstance(key, str) and isinstance(value, str) for key, value in score.metadata.items())
            or not set(score.metadata) <= METADATA_FIELDS):
        raise CodettaError("Score metadata supports only string title, composer and description fields")

    identifiers: set[str] = set()

    def identify(identifier: str, kind: str) -> None:
        if not isinstance(identifier, str) or not identifier or identifier in identifiers:
            raise CodettaError(f"{kind} needs a nonempty, globally unique ID")
        identifiers.add(identifier)

    part = score.parts[0]
    identify(part.id, "Part")
    measure_counts = {len(staff.measures) for staff in part.staves}
    if len(measure_counts) != 1 or not next(iter(measure_counts)):
        raise CodettaError("Every staff must contain the same nonzero number of measures")
    event_locations: dict[str, tuple[int, int, str, Event]] = {}
    event_count = 0
    reference_measures: tuple[Measure, ...] | None = None
    for staff_index, staff in enumerate(part.staves, 1):
        identify(staff.id, "Staff")
        if reference_measures is None:
            reference_measures = staff.measures
        for measure_index, measure in enumerate(staff.measures):
            identify(measure.id, "Measure")
            if measure.number != measure_index + 1:
                raise CodettaError("Measure numbers must be consecutive and start at 1")
            reference = reference_measures[measure_index]
            if (measure.number, measure.time_signature, measure.key_signature) != (
                    reference.number, reference.time_signature, reference.key_signature):
                raise CodettaError("Parallel staves must have matching measure attributes")
            if measure.barline not in ("regular", "light-heavy"):
                raise CodettaError("Barline must be regular or light-heavy")
            if not 1 <= len(measure.voices) <= 4:
                raise CodettaError("A measure must contain between one and four voices per staff")
            for voice in measure.voices:
                identify(voice.id, "Voice")
                if voice.staff != staff_index or not 1 <= voice.staff <= len(part.staves):
                    raise CodettaError("Voice staff number does not match its containing staff")
                previous_end = Fraction(0)
                for event in sorted(voice.events, key=lambda item: (item.start, item.id)):
                    identify(event.id, "Event")
                    event_count += 1
                    if event_count > MAX_SCORE_EVENTS:
                        raise CodettaError(f"A score may contain at most {MAX_SCORE_EVENTS:,} events")
                    if not isinstance(event.start, Fraction) or not isinstance(event.duration, Fraction):
                        raise CodettaError("Event times and durations must be rational numbers")
                    if event.start < 0 or event.duration <= 0 or event.start + event.duration > measure.duration:
                        raise CodettaError(f"Event {event.id} is outside measure {measure.number}")
                    if event.start < previous_end:
                        raise CodettaError(f"Events overlap in voice {voice.id}")
                    previous_end = event.start + event.duration
                    if isinstance(event, Chord) and len(event.pitches) < 2:
                        raise CodettaError("A chord must contain at least two pitches")
                    if getattr(event, "accidental", None) not in (None, "sharp", "flat", "natural"):
                        raise CodettaError("Unsupported accidental")
                    if getattr(event, "stem", None) not in (None, "up", "down"):
                        raise CodettaError("Stem must be up, down or omitted")
                    event_locations[event.id] = (measure.number, staff_index, voice.id, event)

    for spanner in score.spanners:
        identify(spanner.id, "Spanner")
        if spanner.type not in ("tie", "slur", "bracket"):
            raise CodettaError("Spanner type must be tie, slur or bracket")
        if spanner.line_style not in ("solid", "dashed"):
            raise CodettaError("Spanner line style must be solid or dashed")
        if spanner.start_anchor not in event_locations or spanner.end_anchor not in event_locations:
            raise CodettaError(f"Spanner {spanner.id} refers to a missing event")
        if type(spanner.nesting_level) is not int or spanner.nesting_level < 0:
            raise CodettaError("Spanner nesting level must be a nonnegative integer")
        start = event_locations[spanner.start_anchor]
        end = event_locations[spanner.end_anchor]
        if start[0] != end[0]:
            raise CodettaError("Codetta v0.1 spanners may not cross a measure boundary")
        if spanner.staff_range is not None:
            top, bottom = spanner.staff_range
            if not 1 <= top <= bottom <= len(part.staves):
                raise CodettaError("Spanner staff range is outside the part")
        if spanner.voice_range is not None:
            first, last = spanner.voice_range
            if not 1 <= first <= last <= 4:
                raise CodettaError("Spanner voice range must be between 1 and 4")
        if spanner.type == "tie":
            if spanner.line_style != "solid" or not isinstance(start[3], Note) or not isinstance(end[3], Note):
                raise CodettaError("A tie must be solid and join two notes")
            if start[1:3] != end[1:3] or start[3].pitch != end[3].pitch:
                raise CodettaError("A tie must join the same pitch in one voice")
            if start[3].start + start[3].duration != end[3].start:
                raise CodettaError("Tied notes must be contiguous")
    return score

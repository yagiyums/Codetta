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
SUPPORTED_VERSIONS = frozenset({"0.1", "0.2"})
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
        if type(self.beats) is not int or not 1 <= self.beats <= 4096:
            raise CodettaError("Time signature numerator must be between 1 and 4096")
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


@dataclass(frozen=True)
class Cue:
    """A small notated reference to the current value of another Voice."""

    id: str
    start: Fraction
    duration: Fraction
    source_voice_id: str
    pitch: Pitch
    accidental: str | None = None
    stem: str | None = None
    type: str = field(default="cue", init=False)


Event: TypeAlias = Note | Rest | Chord | Cue


@dataclass(frozen=True)
class Voice:
    id: str
    staff: int
    events: tuple[Event, ...]
    name: str | None = None


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
class VoiceGroup:
    id: str
    name: str
    voice_ids: tuple[str, ...]
    output_anchor: str | None = None


@dataclass(frozen=True)
class PhraseRegion:
    id: str
    start_anchor: str
    end_anchor: str
    voice_ids: tuple[str, ...]
    output_anchor: str


@dataclass(frozen=True)
class Relation:
    """A directional musical connector; operand meaning comes from its shape."""

    id: str
    connector: str
    input_anchors: tuple[str, ...]
    output_anchor: str
    field_voice_id: str | None = None


@dataclass(frozen=True)
class Section:
    id: str
    name: str
    rehearsal_mark: str
    start_measure: str
    end_measure: str
    parameter_voice_ids: tuple[str, ...] = ()
    return_voice_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class SectionReference:
    id: str
    section_id: str
    anchor: str
    argument_voice_ids: tuple[str, ...]
    result_voice_ids: tuple[str, ...]


@dataclass(frozen=True)
class RepeatRegion:
    id: str
    start_measure: str
    end_measure: str
    iterator_voice_id: str | None = None
    times: int | None = None
    count_voice_id: str | None = None
    collection_voice_id: str | None = None
    condition_voice_id: str | None = None
    test_at_end: bool = False


@dataclass(frozen=True)
class VoltaEnding:
    numbers: tuple[int, ...]
    start_measure: str
    end_measure: str


@dataclass(frozen=True)
class VoltaGroup:
    id: str
    condition_voice_id: str
    endings: tuple[VoltaEnding, ...]


@dataclass(frozen=True)
class Score:
    metadata: dict[str, str]
    parts: tuple[Part, ...]
    spanners: tuple[Spanner, ...]
    format_version: str = FORMAT_VERSION
    language_version: str = LANGUAGE_VERSION
    voice_groups: tuple[VoiceGroup, ...] = ()
    phrases: tuple[PhraseRegion, ...] = ()
    relations: tuple[Relation, ...] = ()
    sections: tuple[Section, ...] = ()
    section_references: tuple[SectionReference, ...] = ()
    repeats: tuple[RepeatRegion, ...] = ()
    voltas: tuple[VoltaGroup, ...] = ()


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
    if (score.format_version not in SUPPORTED_VERSIONS
            or score.language_version != score.format_version):
        raise CodettaError("Codetta score and language versions must both be 0.1 or 0.2")
    version = score.language_version
    if len(score.parts) != 1 or not score.parts[0].staves:
        raise CodettaError("Codetta v0.1 needs exactly one part with at least one staff")
    if (not all(isinstance(key, str) and isinstance(value, str) for key, value in score.metadata.items())
            or not set(score.metadata) <= METADATA_FIELDS):
        raise CodettaError("Score metadata supports only string title, composer and description fields")

    identifiers: set[str] = set()
    voice_definitions: dict[str, tuple[int, str | None]] = {}

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
            if version == "0.1" and measure.time_signature.beats > 256:
                raise CodettaError("Codetta v0.1 time signatures support at most 256 beats")
            if version == "0.1" and not 1 <= len(measure.voices) <= 4:
                raise CodettaError("A v0.1 measure must contain between one and four voices per staff")
            if version == "0.2" and len(measure.voices) > 4:
                raise CodettaError("A measure may contain at most four voices per staff")
            measure_voice_ids: set[str] = set()
            for voice in measure.voices:
                if not isinstance(voice.id, str) or not voice.id:
                    raise CodettaError("Voice needs a nonempty ID")
                if voice.id in measure_voice_ids:
                    raise CodettaError(f"Voice {voice.id} occurs twice in one measure")
                measure_voice_ids.add(voice.id)
                if version == "0.1":
                    identify(voice.id, "Voice")
                    if voice.name is not None:
                        raise CodettaError("Codetta v0.1 Voices do not have names")
                elif voice.id in voice_definitions:
                    if voice_definitions[voice.id] != (voice.staff, voice.name):
                        raise CodettaError(f"Voice {voice.id} changes staff or name")
                else:
                    if voice.name is not None and (
                            not isinstance(voice.name, str) or not voice.name.isidentifier()):
                        raise CodettaError("A named Voice needs a programming identifier")
                    voice_definitions[voice.id] = (voice.staff, voice.name)
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
                    if isinstance(event, Cue) and version != "0.2":
                        raise CodettaError("Cue events require Codetta v0.2")
                    if isinstance(event, Chord) and len(event.pitches) < 2:
                        raise CodettaError("A chord must contain at least two pitches")
                    if getattr(event, "accidental", None) not in (None, "sharp", "flat", "natural"):
                        raise CodettaError("Unsupported accidental")
                    if getattr(event, "stem", None) not in (None, "up", "down"):
                        raise CodettaError("Stem must be up, down or omitted")
                    event_locations[event.id] = (measure.number, staff_index, voice.id, event)

    if version == "0.1" and any((score.voice_groups, score.phrases, score.relations,
                                  score.sections, score.section_references,
                                  score.repeats, score.voltas)):
        raise CodettaError("Codetta v0.1 cannot contain v0.2 score structures")
    voice_ids = set(voice_definitions)
    if version == "0.2":
        for voice_id in voice_ids:
            identify(voice_id, "Voice")
        for _, _, _, _, _, event in iter_events(score):
            if isinstance(event, Cue) and event.source_voice_id not in voice_ids:
                raise CodettaError(f"Cue {event.id} refers to a missing Voice")
    measure_positions = {measure.id: measure.number
                         for _, _, _, measure in iter_measures(score)}
    measure_ids = set(measure_positions)

    def ordered_range(start: str, end: str, location: str) -> None:
        if start not in measure_ids or end not in measure_ids:
            raise CodettaError(f"{location} refers to a missing measure")
        if measure_positions[start] > measure_positions[end]:
            raise CodettaError(f"{location} runs backwards")

    def voices_exist(values: tuple[str, ...], location: str, *, nonempty: bool = False,
                     allow_duplicates: bool = False) -> None:
        if nonempty and not values:
            raise CodettaError(f"{location} needs at least one Voice")
        if ((not allow_duplicates and len(set(values)) != len(values))
                or any(value not in voice_ids for value in values)):
            raise CodettaError(f"{location} refers to missing or duplicate Voices")

    def anchors_exist(values: tuple[str, ...], location: str) -> None:
        if not values or any(value not in event_locations for value in values):
            raise CodettaError(f"{location} refers to missing events")

    for group in score.voice_groups:
        identify(group.id, "Voice group")
        if not isinstance(group.name, str) or not group.name:
            raise CodettaError("Voice group needs a name")
        voices_exist(group.voice_ids, f"Voice group {group.id}", nonempty=True)
        if group.output_anchor is not None:
            anchors_exist((group.output_anchor,), f"Voice group {group.id}")
    for phrase in score.phrases:
        identify(phrase.id, "Phrase")
        anchors_exist((phrase.start_anchor, phrase.end_anchor, phrase.output_anchor),
                      f"Phrase {phrase.id}")
        voices_exist(phrase.voice_ids, f"Phrase {phrase.id}", nonempty=True)
    connectors = {"slur", "bracket", "dashed-slur", "dashed-bracket",
                  "hairpin-crescendo", "hairpin-diminuendo", "unison",
                  "scalar-stack", "application", "field"}
    for relation in score.relations:
        identify(relation.id, "Relation")
        if relation.connector not in connectors:
            raise CodettaError(f"Relation {relation.id} has an unsupported connector")
        anchors_exist(relation.input_anchors + (relation.output_anchor,),
                      f"Relation {relation.id}")
        if relation.field_voice_id is not None and relation.field_voice_id not in voice_ids:
            raise CodettaError(f"Relation {relation.id} refers to a missing field Voice")
    section_ids: set[str] = set()
    section_names: set[str] = set()
    sections_by_id: dict[str, Section] = {}
    for section in score.sections:
        identify(section.id, "Section")
        section_ids.add(section.id)
        sections_by_id[section.id] = section
        if (not isinstance(section.name, str) or not section.name.isidentifier()
                or section.name in section_names or not isinstance(section.rehearsal_mark, str)
                or not section.rehearsal_mark):
            raise CodettaError("Sections need unique identifier names and rehearsal marks")
        section_names.add(section.name)
        ordered_range(section.start_measure, section.end_measure, f"Section {section.id}")
        voices_exist(section.parameter_voice_ids, f"Section {section.id} parameters")
        voices_exist(section.return_voice_ids, f"Section {section.id} returns")
    for reference in score.section_references:
        identify(reference.id, "Section reference")
        if reference.section_id not in section_ids or reference.anchor not in event_locations:
            raise CodettaError(f"Section reference {reference.id} has a missing target or anchor")
        section = sections_by_id[reference.section_id]
        voices_exist(reference.argument_voice_ids, f"Section reference {reference.id} arguments",
                     allow_duplicates=True)
        voices_exist(reference.result_voice_ids, f"Section reference {reference.id} results")
        if len(reference.argument_voice_ids) != len(section.parameter_voice_ids):
            raise CodettaError(f"Section reference {reference.id} has the wrong argument count")
        expected_results = max(1, len(section.return_voice_ids))
        if len(reference.result_voice_ids) != expected_results:
            raise CodettaError(f"Section reference {reference.id} has the wrong result count")
        if event_locations[reference.anchor][2] not in reference.result_voice_ids:
            raise CodettaError(f"Section reference {reference.id} anchor is outside its result Voices")
    for repeat in score.repeats:
        identify(repeat.id, "Repeat")
        ordered_range(repeat.start_measure, repeat.end_measure, f"Repeat {repeat.id}")
        modes = sum((repeat.times is not None, repeat.count_voice_id is not None,
                     repeat.collection_voice_id is not None,
                     repeat.condition_voice_id is not None))
        if modes != 1:
            raise CodettaError("Repeat needs exactly one count, count Voice or condition Voice")
        if repeat.times is not None and (type(repeat.times) is not int or repeat.times < 0):
            raise CodettaError("Repeat count must be a nonnegative integer")
        if type(repeat.test_at_end) is not bool:
            raise CodettaError("Repeat test_at_end must be Bool")
        for value in (repeat.iterator_voice_id, repeat.count_voice_id,
                      repeat.collection_voice_id, repeat.condition_voice_id):
            if value is not None and value not in voice_ids:
                raise CodettaError(f"Repeat {repeat.id} refers to a missing Voice")
    for volta in score.voltas:
        identify(volta.id, "Volta")
        if volta.condition_voice_id not in voice_ids or not 1 <= len(volta.endings) <= 2:
            raise CodettaError("Volta needs a condition Voice and one or two endings")
        numbers: set[int] = set()
        for ending in volta.endings:
            if (not ending.numbers or numbers.intersection(ending.numbers)
                    or any(type(number) is not int or number < 1 for number in ending.numbers)
                    or ending.start_measure not in measure_ids or ending.end_measure not in measure_ids
                    or measure_positions[ending.start_measure] > measure_positions[ending.end_measure]):
                raise CodettaError(f"Volta {volta.id} has invalid endings")
            numbers.update(ending.numbers)

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
        if version == "0.1" and start[0] != end[0]:
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
            if start[0] == end[0] and start[3].start + start[3].duration != end[3].start:
                raise CodettaError("Tied notes must be contiguous")
    return score

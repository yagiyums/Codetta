"""Read-only display projection of the canonical Codetta Score Model."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from codetta.score_model import Chord, Note, Rest, Score, validate_score
from codetta.semantics import CodettaError


@dataclass(frozen=True)
class NotationOptions:
    beats: int
    beat_type: int
    fifths: int
    clef: str

    @property
    def measure_beats(self) -> Fraction:
        return Fraction(self.beats * 4, self.beat_type)


@dataclass(frozen=True)
class DisplayNote:
    start: Fraction
    duration: Fraction
    pitches: tuple[int, ...]
    staff: int
    voice: int
    event_id: str
    tie_start: bool = False
    tie_stop: bool = False
    spellings: tuple[tuple[str, int, int], ...] = ()
    accidental: str | None = None
    stem: str | None = None


@dataclass(frozen=True)
class Scope:
    kind: str
    line_style: str
    start: Fraction
    end: Fraction
    top_staff: int
    bottom_staff: int
    identifier: str
    start_anchor: str
    end_anchor: str
    depth: int


@dataclass(frozen=True)
class DisplayScore:
    notes: tuple[DisplayNote, ...]
    scopes: tuple[Scope, ...]
    staves: int
    duration: Fraction
    options: NotationOptions
    title: str

def from_score(score: Score) -> DisplayScore:
    """Project notation without parsing or evaluating its programming meaning."""
    validate_score(score)
    part = score.parts[0]
    first = part.staves[0].measures[0]
    for staff in part.staves:
        for measure in staff.measures:
            if measure.time_signature != first.time_signature:
                raise CodettaError("Rendering v0.1 requires one time signature throughout the score")
    measure_beats = first.duration * 4
    tied_from = {spanner.start_anchor for spanner in score.spanners if spanner.type == "tie"}
    tied_to = {spanner.end_anchor for spanner in score.spanners if spanner.type == "tie"}
    event_positions: dict[str, tuple[Fraction, Fraction, int]] = {}
    notes = []
    for staff_number, staff in enumerate(part.staves, 1):
        for measure_index, measure in enumerate(staff.measures):
            offset = measure_beats * measure_index
            for voice_number, voice in enumerate(measure.voices, 1):
                for event in voice.events:
                    start = offset + event.start * 4
                    duration = event.duration * 4
                    event_positions[event.id] = (start, start + duration, staff_number)
                    if isinstance(event, Note):
                        pitches = (event.pitch.midi,)
                        spellings = ((event.pitch.step, event.pitch.alter, event.pitch.octave),)
                        accidental, stem = event.accidental, event.stem
                    elif isinstance(event, Chord):
                        pitches = tuple(pitch.midi for pitch in event.pitches)
                        spellings = tuple((pitch.step, pitch.alter, pitch.octave) for pitch in event.pitches)
                        accidental, stem = event.accidental, event.stem
                    elif isinstance(event, Rest):
                        pitches = ()
                        spellings = ()
                        accidental = stem = None
                    else:
                        raise TypeError(f"Unsupported event {type(event).__name__}")
                    notes.append(DisplayNote(start, duration, pitches, staff_number, voice_number,
                                             event.id, event.id in tied_from, event.id in tied_to,
                                             spellings, accidental, stem))
    scopes = []
    for spanner in score.spanners:
        if spanner.type == "tie":
            continue
        start = event_positions[spanner.start_anchor]
        end = event_positions[spanner.end_anchor]
        top, bottom = spanner.staff_range or (min(start[2], end[2]), max(start[2], end[2]))
        scopes.append(Scope(spanner.type, spanner.line_style, min(start[0], end[0]),
                            max(start[1], end[1]), top, bottom, spanner.id,
                            spanner.start_anchor, spanner.end_anchor, spanner.nesting_level))
    duration = measure_beats * len(part.staves[0].measures)
    options = NotationOptions(first.time_signature.beats, first.time_signature.beat_type,
                              first.key_signature.fifths,
                              "treble" if first.clef.sign == "G" else "bass")
    return DisplayScore(tuple(notes), tuple(scopes), len(part.staves), duration, options,
                        score.metadata.get("title", "Codetta"))

"""Notation choices and a display projection of IR; no program evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from codetta import ir
from codetta.semantics import CodettaError


@dataclass(frozen=True)
class NotationOptions:
    beats: int = 4
    beat_type: int = 4
    fifths: int = 0
    clef: str = "treble"

    def __post_init__(self) -> None:
        if type(self.beats) is not int or not 1 <= self.beats <= 32:
            raise CodettaError("Time signature numerator must be between 1 and 32")
        if self.beat_type not in (1, 2, 4, 8, 16, 32):
            raise CodettaError("Time signature denominator must be 1, 2, 4, 8, 16 or 32")
        if type(self.fifths) is not int or not -7 <= self.fifths <= 7:
            raise CodettaError("Key signature fifths must be between -7 and 7")
        if self.clef not in ("treble", "bass"):
            raise CodettaError("Clef must be treble or bass")

    @property
    def measure_beats(self) -> Fraction:
        return Fraction(self.beats * 4, self.beat_type)


@dataclass(frozen=True)
class DisplayNote:
    start: Fraction
    duration: Fraction
    pitches: tuple[int, ...]  # Empty means a notated rest; multiple means a chord.
    staff: int = 1
    voice: int = 1
    path: str = ""


@dataclass(frozen=True)
class Scope:
    kind: str
    start: Fraction
    end: Fraction
    staff: int
    path: str
    depth: int


@dataclass(frozen=True)
class DisplayScore:
    notes: tuple[DisplayNote, ...]
    scopes: tuple[Scope, ...]
    staves: int
    duration: Fraction
    options: NotationOptions


def project(program: ir.Emit, options: NotationOptions | None = None) -> DisplayScore:
    """Keep written durations; place control expressions on additional staves."""
    if not isinstance(program, ir.Emit):
        raise CodettaError("A displayed program needs one top-level Emit")
    options = options or NotationOptions()
    notes: list[DisplayNote] = []
    scopes: list[Scope] = []
    staves = 1

    def walk(node: ir.Phrase, start: Fraction, staff: int, path: str, depth: int) -> Fraction:
        nonlocal staves
        if depth > 64:
            raise CodettaError("Notation supports up to 64 nested phrases")
        if isinstance(node, ir.Span):
            notes.append(DisplayNote(start, Fraction(node.beats), (node.pitch,), staff, path=path))
            end = start + node.beats
        elif isinstance(node, ir.Zero):
            end = start
        elif isinstance(node, ir.Sequence):
            end = start
            for i, child in enumerate(node.children, 1):
                end = walk(child, end, staff, f"{path}/phrase[{i}]", depth + 1)
        elif isinstance(node, ir.Invert):
            end = walk(node.body, start, staff, path + "/invert", depth + 1)
        elif isinstance(node, (ir.Scale, ir.Unscale)):
            staves += 1
            if staves > 32:
                raise CodettaError("Notation supports up to 32 staves")
            control_staff = staves
            body_end = walk(node.body, start, staff, path + "/body", depth + 1)
            control_end = walk(node.factor, start, control_staff, path + "/control", depth + 1)
            end = max(body_end, control_end)
        else:
            raise TypeError(f"Unsupported IR node: {type(node).__name__}")
        scopes.append(Scope(type(node).__name__, start, end, staff, path, depth))
        return end

    duration = walk(program.body, Fraction(0), 1, "output", 0)
    return DisplayScore(tuple(notes), tuple(scopes), staves, duration, options)

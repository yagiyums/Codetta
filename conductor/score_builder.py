"""Lay a Conductor AST out as notation-only Codetta Score Model data."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from codetta import ast
from codetta.score_model import (Clef, KeySignature, Measure, Note, Part, Pitch,
                                 Rest, Score, Spanner, Staff, TimeSignature, Voice,
                                 validate_score)
from codetta.semantics import CodettaError

MAX_MEASURE_BEATS = 256


@dataclass(frozen=True)
class _Fragment:
    start: int
    end: int
    staff: int
    staff_count: int
    event_ids: tuple[str, ...]


def _staff_count(node: ast.Expression) -> int:
    if isinstance(node, ast.Integer):
        return 1
    if isinstance(node, (ast.Negate, ast.Reciprocal)):
        return _staff_count(node.body)
    if isinstance(node, ast.Sum):
        return max((_staff_count(term) for term in node.terms), default=1)
    if isinstance(node, ast.Product):
        return sum(_staff_count(factor) for factor in node.factors)
    raise TypeError(f"Unsupported AST node: {type(node).__name__}")


class _Builder:
    def __init__(self):
        self.events: dict[int, list[Note | Rest]] = {}
        self.event_positions: dict[str, tuple[int, int, int]] = {}
        self.spanners: list[Spanner] = []
        self.event_number = 0
        self.spanner_number = 0
        self.literal_number = 0

    def event_id(self) -> str:
        self.event_number += 1
        return f"event-{self.event_number}"

    def spanner_id(self) -> str:
        self.spanner_number += 1
        return f"spanner-{self.spanner_number}"

    def add_event(self, staff: int, event: Note | Rest, start: int, end: int) -> None:
        self.events.setdefault(staff, []).append(event)
        self.event_positions[event.id] = (start, end, staff)

    def rest(self, staff: int, start: int, duration: int) -> str:
        identifier = self.event_id()
        self.add_event(staff, Rest(identifier, Fraction(start, 4), Fraction(duration, 4)),
                       start, start + duration)
        return identifier

    def anchors(self, fragment: _Fragment) -> tuple[str, str]:
        first = min(fragment.event_ids,
                    key=lambda identifier: (self.event_positions[identifier][0],
                                            self.event_positions[identifier][2], identifier))
        last = max(fragment.event_ids,
                   key=lambda identifier: (self.event_positions[identifier][1],
                                           -self.event_positions[identifier][2], identifier))
        return first, last

    def group(self, kind: str, line_style: str, fragment: _Fragment, depth: int) -> None:
        first, last = self.anchors(fragment)
        self.spanners.append(Spanner(
            self.spanner_id(), kind, line_style, first, last,
            (fragment.staff, fragment.staff + fragment.staff_count - 1), (1, 1), depth,
        ))

    def layout(self, node: ast.Expression, start: int, staff: int, depth: int) -> _Fragment:
        if depth > 64:
            raise CodettaError("Conductor supports at most 64 nested expressions")
        if isinstance(node, ast.Integer):
            if node.value < 0:
                raise CodettaError("Integer nodes must be nonnegative; use Negate for a negative value")
            self.literal_number += 1
            if node.value == 0:
                identifier = self.rest(staff, start, 1)
                return _Fragment(start, start + 1, staff, 1, (identifier,))
            pitch = Pitch.from_midi(60 + (self.literal_number - 1) % 12)
            cursor = start
            identifiers = []
            remaining = node.value
            while remaining:
                duration = min(4, remaining)
                identifier = self.event_id()
                note = Note(identifier, Fraction(cursor, 4), Fraction(duration, 4), pitch)
                self.add_event(staff, note, cursor, cursor + duration)
                if identifiers:
                    self.spanners.append(Spanner(self.spanner_id(), "tie", "solid",
                                                 identifiers[-1], identifier, (staff, staff), (1, 1), depth))
                identifiers.append(identifier)
                cursor += duration
                remaining -= duration
            return _Fragment(start, cursor, staff, 1, tuple(identifiers))
        if isinstance(node, ast.Sum):
            if len(node.terms) < 2:
                raise CodettaError("A Sum needs at least two terms")
            cursor = start
            event_ids: list[str] = []
            count = _staff_count(node)
            for term in node.terms:
                child = self.layout(term, cursor, staff, depth + 1)
                cursor = child.end
                event_ids.extend(child.event_ids)
            fragment = _Fragment(start, cursor, staff, count, tuple(event_ids))
            self.group("slur", "solid", fragment, depth)
            return fragment
        if isinstance(node, ast.Product):
            if len(node.factors) < 2:
                raise CodettaError("A Product needs at least two factors")
            next_staff = staff
            children = []
            for factor in node.factors:
                child = self.layout(factor, start, next_staff, depth + 1)
                children.append(child)
                next_staff += child.staff_count
            end = max(child.end for child in children)
            event_ids = tuple(identifier for child in children for identifier in child.event_ids)
            fragment = _Fragment(start, end, staff, next_staff - staff, event_ids)
            self.group("bracket", "solid", fragment, depth)
            return fragment
        if isinstance(node, (ast.Negate, ast.Reciprocal)):
            child = self.layout(node.body, start, staff, depth + 1)
            kind = "slur" if isinstance(node, ast.Negate) else "bracket"
            self.group(kind, "dashed", child, depth)
            return child
        raise TypeError(f"Unsupported AST node: {type(node).__name__}")


def build_score(program: ast.Program, *, title: str = "Codetta program",
                fifths: int = 0, clef: str = "treble") -> Score:
    if not isinstance(program, ast.Program) or len(program.blocks) != 1:
        raise CodettaError("Conductor v0.1 accepts exactly one expression block")
    builder = _Builder()
    fragment = builder.layout(program.blocks[0].expression, 0, 1, 0)
    beats = max(1, fragment.end)
    if beats > MAX_MEASURE_BEATS:
        raise CodettaError(f"Expression needs {beats} quarter-note beats; the v0.1 limit is {MAX_MEASURE_BEATS}")
    staff_count = _staff_count(program.blocks[0].expression)
    clef_value = Clef("G", 2) if clef == "treble" else Clef("F", 4)
    time = TimeSignature(beats, 4)
    key = KeySignature(fifths)
    staves = []
    for staff_number in range(1, staff_count + 1):
        events = sorted(builder.events.get(staff_number, []), key=lambda event: (event.start, event.id))
        complete: list[Note | Rest] = []
        cursor = Fraction(0)
        for event in events:
            if event.start > cursor:
                gap = event.start - cursor
                identifier = builder.event_id()
                complete.append(Rest(identifier, cursor, gap))
                builder.event_positions[identifier] = (int(cursor * 4), int(event.start * 4), staff_number)
            complete.append(event)
            cursor = event.start + event.duration
        if cursor < time.duration:
            identifier = builder.event_id()
            complete.append(Rest(identifier, cursor, time.duration - cursor))
            builder.event_positions[identifier] = (int(cursor * 4), beats, staff_number)
        voice = Voice(f"voice-{staff_number}", staff_number, tuple(complete))
        measure = Measure(f"measure-{staff_number}-1", 1, time, key, clef_value,
                          (voice,), "light-heavy")
        staves.append(Staff(f"staff-{staff_number}", (measure,)))
    score = Score({"title": title}, (Part("part-1", tuple(staves)),), tuple(builder.spanners))
    return validate_score(score)

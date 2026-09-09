"""Derive the Codetta AST solely from notation in a validated Score Model."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from codetta import ast
from codetta.score_model import Chord, Event, Note, Rest, Score, Spanner, validate_score
from codetta.semantics import CodettaError


class ScoreSyntaxError(CodettaError):
    pass


@dataclass(frozen=True)
class _EventInfo:
    event: Event
    measure_id: str
    measure_number: int
    staff: int
    voice: int

    @property
    def start(self) -> Fraction:
        return self.event.start

    @property
    def end(self) -> Fraction:
        return self.event.start + self.event.duration


@dataclass(frozen=True)
class _Atom:
    expression: ast.Expression
    event_ids: frozenset[str]
    start: Fraction
    end: Fraction
    staff: int
    voice: int


@dataclass
class _Group:
    spanner: Spanner
    start: Fraction
    end: Fraction
    top: int
    bottom: int
    parent: _Group | None = None
    expression: ast.Expression | None = None

    def contains_group(self, other: _Group) -> bool:
        return (self.spanner.nesting_level < other.spanner.nesting_level
                and self.start <= other.start and other.end <= self.end
                and self.top <= other.top and other.bottom <= self.bottom)

    def contains_atom(self, atom: _Atom) -> bool:
        return (self.start <= atom.start and atom.end <= self.end
                and self.top <= atom.staff <= self.bottom)

    def contains_event(self, info: _EventInfo) -> bool:
        return (self.start <= info.start and info.end <= self.end
                and self.top <= info.staff <= self.bottom)


def _source(expressions: list[ast.Expression], group: _Group | None, measure_id: str) -> ast.SourceRef:
    event_ids: list[str] = []
    spanner_ids: list[str] = []
    for expression in expressions:
        event_ids.extend(expression.source_ref.event_ids)
        spanner_ids.extend(expression.source_ref.spanner_ids)
    if group is not None:
        spanner_ids.append(group.spanner.id)
    return ast.SourceRef(tuple(dict.fromkeys(event_ids)), tuple(dict.fromkeys(spanner_ids)), measure_id)


def _parse_measure(score: Score, measure_number: int) -> ast.Block:
    part = score.parts[0]
    infos: dict[str, _EventInfo] = {}
    measure_id = part.staves[0].measures[measure_number - 1].id
    for staff_number, staff in enumerate(part.staves, 1):
        measure = staff.measures[measure_number - 1]
        for voice_number, voice in enumerate(measure.voices, 1):
            for event in voice.events:
                if isinstance(event, Chord):
                    raise ScoreSyntaxError(f"Chord {event.id} has no computational meaning in Codetta v0.1")
                infos[event.id] = _EventInfo(event, measure_id, measure_number, staff_number, voice_number)

    spanners = [spanner for spanner in score.spanners if spanner.start_anchor in infos]
    ties = [spanner for spanner in spanners if spanner.type == "tie"]
    outgoing: dict[str, str] = {}
    incoming: dict[str, str] = {}
    tie_ids: dict[tuple[str, str], str] = {}
    for tie in ties:
        if tie.start_anchor in outgoing or tie.end_anchor in incoming:
            raise ScoreSyntaxError(f"Ambiguous tie chain at {tie.id}")
        outgoing[tie.start_anchor] = tie.end_anchor
        incoming[tie.end_anchor] = tie.start_anchor
        tie_ids[(tie.start_anchor, tie.end_anchor)] = tie.id

    atoms: list[_Atom] = []
    visited: set[str] = set()
    for identifier, info in infos.items():
        if not isinstance(info.event, Note) or identifier in incoming:
            continue
        chain = []
        current = identifier
        while current:
            if current in visited:
                raise ScoreSyntaxError(f"Tie cycle at event {current}")
            visited.add(current)
            chain.append(current)
            current = outgoing.get(current, "")
        members = [infos[item] for item in chain]
        duration = sum((member.event.duration for member in members), Fraction(0)) * 4
        if duration.denominator != 1 or duration <= 0:
            raise ScoreSyntaxError(f"Tied value at {identifier} is not a positive integer of quarter notes")
        refs = ast.SourceRef(tuple(chain), tuple(tie_ids[(a, b)] for a, b in zip(chain, chain[1:])), measure_id)
        atoms.append(_Atom(ast.Integer(duration.numerator, refs), frozenset(chain),
                           members[0].start, members[-1].end, info.staff, info.voice))
    unused_notes = set(identifier for identifier, info in infos.items() if isinstance(info.event, Note)) - visited
    if unused_notes:
        raise ScoreSyntaxError(f"Tie chain does not have a start: {sorted(unused_notes)[0]}")

    groups: list[_Group] = []
    for spanner in spanners:
        if spanner.type == "tie":
            continue
        start_info, end_info = infos[spanner.start_anchor], infos[spanner.end_anchor]
        top, bottom = spanner.staff_range or (min(start_info.staff, end_info.staff),
                                               max(start_info.staff, end_info.staff))
        groups.append(_Group(spanner, min(start_info.start, end_info.start),
                             max(start_info.end, end_info.end), top, bottom))

    def overlaps(left: _Group, right: _Group) -> bool:
        return (max(left.start, right.start) < min(left.end, right.end)
                and max(left.top, right.top) <= min(left.bottom, right.bottom))

    for index, group in enumerate(groups):
        for other in groups[index + 1:]:
            if not overlaps(group, other):
                continue
            if not group.contains_group(other) and not other.contains_group(group):
                raise ScoreSyntaxError(f"Spanners {group.spanner.id} and {other.spanner.id} cross ambiguously")
    for group in groups:
        candidates = [candidate for candidate in groups if candidate.contains_group(group)]
        if candidates:
            nearest_level = max(candidate.spanner.nesting_level for candidate in candidates)
            nearest = [candidate for candidate in candidates if candidate.spanner.nesting_level == nearest_level]
            if len(nearest) != 1:
                raise ScoreSyntaxError(f"Spanner {group.spanner.id} has an ambiguous parent")
            group.parent = nearest[0]

    rests = [info for info in infos.values() if isinstance(info.event, Rest)]

    def expression_for(group: _Group) -> ast.Expression:
        if group.expression is not None:
            return group.expression
        children = [candidate for candidate in groups if candidate.parent is group]
        child_atoms = [atom for atom in atoms if group.contains_atom(atom)
                       and not any(child.contains_atom(atom) for child in children)]
        child_rests = [info for info in rests if group.contains_event(info)
                       and not any(child.contains_event(info) for child in children)]
        child_expressions = [(child.start, child.top, expression_for(child)) for child in children]
        atom_expressions = [(atom.start, atom.staff, atom.expression) for atom in child_atoms]

        if group.spanner.type == "slur":
            items = child_expressions + atom_expressions
            for info in child_rests:
                if info.staff == group.top:
                    zero = ast.Integer(0, ast.SourceRef((info.event.id,), (), measure_id))
                    items.append((info.start, info.staff, zero))
            items.sort(key=lambda item: (item[0], item[1]))
            expressions = [item[2] for item in items]
            if group.spanner.line_style == "dashed":
                if len(expressions) != 1:
                    raise ScoreSyntaxError(f"Dashed slur {group.spanner.id} must enclose one expression")
                group.expression = ast.Negate(expressions[0], _source(expressions, group, measure_id))
            else:
                if len(expressions) < 2:
                    raise ScoreSyntaxError(f"Solid slur {group.spanner.id} must join at least two expressions")
                group.expression = ast.Sum(tuple(expressions), _source(expressions, group, measure_id))
            return group.expression

        occupied: set[int] = set()
        factors: list[tuple[int, ast.Expression]] = []
        for child in children:
            factors.append((child.top, expression_for(child)))
            occupied.update(range(child.top, child.bottom + 1))
        for staff in range(group.top, group.bottom + 1):
            if staff in occupied:
                continue
            lane = sorted((atom for atom in child_atoms if atom.staff == staff), key=lambda atom: atom.start)
            if len(lane) == 1:
                expression = lane[0].expression
            elif len(lane) > 1:
                expressions = [atom.expression for atom in lane]
                expression = ast.Sum(tuple(expressions), _source(expressions, None, measure_id))
            else:
                lane_rests = [info for info in child_rests if info.staff == staff]
                if not lane_rests:
                    continue
                expression = ast.Integer(0, ast.SourceRef(tuple(info.event.id for info in lane_rests), (), measure_id))
            factors.append((staff, expression))
        factors.sort(key=lambda item: item[0])
        expressions = [item[1] for item in factors]
        if group.spanner.line_style == "dashed":
            if len(expressions) != 1:
                raise ScoreSyntaxError(f"Dashed bracket {group.spanner.id} must enclose one expression")
            group.expression = ast.Reciprocal(expressions[0], _source(expressions, group, measure_id))
        else:
            if len(expressions) < 2:
                raise ScoreSyntaxError(f"Solid bracket {group.spanner.id} must join at least two voices")
            group.expression = ast.Product(tuple(expressions), _source(expressions, group, measure_id))
        return group.expression

    roots = [group for group in groups if group.parent is None]
    covered_atoms = {id(atom) for root in roots for atom in atoms if root.contains_atom(atom)}
    bare_atoms = [atom for atom in atoms if id(atom) not in covered_atoms]
    expressions = [(root.start, root.top, expression_for(root)) for root in roots]
    expressions.extend((atom.start, atom.staff, atom.expression) for atom in bare_atoms)
    expressions.sort(key=lambda item: (item[0], item[1]))
    if not expressions:
        event_ids = tuple(info.event.id for info in rests)
        result: ast.Expression = ast.Integer(0, ast.SourceRef(event_ids, (), measure_id))
    elif len(expressions) == 1:
        result = expressions[0][2]
    elif len({staff for _, staff, _ in expressions}) == 1:
        values = [item[2] for item in expressions]
        result = ast.Sum(tuple(values), _source(values, None, measure_id))
    else:
        raise ScoreSyntaxError(f"Measure {measure_number} has ungrouped simultaneous voices")
    all_event_ids = tuple(info.event.id for info in infos.values())
    return ast.Block(result, ast.SourceRef(all_event_ids, tuple(spanner.id for spanner in spanners), measure_id))


def parse_score(score: Score) -> ast.Program:
    validate_score(score)
    for staff in score.parts[0].staves:
        for index, measure in enumerate(staff.measures):
            expected = "light-heavy" if index == len(staff.measures) - 1 else "regular"
            if measure.barline != expected:
                raise ScoreSyntaxError("Only the final measure may use the output light-heavy barline")
    measures = len(score.parts[0].staves[0].measures)
    try:
        return ast.Program(tuple(_parse_measure(score, number) for number in range(1, measures + 1)))
    except RecursionError as exc:
        raise ScoreSyntaxError("Score grouping is too deeply nested") from exc

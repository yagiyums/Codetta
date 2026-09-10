"""Derive the Codetta v0.2 AST from musical score structures."""

from __future__ import annotations

from dataclasses import fields, is_dataclass

from codetta import ast
from codetta.score_model import Cue, Note, Rest, Score, validate_score
from codetta.semantics import CodettaError


class V02ScoreSyntaxError(CodettaError):
    pass


def _same_syntax(left: object, right: object) -> bool:
    """Compare AST meaning while ignoring score provenance."""
    if type(left) is not type(right):
        return False
    if is_dataclass(left):
        return all(field.name in ("source", "source_ref")
                   or _same_syntax(getattr(left, field.name), getattr(right, field.name))
                   for field in fields(left))
    if isinstance(left, tuple):
        return len(left) == len(right) and all(_same_syntax(a, b) for a, b in zip(left, right))
    return left == right


class _Parser:
    def __init__(self, score: Score):
        self.score = validate_score(score)
        self.part = score.parts[0]
        self.measure_ids = [measure.id for measure in self.part.staves[0].measures]
        self.measure_index = {identifier: index for index, identifier in enumerate(self.measure_ids)}
        self.events: dict[str, object] = {}
        self.event_voice: dict[str, str] = {}
        self.event_measure: dict[str, int] = {}
        self.measure_events: dict[int, list[tuple[str, object]]] = {}
        self.voices = {}
        for staff in self.part.staves:
            for index, measure in enumerate(staff.measures):
                for voice in measure.voices:
                    self.voices.setdefault(voice.id, voice)
                    for event in voice.events:
                        self.events[event.id] = event
                        self.event_voice[event.id] = voice.id
                        self.event_measure[event.id] = index
                        self.measure_events.setdefault(index, []).append((voice.id, event))
        self.relation_output = {item.output_anchor: item for item in score.relations}
        self.phrase_output = {item.output_anchor: item for item in score.phrases}
        self.group_output = {item.output_anchor: item for item in score.voice_groups
                             if item.output_anchor is not None}
        self.reference_output = {item.anchor: item for item in score.section_references}
        self.sections = {item.id: item for item in score.sections}
        self.decoding: set[str] = set()
        self.phrase_elements: dict[str, tuple[str, ...]] = {
            phrase.id: self._phrase_elements(phrase) for phrase in score.phrases
        }
        self.consumed = {anchor for item in score.relations for anchor in item.input_anchors}
        # A tied note is one sustained value.  Only its first attack can update
        # the named Voice; continuation notes extend lifetime without assigning.
        self.consumed.update(item.end_anchor for item in score.spanners if item.type == "tie")
        for values in self.phrase_elements.values():
            self.consumed.update(values)
        for group in score.voice_groups:
            if group.output_anchor is None:
                continue
            measure = self.event_measure[group.output_anchor]
            for voice_id in group.voice_ids:
                self.consumed.update(event.id for candidate, event in self.measure_events.get(measure, ())
                                     if candidate == voice_id)

    def voice_name(self, voice_id: str) -> str:
        voice = self.voices.get(voice_id)
        if voice is None or voice.name is None:
            raise V02ScoreSyntaxError(f"Voice {voice_id} needs a name in this relation")
        return voice.name

    def _phrase_elements(self, phrase) -> tuple[str, ...]:
        measure = self.event_measure[phrase.output_anchor]
        candidates = [event for voice_id, event in self.measure_events.get(measure, ())
                      if voice_id in phrase.voice_ids]
        candidates.sort(key=lambda item: (item.start, item.id))
        identifiers = [item.id for item in candidates]
        try:
            first = identifiers.index(phrase.start_anchor)
            last = identifiers.index(phrase.end_anchor)
        except ValueError as exc:
            raise V02ScoreSyntaxError(f"Phrase {phrase.id} anchors are not in its Voices") from exc
        if first > last:
            raise V02ScoreSyntaxError(f"Phrase {phrase.id} runs backwards")
        return tuple(identifiers[first:last + 1])

    def expression(self, anchor: str) -> ast.ExpressionV02:
        if anchor in self.decoding:
            raise V02ScoreSyntaxError(f"Cyclic notation relation at {anchor}")
        self.decoding.add(anchor)
        try:
            source = ast.SourceRef((anchor,), (), self.measure_ids[self.event_measure[anchor]])
            if anchor in self.reference_output:
                reference = self.reference_output[anchor]
                section = self.sections[reference.section_id]
                return ast.FunctionCall(section.name, tuple(
                    ast.VariableRef(self.voice_name(voice_id))
                    for voice_id in reference.argument_voice_ids
                ), source)
            if anchor in self.phrase_output:
                phrase = self.phrase_output[anchor]
                return ast.ArrayLiteral(tuple(self.expression(item)
                                              for item in self.phrase_elements[phrase.id]), source)
            if anchor in self.group_output:
                group = self.group_output[anchor]
                measure = self.event_measure[anchor]
                fields = []
                for voice_id in group.voice_ids:
                    values = [event.id for candidate, event in self.measure_events.get(measure, ())
                              if candidate == voice_id]
                    if len(values) != 1:
                        raise V02ScoreSyntaxError(
                            f"Struct Voice {voice_id} needs one value at its group onset"
                        )
                    fields.append((self.voice_name(voice_id), self.expression(values[0])))
                return ast.StructLiteral(tuple(fields), source)
            relation = self.relation_output.get(anchor)
            if relation is not None:
                inputs = tuple(self.expression(item) for item in relation.input_anchors)
                if relation.connector == "slur":
                    return ast.Sum(inputs, source)
                if relation.connector == "bracket":
                    return ast.Product(inputs, source)
                if relation.connector == "dashed-slur" and len(inputs) == 1:
                    return ast.Negate(inputs[0], source)
                if relation.connector == "dashed-bracket" and len(inputs) == 1:
                    return ast.Reciprocal(inputs[0], source)
                if relation.connector in ("hairpin-crescendo", "hairpin-diminuendo", "unison"):
                    if len(inputs) != 2:
                        raise V02ScoreSyntaxError("A comparison relation needs two values")
                    operator = {"hairpin-crescendo": "<", "hairpin-diminuendo": ">",
                                "unison": "=="}[relation.connector]
                    return ast.Comparison(operator, inputs[0], inputs[1], source)
                if relation.connector == "scalar-stack":
                    if len(inputs) != 2:
                        raise V02ScoreSyntaxError("A Float scalar stack needs two components")
                    significand = self._signed_integer(inputs[0])
                    exponent = self._signed_integer(inputs[1])
                    return ast.FloatLiteral(significand, exponent, source)
                if relation.connector == "application" and len(inputs) == 2:
                    return ast.ArrayAccess(inputs[0], inputs[1], source)
                if relation.connector == "field" and len(inputs) == 1 and relation.field_voice_id:
                    return ast.FieldAccess(inputs[0], self.voice_name(relation.field_voice_id), source)
                raise V02ScoreSyntaxError(f"Invalid {relation.connector} relation {relation.id}")
            event = self.events[anchor]
            if isinstance(event, Cue):
                return ast.VariableRef(self.voice_name(event.source_voice_id), source)
            if isinstance(event, Rest):
                return ast.Integer(0, source)
            if isinstance(event, Note):
                value = event.duration * 4
                if value.denominator != 1:
                    raise V02ScoreSyntaxError(f"Int event {event.id} is not a whole quarter-note count")
                return ast.Integer(value.numerator, source)
            raise V02ScoreSyntaxError(f"Event {anchor} cannot be used as a v0.2 value")
        finally:
            self.decoding.remove(anchor)

    @staticmethod
    def _signed_integer(node: ast.ExpressionV02) -> int:
        if isinstance(node, ast.Integer):
            return node.value
        if isinstance(node, (ast.Negate, ast.UnaryExpr)) and isinstance(node.body, ast.Integer):
            return -node.body.value
        raise V02ScoreSyntaxError("Float components must be notated integers")

    def assignment_for_voice(self, index: int, voice_id: str) -> ast.Assignment | None:
        candidates = [(event.start, event.id) for candidate, event in self.measure_events.get(index, ())
                      if candidate == voice_id and (
                          event.id in self.relation_output or event.id in self.phrase_output
                          or event.id in self.group_output or event.id in self.reference_output
                          or event.id not in self.consumed)]
        if not candidates:
            return None
        candidates.sort()
        if len(candidates) != 1:
            raise V02ScoreSyntaxError(f"Voice {voice_id} has ambiguous assignments in one measure")
        return ast.Assignment(self.voice_name(voice_id), self.expression(candidates[0][1]))

    def plain_measure(self, index: int, excluded: set[str] = frozenset()) -> tuple[ast.Statement, ...]:
        result = []
        seen = set()
        for voice_id, _ in self.measure_events.get(index, ()):
            if voice_id in seen or voice_id in excluded or self.voices[voice_id].name is None:
                continue
            seen.add(voice_id)
            assignment = self.assignment_for_voice(index, voice_id)
            if assignment is not None:
                result.append(assignment)
        return tuple(result)

    def condition(self, voice_id: str) -> tuple[int, ast.ExpressionV02]:
        locations = sorted({index for index, values in self.measure_events.items()
                            if any(candidate == voice_id for candidate, _ in values)})
        if len(locations) != 1:
            raise V02ScoreSyntaxError(f"Condition Voice {voice_id} needs one notation point")
        assignment = self.assignment_for_voice(locations[0], voice_id)
        if assignment is None:
            raise V02ScoreSyntaxError(f"Condition Voice {voice_id} has no value")
        return locations[0], assignment.value

    def statements(self, first: int, last: int,
                   ignored: frozenset[str] = frozenset()) -> tuple[ast.Statement, ...]:
        result: list[ast.Statement] = []
        repeat_by_start = {self.measure_index[item.start_measure]: item for item in self.score.repeats
                           if item.id not in ignored
                           and first <= self.measure_index[item.start_measure] <= last}
        volta_by_condition = {}
        for item in self.score.voltas:
            index, condition = self.condition(item.condition_voice_id)
            if item.id not in ignored and first <= index <= last:
                volta_by_condition[index] = (item, condition)
        index = first
        while index <= last:
            if index in volta_by_condition:
                volta, condition = volta_by_condition[index]
                ordered = sorted(volta.endings, key=lambda item: min(item.numbers))
                nested_ignored = ignored | {volta.id}
                bodies = [self.statements(self.measure_index[item.start_measure],
                                          self.measure_index[item.end_measure], nested_ignored)
                          for item in ordered]
                # A one-ending volta guarding an equivalent native post-test
                # repeat is the score spelling of a conventional pre-test while.
                guarded = bodies[0]
                if (len(bodies) == 1 and len(guarded) == 1
                        and isinstance(guarded[0], ast.While) and guarded[0].test_at_end
                        and _same_syntax(condition, guarded[0].condition)):
                    result.append(ast.While(condition, guarded[0].body, False))
                else:
                    result.append(ast.If(condition, guarded,
                                         bodies[1] if len(bodies) > 1 else ()))
                index = max(self.measure_index[item.end_measure] for item in ordered) + 1
                continue
            repeat = repeat_by_start.get(index)
            if repeat is not None:
                end = self.measure_index[repeat.end_measure]
                if repeat.condition_voice_id is not None:
                    condition_index, condition = self.condition(repeat.condition_voice_id)
                    if repeat.test_at_end:
                        if condition_index != end:
                            raise V02ScoreSyntaxError(
                                f"Post-test repeat {repeat.id} needs its condition at the end"
                            )
                        body = self.statements(index, condition_index - 1,
                                               ignored | {repeat.id})
                    else:
                        if condition_index != index:
                            raise V02ScoreSyntaxError(
                                f"Pre-test repeat {repeat.id} needs its condition at the start"
                            )
                        body = self.statements(condition_index + 1, end,
                                               ignored | {repeat.id}) if condition_index < end else ()
                    result.append(ast.While(condition, body, repeat.test_at_end))
                else:
                    if repeat.times is not None:
                        iterable: ast.ExpressionV02 = ast.Integer(repeat.times)
                    elif repeat.collection_voice_id is not None:
                        iterable = ast.FunctionCall("length", (
                            ast.VariableRef(self.voice_name(repeat.collection_voice_id)),
                        ))
                    else:
                        iterable = ast.VariableRef(self.voice_name(repeat.count_voice_id))
                    iterator = self.voice_name(repeat.iterator_voice_id)
                    result.append(ast.For(iterator, iterable,
                                          self.statements(index, end, ignored | {repeat.id})))
                index = end + 1
                continue
            excluded = {item.condition_voice_id for item in self.score.voltas}
            excluded.update(item.condition_voice_id for item in self.score.repeats
                            if item.condition_voice_id is not None)
            result.extend(self.plain_measure(index, excluded))
            index += 1
        return tuple(result)

    def parse(self) -> ast.Program:
        functions = []
        section_ranges = []
        for section in self.score.sections:
            first = self.measure_index[section.start_measure]
            last = self.measure_index[section.end_measure]
            section_ranges.append((first, last))
            body = list(self.statements(first, last))
            if section.return_voice_ids:
                if len(section.return_voice_ids) != 1:
                    raise V02ScoreSyntaxError("v0.2 currently supports one return Voice")
                body.append(ast.Return(ast.VariableRef(self.voice_name(section.return_voice_ids[0]))))
            else:
                body.append(ast.Return(None))
            functions.append(ast.FunctionDecl(
                section.name, tuple(self.voice_name(item) for item in section.parameter_voice_ids),
                tuple(body), ast.SourceRef(structure_ids=(section.id,)),
            ))
        main: list[ast.Statement] = []
        index = 0
        for first, last in sorted(section_ranges):
            if index < first:
                main.extend(self.statements(index, first - 1))
            index = max(index, last + 1)
        if index < len(self.measure_ids):
            main.extend(self.statements(index, len(self.measure_ids) - 1))
        return ast.Program(statements=tuple(main), functions=tuple(functions), language_version="0.2")


def parse_score(score: Score) -> ast.Program:
    if score.language_version != "0.2":
        raise V02ScoreSyntaxError("v0.2 parser needs a v0.2 score")
    return _Parser(score).parse()

"""Lay a Codetta v0.2 AST out as notation-centred score structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction

from codetta import ast
from codetta.score_model import (Clef, Cue, KeySignature, Measure, Note, Part,
                                 PhraseRegion, Pitch, Relation, RepeatRegion,
                                 Rest, Score, Section, SectionReference, Spanner, Staff,
                                 TimeSignature, Voice, VoiceGroup, VoltaEnding,
                                 VoltaGroup, validate_score)
from codetta.semantics import CodettaError


@dataclass
class _Voice:
    id: str
    name: str | None
    staff: int
    lane: int


@dataclass
class _Measure:
    events: dict[str, list[Note | Rest | Cue]] = field(default_factory=dict)
    beats: int = 1


class _Builder:
    def __init__(self, title: str):
        self.title = title
        self.voices: list[_Voice] = []
        self.variables: dict[tuple[str, str], _Voice] = {}
        self.measures: list[_Measure] = []
        self.relations: list[Relation] = []
        self.phrases: list[PhraseRegion] = []
        self.groups: list[VoiceGroup] = []
        self.sections: list[Section] = []
        self.references: list[SectionReference] = []
        self.repeats: list[RepeatRegion] = []
        self.voltas: list[VoltaGroup] = []
        self.section_ids: dict[str, str] = {}
        self.number = 0
        self.condition_number = 0

    def identifier(self, prefix: str) -> str:
        self.number += 1
        return f"{prefix}-{self.number}"

    def voice(self, name: str | None = None, scope: str = "temporary") -> _Voice:
        if name is not None:
            key = (scope, name)
            if key in self.variables:
                return self.variables[key]
        item = _Voice(self.identifier("voice"), name,
                      len(self.voices) // 4 + 1, len(self.voices) % 4 + 1)
        self.voices.append(item)
        if name is not None:
            self.variables[(scope, name)] = item
        return item

    def variable(self, scope: str, name: str) -> _Voice:
        return self.voice(name, scope)

    def measure(self) -> int:
        self.measures.append(_Measure())
        return len(self.measures) - 1

    def event(self, measure: int, voice: _Voice, start: int = 0, duration: int = 1,
              *, zero: bool = False, cue: _Voice | None = None) -> str:
        if duration <= 0:
            raise CodettaError("A notated value must have positive duration")
        identifier = self.identifier("event")
        begin, length = Fraction(start, 4), Fraction(duration, 4)
        pitch = Pitch.from_midi(48 + ((voice.staff - 1) * 7) % 30 + (voice.lane - 1) * 2)
        if cue is not None:
            item: Note | Rest | Cue = Cue(identifier, begin, length, cue.id, pitch)
        elif zero:
            item = Rest(identifier, begin, length)
        else:
            item = Note(identifier, begin, length, pitch)
        self.measures[measure].events.setdefault(voice.id, []).append(item)
        self.measures[measure].beats = max(self.measures[measure].beats, start + duration)
        return identifier

    def carrier(self, measure: int, voice: _Voice, start: int = 0) -> str:
        return self.event(measure, voice, start, 1)

    def expression(self, node: ast.ExpressionV02, measure: int, scope: str,
                   output: _Voice | None = None, start: int = 0) -> str:
        destination = output or self.voice()
        if isinstance(node, ast.Integer):
            if node.value < 0 or node.value > 4096:
                raise CodettaError("A v0.2 Int notation must be between 0 and 4096")
            return self.event(measure, destination, start, max(1, node.value), zero=node.value == 0)
        if isinstance(node, ast.FloatLiteral):
            significand_voice = self.voice()
            exponent_voice = self.voice()
            significand_node: ast.ExpressionV02 = ast.Integer(abs(node.significand))
            if node.significand < 0:
                significand_node = ast.UnaryExpr("-", significand_node)
            significand = self.expression(significand_node, measure, scope,
                                           significand_voice, start)
            exponent_node: ast.ExpressionV02 = ast.Integer(abs(node.exponent))
            if node.exponent < 0:
                exponent_node = ast.UnaryExpr("-", exponent_node)
            exponent = self.expression(exponent_node, measure, scope, exponent_voice, start)
            result = self.carrier(measure, destination, start)
            self.relations.append(Relation(self.identifier("relation"), "scalar-stack",
                                           (significand, exponent), result))
            return result
        if isinstance(node, ast.BoolLiteral):
            left = self.expression(ast.Integer(1), measure, scope)
            right = self.expression(ast.Integer(1 if node.value else 0), measure, scope)
            result = self.carrier(measure, destination, start)
            self.relations.append(Relation(self.identifier("relation"), "unison",
                                           (left, right), result))
            return result
        if isinstance(node, ast.VariableRef):
            source = self.variables.get((scope, node.name))
            if source is None:
                # Parameters are registered before their section body is laid out.
                source = self.variable(scope, node.name)
            return self.event(measure, destination, start, 1, cue=source)
        if isinstance(node, ast.Negate):
            return self.expression(ast.UnaryExpr("-", node.body), measure, scope, destination, start)
        if isinstance(node, ast.Reciprocal):
            value = self.expression(node.body, measure, scope)
            result = self.carrier(measure, destination, start)
            self.relations.append(Relation(self.identifier("relation"), "dashed-bracket",
                                           (value,), result))
            return result
        if isinstance(node, ast.UnaryExpr):
            if node.operator == "not":
                return self.expression(ast.Comparison("==", node.body, ast.BoolLiteral(False)),
                                       measure, scope, destination, start)
            value = self.expression(node.body, measure, scope)
            result = self.carrier(measure, destination, start)
            self.relations.append(Relation(self.identifier("relation"), "dashed-slur",
                                           (value,), result))
            return result
        if isinstance(node, (ast.Sum, ast.Product)):
            values = node.terms if isinstance(node, ast.Sum) else node.factors
            connector = "slur" if isinstance(node, ast.Sum) else "bracket"
            inputs = tuple(self.expression(value, measure, scope) for value in values)
            result = self.carrier(measure, destination, start)
            self.relations.append(Relation(self.identifier("relation"), connector, inputs, result))
            return result
        if isinstance(node, ast.BinaryExpr):
            if node.operator == "-":
                right = ast.UnaryExpr("-", node.right)
                return self.expression(ast.Sum((node.left, right)), measure, scope, destination, start)
            if node.operator == "/":
                right = ast.Reciprocal(node.right)
                return self.expression(ast.Product((node.left, right)), measure, scope, destination, start)
            connector = {"+": "slur", "*": "bracket"}.get(node.operator)
            if connector is None:
                raise CodettaError(f"Unsupported score operator {node.operator}")
            inputs = (self.expression(node.left, measure, scope),
                      self.expression(node.right, measure, scope))
            result = self.carrier(measure, destination, start)
            self.relations.append(Relation(self.identifier("relation"), connector, inputs, result))
            return result
        if isinstance(node, ast.Comparison):
            connector = {"<": "hairpin-crescendo", ">": "hairpin-diminuendo",
                         "==": "unison"}.get(node.operator)
            if connector is None:
                raise CodettaError(f"Unsupported score comparison {node.operator}")
            inputs = (self.expression(node.left, measure, scope),
                      self.expression(node.right, measure, scope))
            result = self.carrier(measure, destination, start)
            self.relations.append(Relation(self.identifier("relation"), connector, inputs, result))
            return result
        if isinstance(node, ast.ArrayLiteral):
            if not node.elements:
                raise CodettaError("Empty Array notation needs an inferred element type")
            element_voice = self.voice()
            cursor = start
            elements = []
            for element in node.elements:
                anchor = self.expression(element, measure, scope, element_voice, cursor)
                elements.append(anchor)
                event = next(item for item in self.measures[measure].events[element_voice.id]
                             if item.id == anchor)
                cursor = max(cursor + 1, int((event.start + event.duration) * 4))
            result = self.carrier(measure, destination, start)
            self.phrases.append(PhraseRegion(self.identifier("phrase"), elements[0], elements[-1],
                                             (element_voice.id,), result))
            return result
        if isinstance(node, ast.StructLiteral):
            field_voices = []
            for field_name, value in node.fields:
                field_voice = self.voice(field_name, self.identifier("record-scope"))
                self.expression(value, measure, scope, field_voice, start)
                field_voices.append(field_voice)
            result = self.carrier(measure, destination, start)
            self.groups.append(VoiceGroup(self.identifier("voice-group"),
                                          destination.name or "record",
                                          tuple(item.id for item in field_voices), result))
            return result
        if isinstance(node, ast.ArrayAccess):
            inputs = (self.expression(node.array, measure, scope),
                      self.expression(node.index, measure, scope))
            result = self.carrier(measure, destination, start)
            self.relations.append(Relation(self.identifier("relation"), "application", inputs, result))
            return result
        if isinstance(node, ast.FieldAccess):
            value = self.expression(node.value, measure, scope)
            selector = self.voice(node.field_name, self.identifier("field-scope"))
            result = self.carrier(measure, destination, start)
            self.relations.append(Relation(self.identifier("relation"), "field", (value,), result,
                                           selector.id))
            return result
        if isinstance(node, ast.FunctionCall):
            if any(not isinstance(argument, ast.VariableRef) for argument in node.arguments):
                raise CodettaError("Score function calls currently require argument Voices")
            section_id = self.section_ids.get(node.function_name)
            if section_id is None:
                raise CodettaError(f"Unknown function section {node.function_name}")
            arguments = tuple(self.variable(scope, argument.name).id for argument in node.arguments)
            result = self.carrier(measure, destination, start)
            self.references.append(SectionReference(self.identifier("section-reference"), section_id,
                                                    result, arguments, (destination.id,)))
            return result
        raise CodettaError(f"Cannot notate {type(node).__name__}")

    def assignment(self, node: ast.Assignment, scope: str) -> list[int]:
        measure = self.measure()
        self.expression(node.value, measure, scope, self.variable(scope, node.target))
        return [measure]

    def statements(self, nodes: tuple[ast.Statement, ...], scope: str) -> list[int]:
        result: list[int] = []
        for node in nodes:
            if isinstance(node, ast.Assignment):
                result.extend(self.assignment(node, scope))
            elif isinstance(node, ast.If):
                condition_measure = self.measure()
                self.condition_number += 1
                condition = self.variable(scope, f"condition_{self.condition_number}")
                self.expression(node.condition, condition_measure, scope, condition)
                true_measures = self.statements(node.true_body, scope) or [self.measure()]
                false_measures = self.statements(node.false_body, scope) if node.false_body else []
                endings = [VoltaEnding((1,), self.measure_id(true_measures[0]),
                                       self.measure_id(true_measures[-1]))]
                if false_measures:
                    endings.append(VoltaEnding((2,), self.measure_id(false_measures[0]),
                                               self.measure_id(false_measures[-1])))
                self.voltas.append(VoltaGroup(self.identifier("volta"), condition.id, tuple(endings)))
                result.extend([condition_measure, *true_measures, *false_measures])
            elif isinstance(node, ast.For):
                prefix: list[int] = []
                iterator = self.variable(scope, node.iterator)
                times = None
                count_voice = None
                collection_voice = None
                if isinstance(node.iterable, ast.Integer):
                    times = node.iterable.value
                elif isinstance(node.iterable, ast.VariableRef):
                    count_voice = self.variable(scope, node.iterable.name).id
                elif (isinstance(node.iterable, ast.FunctionCall)
                      and node.iterable.function_name in ("len", "length")
                      and len(node.iterable.arguments) == 1
                      and isinstance(node.iterable.arguments[0], ast.VariableRef)):
                    collection_voice = self.variable(scope, node.iterable.arguments[0].name).id
                else:
                    count_name = f"count_{self.identifier('loop')}"
                    prefix = self.assignment(ast.Assignment(count_name, node.iterable), scope)
                    count_voice = self.variable(scope, count_name).id
                body = self.statements(node.body, scope) or [self.measure()]
                self.repeats.append(RepeatRegion(self.identifier("repeat"), self.measure_id(body[0]),
                                                 self.measure_id(body[-1]), iterator.id, times,
                                                 count_voice, collection_voice))
                result.extend([*prefix, *body])
            elif isinstance(node, ast.While):
                guard_measure = None
                guard = None
                if not node.test_at_end:
                    self.condition_number += 1
                    guard_measure = self.measure()
                    guard = self.variable(scope, f"condition_{self.condition_number}")
                    self.expression(node.condition, guard_measure, scope, guard)
                body = self.statements(node.body, scope) or [self.measure()]
                condition_measure = self.measure()
                self.condition_number += 1
                condition = self.variable(scope, f"condition_{self.condition_number}")
                self.expression(node.condition, condition_measure, scope, condition)
                self.repeats.append(RepeatRegion(self.identifier("repeat"),
                                                 self.measure_id(body[0]),
                                                 self.measure_id(condition_measure), condition_voice_id=condition.id,
                                                 test_at_end=True))
                # The conditional repeat itself is the native post-test form.  A
                # pre-test while adds a first-pass volta guard so zero iterations
                # remain possible without inventing an opcode.
                if node.test_at_end:
                    result.extend([*body, condition_measure])
                else:
                    self.voltas.append(VoltaGroup(
                        self.identifier("volta"), guard.id,
                        (VoltaEnding((1,), self.measure_id(body[0]),
                                     self.measure_id(condition_measure)),),
                    ))
                    result.extend([guard_measure, *body, condition_measure])
            elif isinstance(node, ast.Return):
                raise CodettaError("Return must be the final statement of a function section")
            else:
                raise CodettaError(f"Cannot notate statement {type(node).__name__}")
        return result

    @staticmethod
    def measure_id(index: int, staff: int = 1) -> str:
        return f"measure-{staff}-{index + 1}"

    def function(self, declaration: ast.FunctionDecl, mark: str) -> None:
        scope = f"function:{declaration.name}"
        parameters = tuple(self.variable(scope, name) for name in declaration.parameters)
        terminal = declaration.body[-1] if declaration.body else None
        if not isinstance(terminal, ast.Return):
            raise CodettaError(f"Function {declaration.name} needs a final return")
        body = self.statements(declaration.body[:-1], scope)
        if terminal.value is None:
            returns: tuple[_Voice, ...] = ()
        elif isinstance(terminal.value, ast.VariableRef):
            returns = (self.variable(scope, terminal.value.name),)
        else:
            return_voice = self.variable(scope, f"return_{declaration.name}")
            measure = self.measure()
            self.expression(terminal.value, measure, scope, return_voice)
            body.append(measure)
            returns = (return_voice,)
        if not body:
            body.append(self.measure())
        self.sections.append(Section(self.section_ids[declaration.name], declaration.name, mark,
                                     self.measure_id(body[0]), self.measure_id(body[-1]),
                                     tuple(item.id for item in parameters),
                                     tuple(item.id for item in returns)))

    def build(self, program: ast.Program) -> Score:
        for index, function in enumerate(program.functions):
            self.section_ids[function.name] = f"section-{index + 1}"
        for index, function in enumerate(program.functions):
            self.function(function, chr(ord("A") + index % 26))
        self.statements(program.statements, "main")
        if not self.measures:
            self.measure()
        beats = max(measure.beats for measure in self.measures)
        if beats > 4096:
            raise CodettaError("Codetta v0.2 canonical layout supports at most 4,096 beats per measure")
        time = TimeSignature(beats, 4)
        key = KeySignature(0)
        staves = []
        staff_count = max(definition.staff for definition in self.voices)
        for staff_number in range(1, staff_count + 1):
            definitions = [item for item in self.voices if item.staff == staff_number]
            measures = []
            for index, source in enumerate(self.measures):
                voices = tuple(Voice(
                    definition.id, definition.staff,
                    tuple(sorted(source.events.get(definition.id, ()),
                                 key=lambda item: (item.start, item.id))),
                    definition.name,
                ) for definition in definitions)
                barline = "light-heavy" if index == len(self.measures) - 1 else "regular"
                measures.append(Measure(self.measure_id(index, staff_number), index + 1,
                                        time, key, Clef("G", 2), voices, barline))
            staves.append(Staff(f"staff-{staff_number}", tuple(measures)))
        display_spanners = []
        styles = {
            "slur": ("slur", "solid"), "bracket": ("bracket", "solid"),
            "dashed-slur": ("slur", "dashed"),
            "dashed-bracket": ("bracket", "dashed"),
        }
        for depth, relation in enumerate(self.relations):
            style = styles.get(relation.connector)
            if style is None:
                continue
            anchors = relation.input_anchors
            start, end = ((anchors[0], anchors[-1]) if len(anchors) > 1
                          else (anchors[0], relation.output_anchor))
            display_spanners.append(Spanner(
                f"display-{relation.id}", style[0], style[1], start, end,
                nesting_level=depth % 8,
            ))
        score = Score({"title": self.title}, (Part("part-1", tuple(staves)),),
                      tuple(display_spanners), "0.2", "0.2",
                      tuple(self.groups), tuple(self.phrases), tuple(self.relations),
                      tuple(self.sections), tuple(self.references), tuple(self.repeats),
                      tuple(self.voltas))
        return validate_score(score)


def build_score(program: ast.Program, *, title: str = "Codetta v0.2 program") -> Score:
    if not isinstance(program, ast.Program) or program.language_version != "0.2":
        raise CodettaError("v0.2 score builder needs a Codetta v0.2 Program")
    return _Builder(title).build(program)

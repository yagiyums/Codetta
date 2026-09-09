"""Public Conductor pipeline from an arithmetic expression to Score Model."""

from codetta.ast import Program
from codetta.score_model import Score
from conductor.parser import parse
from conductor.score_builder import build_score


def compile_ast(program: Program, *, title: str = "Codetta program",
                fifths: int = 0, clef: str = "treble") -> Score:
    return build_score(program, title=title, fifths=fifths, clef=clef)


def compile_expression(source: str, *, title: str = "Codetta program",
                       fifths: int = 0, clef: str = "treble") -> Score:
    return compile_ast(parse(source), title=title, fifths=fifths, clef=clef)

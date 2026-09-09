"""Load .codetta and derive its AST and execution IR."""

from dataclasses import dataclass
from pathlib import Path

from codetta import ast, ir
from codetta.score_model import Score
from codetta.score_parser import parse_score
from codetta.semantic_analyzer import analyze
from codetta.serialization import read_score as deserialize_score


@dataclass(frozen=True)
class LoadedProgram:
    score: Score
    syntax: ast.Program
    execution: ir.Program


def read_score(path: str | Path) -> Score:
    return deserialize_score(path)


def read_program(path: str | Path) -> LoadedProgram:
    score = read_score(path)
    syntax = parse_score(score)
    return LoadedProgram(score, syntax, analyze(syntax))

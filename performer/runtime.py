"""Complete Performer load, analyze, and evaluation pipeline."""

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from codetta import ast, ir
from codetta.score_model import Score
from performer.evaluator import evaluate
from performer.score_reader import read_program


@dataclass(frozen=True)
class ExecutionResult:
    score: Score
    syntax: ast.Program
    execution: ir.Program
    value: Fraction


def run(path: str | Path) -> ExecutionResult:
    loaded = read_program(path)
    return ExecutionResult(loaded.score, loaded.syntax, loaded.execution,
                           evaluate(loaded.execution))

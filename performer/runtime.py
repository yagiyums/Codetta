"""Complete Performer load, analyze, and evaluation pipeline."""

from dataclasses import dataclass
from pathlib import Path

from codetta import ast, ir
from codetta.score_model import Score
from performer.evaluator import TraceEvent, evaluate_with_trace
from performer.score_reader import read_program


@dataclass(frozen=True)
class ExecutionResult:
    score: Score
    syntax: ast.Program
    execution: ir.Program
    value: object
    trace: tuple[TraceEvent, ...] = ()


def run(path: str | Path, *, max_iterations: int = 10_000,
        max_steps: int = 100_000, max_call_depth: int = 128) -> ExecutionResult:
    loaded = read_program(path)
    result = evaluate_with_trace(
        loaded.execution,
        max_iterations=max_iterations,
        max_steps=max_steps,
        max_call_depth=max_call_depth,
    )
    return ExecutionResult(loaded.score, loaded.syntax, loaded.execution,
                           result.value, result.trace)

"""Build and execute every artifact in the Codetta v0.1 calculator demo."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codetta.serialization import write_score as write_codetta
from conductor.compiler import compile_expression
from performer.player import plan, write_wav
from performer.runtime import run
from rendering.musicxml import write_musicxml
from rendering.renderer import write_score as render_score


def main() -> None:
    folder = Path(__file__).resolve().parent
    expression = (folder / "expression.txt").read_text(encoding="utf-8-sig").strip()
    score = compile_expression(expression, title="Codetta calculator demo")

    program_path = write_codetta(score, folder / "program.codetta")
    write_musicxml(score, folder / "score.musicxml")
    render_score(score, folder / "score.svg")
    render_score(score, folder / "score.html")

    executed = run(program_path)
    write_wav(plan(executed.score, executed.value), folder / "performance.wav")
    print(f"Result: {executed.value}")
    print(f"Program: {program_path}")
    print(f"Score:   {folder / 'score.html'}")
    print(f"Audio:   {folder / 'performance.wav'}")


if __name__ == "__main__":
    main()

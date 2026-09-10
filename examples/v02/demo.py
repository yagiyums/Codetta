"""Build every artifact for the Codetta v0.2 process example."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codetta.serialization import write_score as write_codetta
from composer.projection import parse_python
from conductor.compiler import compile_ast
from performer.player import plan, write_wav
from performer.runtime import run
from rendering.musicxml import write_musicxml
from rendering.renderer import write_score as render_score


def main() -> None:
    folder = Path(__file__).resolve().parent
    source = (folder / "process.py").read_text(encoding="utf-8-sig")
    score = compile_ast(parse_python(source), title="Codetta v0.2 process demo")

    program_path = write_codetta(score, folder / "program.codetta")
    write_musicxml(score, folder / "score.musicxml", debug=True)
    render_score(score, folder / "score.svg")
    render_score(score, folder / "score.html", debug=True)

    executed = run(program_path)
    performance = plan(executed.score, executed.value, trace=executed.trace)
    write_wav(performance, folder / "performance.wav", bpm=600)
    print(f"Result:  {executed.value}")
    print(f"Program: {program_path}")
    print(f"Score:   {folder / 'score.html'}")
    print(f"Audio:   {folder / 'performance.wav'}")


if __name__ == "__main__":
    main()

"""Command-line Conductor: expression -> Score Model -> output."""

import argparse
from pathlib import Path
import sys

from codetta.semantics import CodettaError
from conductor.compiler import compile_expression
from conductor.score_writer import write_score


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile arithmetic into a Codetta score.")
    parser.add_argument("expression", nargs="?", help="Arithmetic expression")
    parser.add_argument("--input", type=Path, help="Read the expression from a UTF-8 file")
    parser.add_argument("-o", "--output", type=Path, default=Path("program.codetta"))
    parser.add_argument("--title", default="Codetta program")
    parser.add_argument("--fifths", type=int, default=0, help="Key signature: -7 through 7")
    parser.add_argument("--clef", choices=("treble", "bass"), default="treble")
    parser.add_argument("--debug", action="store_true", help="Include a separate debug layer in HTML")
    args = parser.parse_args(argv)
    if (args.expression is None) == (args.input is None):
        parser.error("Supply either an expression or --input, but not both")
    if args.input and args.input.resolve() == args.output.resolve():
        parser.error("Input and output must be different files")
    try:
        source = args.input.read_text(encoding="utf-8-sig") if args.input else args.expression
        score = compile_expression(source, title=args.title, fifths=args.fifths, clef=args.clef)
        paths = write_score(score, args.output, debug=args.debug)
    except (CodettaError, OSError, UnicodeError) as exc:
        print(f"Conductor: {exc}", file=sys.stderr)
        return 1
    for path in paths:
        print(f"Score written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

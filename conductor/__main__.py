"""python -m conductor '(3 + 5) * 2' -o score.svg"""

import argparse
from pathlib import Path
import sys

from codetta.semantics import CodettaError
from conductor.compiler import compile_expression
from conductor.score_writer import write_score


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile an arithmetic expression to a Codetta SVG score.")
    parser.add_argument("expression", nargs="?", help="Quote the arithmetic expression")
    parser.add_argument("--input", type=Path, help="Read the expression from a UTF-8 file")
    parser.add_argument("-o", "--output", type=Path, default=Path("score.svg"))
    args = parser.parse_args(argv)
    if (args.expression is None) == (args.input is None):
        parser.error("Supply either an expression or --input, but not both")
    try:
        source = args.input.read_text(encoding="utf-8-sig") if args.input else args.expression
        path = write_score(compile_expression(source), args.output)
    except (CodettaError, OSError, UnicodeError) as exc:
        print(f"Conductor: {exc}", file=sys.stderr)
        return 1
    print(f"Score written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

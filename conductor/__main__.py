"""python -m conductor '(3 + 5) * 2' -o score.svg"""

import argparse
from pathlib import Path
import sys

from codetta.semantics import CodettaError
from conductor.compiler import compile_expression
from conductor.score_writer import write_score


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile an expression and export conventional staff notation or executable Codetta SVG.")
    parser.add_argument("expression", nargs="?", help="Quote the arithmetic expression")
    parser.add_argument("--input", type=Path, help="Read the expression from a UTF-8 file")
    parser.add_argument("-o", "--output", type=Path, default=Path("score.svg"))
    parser.add_argument("--format", choices=("svg", "html", "musicxml", "executable-svg"),
                        help="Default: infer from output suffix; .svg is conventional staff notation")
    parser.add_argument("--debug", action="store_true", help="Show IR annotations on the staff score")
    parser.add_argument("--time", default="4/4", help="Notated time signature, e.g. 3/4")
    parser.add_argument("--fifths", type=int, default=0, help="Key signature: -7 through 7 (default C major)")
    parser.add_argument("--clef", choices=("treble", "bass"), default="treble")
    args = parser.parse_args(argv)
    if (args.expression is None) == (args.input is None):
        parser.error("Supply either an expression or --input, but not both")
    if args.input and args.input.resolve() == args.output.resolve():
        parser.error("Input and output must be different files")
    output_format = args.format or {".svg": "svg", ".html": "html", ".xml": "musicxml",
                                   ".musicxml": "musicxml"}.get(args.output.suffix.lower())
    if output_format is None:
        parser.error("Use an .svg, .html, or .musicxml output filename")
    expected_suffixes = {"svg": (".svg",), "html": (".html",), "musicxml": (".xml", ".musicxml"),
                         "executable-svg": (".svg",)}
    if args.output.suffix.lower() not in expected_suffixes[output_format]:
        parser.error("Output filename extension does not match --format")
    try:
        source = args.input.read_text(encoding="utf-8-sig") if args.input else args.expression
        program = compile_expression(source)
        if output_format == "executable-svg":
            paths = (write_score(program, args.output),)
        else:
            from rendering.model import NotationOptions
            from rendering.musicxml import write_musicxml
            from rendering.renderer import write_ir

            try:
                beats, beat_type = map(int, args.time.split("/"))
            except ValueError as exc:
                raise CodettaError("Time signature must look like 4/4 or 3/8") from exc
            notation = NotationOptions(beats, beat_type, args.fifths, args.clef)
            if output_format == "musicxml":
                paths = (write_musicxml(program, args.output, notation, debug=args.debug),)
            else:
                paths = write_ir(program, args.output, notation, debug=args.debug)
    except (CodettaError, OSError, UnicodeError) as exc:
        print(f"Conductor: {exc}", file=sys.stderr)
        return 1
    for path in paths:
        print(f"Score written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

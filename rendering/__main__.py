"""Render a .codetta or MusicXML file as SVG/HTML notation."""

import argparse
from pathlib import Path
import sys

from codetta.semantics import CodettaError
from codetta.serialization import read_score
from rendering.renderer import (RenderOptions, read_musicxml, render_musicxml,
                                write_rendered, write_score)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render Codetta or MusicXML as conventional staff notation.")
    parser.add_argument("input", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=Path("score.html"))
    parser.add_argument("--page-width", type=int, default=2100)
    parser.add_argument("--page-height", type=int, default=2970)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)
    if args.input.resolve() == args.output.resolve():
        parser.error("Input and output must be different files")
    options = RenderOptions(args.page_width, args.page_height)
    try:
        if args.input.suffix.lower() == ".codetta":
            paths = write_score(read_score(args.input), args.output, options, debug=args.debug)
            diagnostics = ""
        else:
            rendered = render_musicxml(read_musicxml(args.input), options)
            paths = write_rendered(rendered, args.output)
            diagnostics = rendered.diagnostics
        if diagnostics:
            print(diagnostics, file=sys.stderr)
    except (CodettaError, OSError, UnicodeError) as exc:
        print(f"Rendering: {exc}", file=sys.stderr)
        return 1
    for path in paths:
        print(f"Score written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

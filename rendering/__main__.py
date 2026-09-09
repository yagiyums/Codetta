"""python -m rendering input.musicxml -o score.html"""

import argparse
from pathlib import Path
import sys

from codetta.semantics import CodettaError
from rendering.renderer import RenderOptions, read_musicxml, render_musicxml, write_rendered


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Engrave MusicXML as conventional staff notation using Verovio.")
    parser.add_argument("input", type=Path, help="MusicXML (.musicxml, .xml or .mxl)")
    parser.add_argument("-o", "--output", type=Path, default=Path("score.html"))
    parser.add_argument("--page-width", type=int, default=2100)
    parser.add_argument("--page-height", type=int, default=2970)
    args = parser.parse_args(argv)
    if args.input.resolve() == args.output.resolve():
        parser.error("Input and output must be different files")
    try:
        rendered = render_musicxml(read_musicxml(args.input), RenderOptions(args.page_width, args.page_height))
        paths = write_rendered(rendered, args.output)
        if rendered.diagnostics:
            print(rendered.diagnostics, file=sys.stderr)
    except (CodettaError, OSError, UnicodeError) as exc:
        print(f"Rendering: {exc}", file=sys.stderr)
        return 1
    for path in paths:
        print(f"Score written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

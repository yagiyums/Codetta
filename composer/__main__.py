"""Launch Composer in the default browser."""

import argparse
from pathlib import Path
import threading
import webbrowser

from composer.server import ComposerApplication, serve


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Open the Codetta Composer local IDE")
    parser.add_argument("file", nargs="?", type=Path, help="Optional .codetta file to open")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--max-iterations", type=int, default=10_000,
                        help="Stop runaway loops after this many iterations")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    if args.max_iterations <= 0:
        parser.error("--max-iterations must be positive")
    app = ComposerApplication.open(args.file, max_iterations=args.max_iterations)
    server = serve(app, args.host, args.port)
    url = f"http://{args.host}:{server.server_port}"
    print(f"Codetta Composer is running at {url} (Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(0.35, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nComposer stopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

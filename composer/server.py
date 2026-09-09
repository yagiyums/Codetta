"""HTTP application backing the dependency-free Composer frontend."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import tempfile
import threading
from typing import Any

from codetta.score_model import Score
from codetta.score_parser import parse_score
from codetta.semantic_analyzer import analyze
from codetta.serialization import dumps, loads, read_score
from codetta.semantics import CodettaError
from composer.projection import emit_python, parse_python
from conductor.compiler import compile_ast, compile_expression
from performer.evaluator import evaluate
from performer.player import plan, write_wav
from rendering.renderer import RenderOptions, render_score


STATIC = Path(__file__).with_name("static")
ROOT = Path(__file__).resolve().parents[1]
MAX_REQUEST = 5 * 1024 * 1024


def _value(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


@dataclass
class Snapshot:
    score: Score
    python: str
    json: str
    svg: str
    debug_svg: str
    result: str


class ComposerApplication:
    def __init__(self, score: Score):
        self.lock = threading.RLock()
        self.latest_revision = 0
        self.snapshot = self._build(score)

    @classmethod
    def open(cls, path: Path | None = None) -> "ComposerApplication":
        if path is not None:
            return cls(read_score(path))
        example = ROOT / "examples" / "calculator" / "program.codetta"
        return cls(read_score(example) if example.exists() else compile_expression("(3 + 5) * 2"))

    @staticmethod
    def _build(score: Score) -> Snapshot:
        syntax = parse_score(score)
        execution = analyze(syntax)
        result = evaluate(execution)
        # Composer uses a compact canvas rather than a print page.  Grow the
        # viewport with the measure so Verovio never has to squeeze a long,
        # single-measure program into an invalid system.
        widest_measure = max(measure.time_signature.beats
                             for staff in score.parts[0].staves for measure in staff.measures)
        page_width = min(10_000, max(960, widest_measure * 120))
        options = RenderOptions(page_width=page_width, page_height=900, scale=60)
        normal = "\n".join(render_score(score, options).pages)
        debug = "\n".join(render_score(score, options, debug=True).pages)
        return Snapshot(score, emit_python(syntax), dumps(score), normal, debug, _value(result))

    def payload(self, revision: int = 0) -> dict[str, Any]:
        with self.lock:
            item = self.snapshot
            score_data = json.loads(item.json)
            return {
                "ok": True, "revision": revision, "python": item.python, "json": item.json,
                "score": score_data, "svg": item.svg, "debug_svg": item.debug_svg,
                "result": item.result, "title": item.score.metadata.get("title", "Untitled"),
                "event_count": sum(len(voice.events) for part in item.score.parts for staff in part.staves
                                   for measure in staff.measures for voice in measure.voices),
                "staff_count": len(item.score.parts[0].staves),
            }

    def sync_python(self, source: str, revision: int) -> dict[str, Any]:
        self._begin(revision)
        program = parse_python(source)
        current_title = self.snapshot.score.metadata.get("title", "Codetta program")
        candidate = compile_ast(program, title=current_title)
        return self.commit(candidate, revision, relaid=True)

    def sync_json(self, source: str, revision: int) -> dict[str, Any]:
        self._begin(revision)
        return self.commit(loads(source), revision)

    def _begin(self, revision: int) -> None:
        with self.lock:
            self.latest_revision = max(self.latest_revision, revision)

    def commit(self, score: Score, revision: int, *, relaid: bool = False) -> dict[str, Any]:
        candidate = self._build(score)
        with self.lock:
            if revision < self.latest_revision:
                response = self.payload(revision)
                response["discarded"] = True
                return response
            self.snapshot = candidate
        response = self.payload(revision)
        response["relaid"] = relaid
        return response

    def audio(self) -> bytes:
        with self.lock:
            snapshot = self.snapshot
        performance = plan(snapshot.score, Fraction(snapshot.result))
        with tempfile.TemporaryDirectory(prefix="codetta-composer-") as folder:
            path = write_wav(performance, Path(folder) / "preview.wav", bpm=120)
            return path.read_bytes()


class _Server(HTTPServer):
    app: ComposerApplication


class Handler(BaseHTTPRequestHandler):
    server: _Server

    def log_message(self, format: str, *args: object) -> None:
        pass

    def _send(self, data: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        self._send(json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8", status)

    def do_GET(self) -> None:
        if self.path == "/api/state":
            self._json(self.server.app.payload())
            return
        if self.path == "/assets/composer.png":
            self._send((ROOT / "logo" / "composer.png").read_bytes(), "image/png")
            return
        name = "index.html" if self.path in ("/", "/index.html") else self.path.removeprefix("/")
        if name not in {"index.html", "app.css", "app.js"}:
            self._send(b"Not found", "text/plain", HTTPStatus.NOT_FOUND)
            return
        content_type = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
                        ".js": "text/javascript; charset=utf-8"}[Path(name).suffix]
        self._send((STATIC / name).read_bytes(), content_type)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_REQUEST:
            self._json({"ok": False, "error": "Request is larger than 5 MiB"}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return
        try:
            if self.path == "/api/audio":
                self._send(self.server.app.audio(), "audio/wav")
                return
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            revision = int(body.get("revision", 0))
            source = body.get("source")
            if not isinstance(source, str):
                raise CodettaError("Request source must be text")
            if self.path == "/api/sync/python":
                response = self.server.app.sync_python(source, revision)
            elif self.path == "/api/sync/json":
                response = self.server.app.sync_json(source, revision)
            else:
                self._json({"ok": False, "error": "Not found"}, HTTPStatus.NOT_FOUND)
                return
            self._json(response)
        except (CodettaError, json.JSONDecodeError, UnicodeError, ValueError) as exc:
            self._json({"ok": False, "error": str(exc), "revision": locals().get("revision", 0)},
                       HTTPStatus.BAD_REQUEST)


def serve(app: ComposerApplication, host: str, port: int) -> _Server:
    server = _Server((host, port), Handler)
    server.app = app
    return server

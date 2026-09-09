"""Write Conductor output through the official format and rendering adapters."""

from pathlib import Path

from codetta.score_model import Score
from codetta.serialization import write_score as write_codetta
from codetta.semantics import CodettaError


def write_score(score: Score, path: str | Path, *, debug: bool = False) -> tuple[Path, ...]:
    destination = Path(path)
    suffix = destination.suffix.lower()
    if suffix == ".codetta":
        return (write_codetta(score, destination),)
    if suffix in (".musicxml", ".xml"):
        from rendering.musicxml import write_musicxml
        return (write_musicxml(score, destination, debug=debug),)
    if suffix in (".svg", ".html"):
        from rendering.renderer import write_score as write_rendered_score
        return write_rendered_score(score, destination, debug=debug)
    raise CodettaError("Output must end in .codetta, .musicxml, .xml, .svg or .html")

"""Verovio engraving adapter. This module never imports the execution runtime."""

from dataclasses import dataclass
from html import escape
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

from codetta import ir
from codetta.semantics import CodettaError
from rendering.model import NotationOptions
from rendering.musicxml import to_musicxml


@dataclass(frozen=True)
class RenderOptions:
    page_width: int = 2100
    page_height: int = 2970
    scale: int = 40

    def __post_init__(self) -> None:
        if not 300 <= self.page_width <= 10000 or not 300 <= self.page_height <= 10000:
            raise CodettaError("Page dimensions must be between 300 and 10000 Verovio units")
        if not 10 <= self.scale <= 200:
            raise CodettaError("Rendering scale must be between 10 and 200")


@dataclass(frozen=True)
class RenderedScore:
    pages: tuple[str, ...]
    diagnostics: str = ""


def _musicxml_text(data: str | bytes) -> str:
    entity_marker = b"<!ENTITY" if isinstance(data, bytes) else "<!ENTITY"
    if entity_marker in data.upper():
        raise CodettaError("XML entity declarations are not supported")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise CodettaError(f"Invalid MusicXML: {exc}") from exc
    if root.tag != "score-partwise":
        raise CodettaError("Expected a score-partwise MusicXML document")
    if root.find("part-list") is None or not root.findall("part/measure"):
        raise CodettaError("MusicXML must contain a part list and measures")
    # Parsing also removes external DOCTYPE declarations; no DTD is fetched.
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def read_musicxml(path: str | Path) -> str:
    source = Path(path)
    if source.suffix.lower() != ".mxl":
        return _musicxml_text(source.read_bytes())
    try:
        with zipfile.ZipFile(source) as archive:
            container = ET.fromstring(archive.read("META-INF/container.xml"))
            entry = next((e.get("full-path") for e in container.iter()
                          if e.tag.rsplit("}", 1)[-1] == "rootfile"), None)
            if not entry:
                raise CodettaError("MXL container has no rootfile")
            return _musicxml_text(archive.read(entry))
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        raise CodettaError(f"Invalid compressed MusicXML: {exc}") from exc


def render_musicxml(xml: str, options: RenderOptions | None = None) -> RenderedScore:
    xml = _musicxml_text(xml)
    try:
        import verovio
    except ImportError as exc:
        raise CodettaError("Staff rendering requires Verovio. Install requirements-rendering.txt in your Python environment.") from exc
    options = options or RenderOptions()
    toolkit = verovio.toolkit()
    toolkit.setOptions({"inputFrom": "xml", "pageWidth": options.page_width,
                        "pageHeight": options.page_height, "scale": options.scale,
                        "adjustPageHeight": True, "svgViewBox": True,
                        "header": "none", "footer": "none", "xmlIdSeed": 1})
    if not toolkit.loadData(xml):
        raise CodettaError("Verovio could not load the MusicXML: " + toolkit.getLog().strip())
    diagnostics = [toolkit.getLog().strip()]
    page_count = toolkit.getPageCount()
    if page_count == 0:
        raise CodettaError("Verovio produced no score pages")
    pages = []
    for page in range(1, page_count + 1):
        svg = toolkit.renderToSVG(page)
        if not svg.strip():
            raise CodettaError(f"Verovio produced an empty page {page}")
        pages.append(svg)
        diagnostics.append(toolkit.getLog().strip())
    return RenderedScore(tuple(pages), "\n".join(dict.fromkeys(d for d in diagnostics if d)))


def render_ir(program: ir.Emit, notation: NotationOptions | None = None,
              options: RenderOptions | None = None, *, debug: bool = False) -> RenderedScore:
    return render_musicxml(to_musicxml(program, notation, debug=debug), options)


def to_html(score: RenderedScore, *, title: str = "Codetta", debug_score: RenderedScore | None = None,
            debug: bool = False) -> str:
    def pages(rendered: RenderedScore, name: str) -> str:
        fragments = []
        for index, svg in enumerate(rendered.pages, 1):
            # Separate normal/debug documents need distinct glyph and element IDs.
            root = ET.fromstring(svg)
            ids = {e.get("id"): f"{name}-p{index}-{e.get('id')}" for e in root.iter() if e.get("id")}
            for item in root.iter():
                if item.tag.rsplit("}", 1)[-1] == "style" and item.text:
                    # Verovio scopes its stroke/fill CSS to the SVG root ID.
                    item.text = re.sub(r"#([A-Za-z_][\w.-]*)",
                                       lambda match: "#" + ids.get(match[1], match[1]), item.text)
                for key, value in list(item.attrib.items()):
                    if key == "id":
                        item.set(key, ids[value])
                    elif value.startswith("#") and value[1:] in ids:
                        item.set(key, "#" + ids[value[1:]])
                    else:
                        value = re.sub(r"url\(#([^)]+)\)",
                                       lambda match: f"url(#{ids.get(match[1], match[1])})", value)
                        item.set(key, value)
            ET.register_namespace("", "http://www.w3.org/2000/svg")
            # HTML recognizes xlink:href, not arbitrary XML namespace prefixes.
            ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
            fragments.append(f'<section class="page" aria-label="Page {index}">{ET.tostring(root, encoding="unicode")}</section>')
        return "\n".join(fragments)

    toggle = ('<label><input id="debug" type="checkbox"' + (' checked' if debug else '')
              + '> Debug mode</label>') if debug_score else ""
    debug_pages = f'<div class="debug-score">{pages(debug_score, "debug")}</div>' if debug_score else ""
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title><style>
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: #ececec; color: #111; font-family: system-ui, sans-serif; }}
header {{ display: flex; align-items: center; gap: 24px; padding: 14px 24px; background: white; border-bottom: 1px solid #ddd; }}
header strong {{ margin-right: auto; }}
button {{ padding: 7px 14px; border: 1px solid #bbb; border-radius: 4px; background: white; cursor: pointer; }}
main {{ padding: 24px; }}
.page {{ max-width: 1000px; margin: 0 auto 24px; padding: 24px; background: white; box-shadow: 0 2px 10px #0001; }}
.page svg {{ display: block; width: 100%; height: auto; }}
.debug-score {{ display: none; }}
body.debug .normal-score {{ display: none; }}
body.debug .debug-score {{ display: block; }}
@page {{ size: A4; margin: 12mm; }}
@media print {{
  body {{ background: white; }} header {{ display: none; }} main {{ padding: 0; }}
  .page {{ max-width: none; margin: 0; padding: 0; box-shadow: none; break-after: page; break-inside: avoid; }}
  .page:last-child {{ break-after: auto; }}
}}
</style></head><body class="{'debug' if debug and debug_score else ''}">
<header><strong>{escape(title)}</strong>{toggle}<button id="print">Print / Save PDF</button></header>
<main><div class="normal-score">{pages(score, "normal")}</div>{debug_pages}</main>
<script>
document.getElementById('print').addEventListener('click', () => window.print());
document.getElementById('debug')?.addEventListener('change', event => {{
  document.body.classList.toggle('debug', event.target.checked);
}});
</script></body></html>
'''


def write_rendered(score: RenderedScore, path: str | Path, *, title: str = "Codetta",
                   debug_score: RenderedScore | None = None, debug: bool = False) -> tuple[Path, ...]:
    destination = Path(path)
    suffix = destination.suffix.lower()
    if suffix not in (".html", ".svg"):
        raise CodettaError("Rendered output must end in .svg or .html; save PDF from the HTML print button")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if suffix == ".html":
        destination.write_text(to_html(score, title=title, debug_score=debug_score, debug=debug), encoding="utf-8")
        return (destination,)
    paths = []
    for index, page in enumerate(score.pages, 1):
        target = destination if index == 1 else destination.with_name(f"{destination.stem}-{index}.svg")
        target.write_text(page, encoding="utf-8")
        paths.append(target)
    return tuple(paths)


def write_ir(program: ir.Emit, path: str | Path, notation: NotationOptions | None = None,
             options: RenderOptions | None = None, *, debug: bool = False) -> tuple[Path, ...]:
    if Path(path).suffix.lower() == ".html":
        normal = render_ir(program, notation, options)
        annotated = render_ir(program, notation, options, debug=True)
        return write_rendered(normal, path, debug_score=annotated, debug=debug)
    return write_rendered(render_ir(program, notation, options, debug=debug), path)

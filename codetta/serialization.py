"""JSON serialization for the official ``.codetta`` score container."""

from __future__ import annotations

from fractions import Fraction
import json
from pathlib import Path
from typing import Any

from codetta.score_model import (FORMAT, Chord, Clef, KeySignature, Measure, Note,
                                 Part, Pitch, Rest, Score, Spanner, Staff,
                                 TimeSignature, Voice, validate_score)
from codetta.semantics import CodettaError

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_JSON_DEPTH = 64


class SerializationError(CodettaError):
    pass


def _fraction(value: Fraction) -> dict[str, int]:
    return {"n": value.numerator, "d": value.denominator}


def _read_fraction(value: object, location: str) -> Fraction:
    if not isinstance(value, dict) or set(value) != {"n", "d"}:
        raise SerializationError(f"{location} must be an object with n and d")
    n, d = value["n"], value["d"]
    if type(n) is not int or type(d) is not int or d == 0:
        raise SerializationError(f"{location} needs integer n and nonzero integer d")
    return Fraction(n, d)


def _pitch(value: Pitch) -> dict[str, object]:
    return {"step": value.step, "alter": value.alter, "octave": value.octave}


def _read_pitch(value: object, location: str) -> Pitch:
    if not isinstance(value, dict) or set(value) != {"step", "alter", "octave"}:
        raise SerializationError(f"{location} must contain step, alter and octave")
    return Pitch(value["step"], value["alter"], value["octave"])


def _event(event: Note | Rest | Chord) -> dict[str, object]:
    result: dict[str, object] = {
        "type": event.type,
        "id": event.id,
        "start": _fraction(event.start),
        "duration": _fraction(event.duration),
    }
    if isinstance(event, Note):
        result["pitch"] = _pitch(event.pitch)
    elif isinstance(event, Chord):
        result["pitches"] = [_pitch(pitch) for pitch in event.pitches]
    if isinstance(event, (Note, Chord)):
        if event.accidental is not None:
            result["accidental"] = event.accidental
        if event.stem is not None:
            result["stem"] = event.stem
    return result


def to_data(score: Score) -> dict[str, object]:
    validate_score(score)
    return {
        "format": FORMAT,
        "format_version": score.format_version,
        "language_version": score.language_version,
        "score": {
            "metadata": dict(score.metadata),
            "parts": [{
                "id": part.id,
                "staves": [{
                    "id": staff.id,
                    "measures": [{
                        "id": measure.id,
                        "number": measure.number,
                        "time_signature": {
                            "beats": measure.time_signature.beats,
                            "beat_type": measure.time_signature.beat_type,
                        },
                        "key_signature": {"fifths": measure.key_signature.fifths},
                        "clef": {"sign": measure.clef.sign, "line": measure.clef.line},
                        "barline": measure.barline,
                        "voices": [{
                            "id": voice.id,
                            "staff": voice.staff,
                            "events": [_event(event) for event in voice.events],
                        } for voice in measure.voices],
                    } for measure in staff.measures],
                } for staff in part.staves],
            } for part in score.parts],
            "spanners": [{
                "id": spanner.id,
                "type": spanner.type,
                "line_style": spanner.line_style,
                "start_anchor": spanner.start_anchor,
                "end_anchor": spanner.end_anchor,
                **({"staff_range": list(spanner.staff_range)} if spanner.staff_range else {}),
                **({"voice_range": list(spanner.voice_range)} if spanner.voice_range else {}),
                "nesting_level": spanner.nesting_level,
            } for spanner in score.spanners],
        },
    }


def dumps(score: Score, *, indent: int = 2) -> str:
    return json.dumps(to_data(score), ensure_ascii=False, indent=indent) + "\n"


def _object(value: object, keys: set[str], location: str, optional: set[str] = frozenset()) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SerializationError(f"{location} must be an object")
    extra = set(value) - keys - optional
    missing = keys - set(value)
    if extra or missing:
        details = []
        if missing:
            details.append("missing " + ", ".join(sorted(missing)))
        if extra:
            details.append("unknown " + ", ".join(sorted(extra)))
        raise SerializationError(f"Invalid {location}: {'; '.join(details)}")
    return value


def _list(value: object, location: str) -> list[Any]:
    if not isinstance(value, list):
        raise SerializationError(f"{location} must be an array")
    return value


def _read_event(value: object, location: str):
    if not isinstance(value, dict) or "type" not in value:
        raise SerializationError(f"{location} needs an event type")
    common = {"type", "id", "start", "duration"}
    event_type = value["type"]
    if event_type == "rest":
        data = _object(value, common, location)
        return Rest(data["id"], _read_fraction(data["start"], location + ".start"),
                    _read_fraction(data["duration"], location + ".duration"))
    optional = {"accidental", "stem"}
    if event_type == "note":
        data = _object(value, common | {"pitch"}, location, optional)
        return Note(data["id"], _read_fraction(data["start"], location + ".start"),
                    _read_fraction(data["duration"], location + ".duration"),
                    _read_pitch(data["pitch"], location + ".pitch"),
                    data.get("accidental"), data.get("stem"))
    if event_type == "chord":
        data = _object(value, common | {"pitches"}, location, optional)
        pitches = tuple(_read_pitch(pitch, f"{location}.pitches[{index}]")
                        for index, pitch in enumerate(_list(data["pitches"], location + ".pitches")))
        return Chord(data["id"], _read_fraction(data["start"], location + ".start"),
                     _read_fraction(data["duration"], location + ".duration"), pitches,
                     data.get("accidental"), data.get("stem"))
    raise SerializationError(f"Unknown event type {event_type!r} at {location}")


def _range(value: object, location: str) -> tuple[int, int]:
    values = _list(value, location)
    if len(values) != 2 or any(type(item) is not int for item in values):
        raise SerializationError(f"{location} must contain two integers")
    return values[0], values[1]


def _depth(value: object, depth: int = 0) -> None:
    if depth > MAX_JSON_DEPTH:
        raise SerializationError(f"JSON nesting exceeds {MAX_JSON_DEPTH} levels")
    if isinstance(value, dict):
        for item in value.values():
            _depth(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _depth(item, depth + 1)


def from_data(value: object) -> Score:
    _depth(value)
    root = _object(value, {"format", "format_version", "language_version", "score"}, "document")
    if root["format"] != FORMAT:
        raise SerializationError(f"Expected format {FORMAT!r}")
    body = _object(root["score"], {"metadata", "parts", "spanners"}, "score")
    metadata = body["metadata"]
    if not isinstance(metadata, dict):
        raise SerializationError("score.metadata must be an object")
    parts = []
    for pi, part_value in enumerate(_list(body["parts"], "score.parts")):
        part_data = _object(part_value, {"id", "staves"}, f"score.parts[{pi}]")
        staves = []
        for si, staff_value in enumerate(_list(part_data["staves"], f"score.parts[{pi}].staves")):
            staff_data = _object(staff_value, {"id", "measures"}, f"staff[{si}]")
            measures = []
            for mi, measure_value in enumerate(_list(staff_data["measures"], f"staff[{si}].measures")):
                location = f"staff[{si}].measures[{mi}]"
                data = _object(measure_value, {"id", "number", "time_signature", "key_signature",
                                               "clef", "barline", "voices"}, location)
                time = _object(data["time_signature"], {"beats", "beat_type"}, location + ".time_signature")
                key = _object(data["key_signature"], {"fifths"}, location + ".key_signature")
                clef = _object(data["clef"], {"sign", "line"}, location + ".clef")
                voices = []
                for vi, voice_value in enumerate(_list(data["voices"], location + ".voices")):
                    voice_data = _object(voice_value, {"id", "staff", "events"}, f"{location}.voices[{vi}]")
                    voices.append(Voice(voice_data["id"], voice_data["staff"], tuple(
                        _read_event(event, f"{location}.voices[{vi}].events[{ei}]")
                        for ei, event in enumerate(_list(voice_data["events"], f"{location}.voices[{vi}].events")))))
                measures.append(Measure(data["id"], data["number"],
                                        TimeSignature(time["beats"], time["beat_type"]),
                                        KeySignature(key["fifths"]), Clef(clef["sign"], clef["line"]),
                                        tuple(voices), data["barline"]))
            staves.append(Staff(staff_data["id"], tuple(measures)))
        parts.append(Part(part_data["id"], tuple(staves)))
    spanners = []
    for index, spanner_value in enumerate(_list(body["spanners"], "score.spanners")):
        location = f"score.spanners[{index}]"
        data = _object(spanner_value, {"id", "type", "line_style", "start_anchor", "end_anchor",
                                               "nesting_level"}, location,
                       {"staff_range", "voice_range"})
        spanners.append(Spanner(data["id"], data["type"], data["line_style"],
                                data["start_anchor"], data["end_anchor"],
                                _range(data["staff_range"], location + ".staff_range") if "staff_range" in data else None,
                                _range(data["voice_range"], location + ".voice_range") if "voice_range" in data else None,
                                data["nesting_level"]))
    try:
        return validate_score(Score(dict(metadata), tuple(parts), tuple(spanners),
                                    root["format_version"], root["language_version"]))
    except CodettaError as exc:
        raise SerializationError(str(exc)) from exc
    except (TypeError, KeyError) as exc:
        raise SerializationError(f"Invalid .codetta field type: {exc}") from exc


def loads(source: str | bytes) -> Score:
    raw = source.encode("utf-8") if isinstance(source, str) else source
    if len(raw) > MAX_FILE_BYTES:
        raise SerializationError(f".codetta file exceeds {MAX_FILE_BYTES // (1024 * 1024)} MiB")
    try:
        return from_data(json.loads(raw.decode("utf-8-sig")))
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise SerializationError(f"Invalid .codetta JSON: {exc}") from exc
    except SerializationError:
        raise
    except CodettaError as exc:
        raise SerializationError(str(exc)) from exc
    except (TypeError, KeyError, IndexError) as exc:
        raise SerializationError(f"Invalid .codetta field type: {exc}") from exc


def write_score(score: Score, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(dumps(score), encoding="utf-8", newline="\n")
    temporary.replace(destination)
    return destination


def read_score(path: str | Path) -> Score:
    return loads(Path(path).read_bytes())

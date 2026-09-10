"""JSON serialization for the official ``.codetta`` score container."""

from __future__ import annotations

from fractions import Fraction
import json
from pathlib import Path
from typing import Any

from codetta.score_model import (FORMAT, Chord, Clef, Cue, KeySignature, Measure,
                                 Note, Part, PhraseRegion, Pitch, Relation,
                                 RepeatRegion, Rest, Score, Section,
                                 SectionReference, Spanner, Staff, TimeSignature,
                                 Voice, VoiceGroup, VoltaEnding, VoltaGroup,
                                 validate_score)
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


def _event(event: Note | Rest | Chord | Cue) -> dict[str, object]:
    result: dict[str, object] = {
        "type": event.type,
        "id": event.id,
        "start": _fraction(event.start),
        "duration": _fraction(event.duration),
    }
    if isinstance(event, (Note, Cue)):
        result["pitch"] = _pitch(event.pitch)
    elif isinstance(event, Chord):
        result["pitches"] = [_pitch(pitch) for pitch in event.pitches]
    if isinstance(event, (Note, Chord, Cue)):
        if event.accidental is not None:
            result["accidental"] = event.accidental
        if event.stem is not None:
            result["stem"] = event.stem
    if isinstance(event, Cue):
        result["source_voice_id"] = event.source_voice_id
    return result


def to_data(score: Score) -> dict[str, object]:
    validate_score(score)
    body: dict[str, object] = {
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
                        **({"name": voice.name} if voice.name is not None else {}),
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
    }
    if score.language_version == "0.2":
        body.update(_v02_data(score))
    return {"format": FORMAT, "format_version": score.format_version,
            "language_version": score.language_version, "score": body}


def _v02_data(score: Score) -> dict[str, object]:
    return {
        "voice_groups": [{"id": item.id, "name": item.name,
                          "voice_ids": list(item.voice_ids),
                          **({"output_anchor": item.output_anchor}
                             if item.output_anchor is not None else {})}
                         for item in score.voice_groups],
        "phrases": [{"id": item.id, "start_anchor": item.start_anchor,
                     "end_anchor": item.end_anchor, "voice_ids": list(item.voice_ids),
                     "output_anchor": item.output_anchor} for item in score.phrases],
        "relations": [{"id": item.id, "connector": item.connector,
                       "input_anchors": list(item.input_anchors),
                       "output_anchor": item.output_anchor,
                       **({"field_voice_id": item.field_voice_id}
                          if item.field_voice_id is not None else {})}
                      for item in score.relations],
        "sections": [{"id": item.id, "name": item.name,
                      "rehearsal_mark": item.rehearsal_mark,
                      "start_measure": item.start_measure, "end_measure": item.end_measure,
                      "parameter_voice_ids": list(item.parameter_voice_ids),
                      "return_voice_ids": list(item.return_voice_ids)}
                     for item in score.sections],
        "section_references": [{"id": item.id, "section_id": item.section_id,
                                "anchor": item.anchor,
                                "argument_voice_ids": list(item.argument_voice_ids),
                                "result_voice_ids": list(item.result_voice_ids)}
                               for item in score.section_references],
        "repeats": [{"id": item.id, "start_measure": item.start_measure,
                     "end_measure": item.end_measure,
                     **({"iterator_voice_id": item.iterator_voice_id}
                        if item.iterator_voice_id is not None else {}),
                     **({"times": item.times} if item.times is not None else {}),
                     **({"count_voice_id": item.count_voice_id}
                        if item.count_voice_id is not None else {}),
                     **({"collection_voice_id": item.collection_voice_id}
                        if item.collection_voice_id is not None else {}),
                     **({"condition_voice_id": item.condition_voice_id}
                        if item.condition_voice_id is not None else {}),
                     "test_at_end": item.test_at_end} for item in score.repeats],
        "voltas": [{"id": item.id, "condition_voice_id": item.condition_voice_id,
                    "endings": [{"numbers": list(ending.numbers),
                                 "start_measure": ending.start_measure,
                                 "end_measure": ending.end_measure}
                                for ending in item.endings]} for item in score.voltas],
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


def _strings(value: object, location: str) -> tuple[str, ...]:
    values = _list(value, location)
    if any(not isinstance(item, str) for item in values):
        raise SerializationError(f"{location} must contain strings")
    return tuple(values)


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
    if event_type == "cue":
        data = _object(value, common | {"pitch", "source_voice_id"}, location, optional)
        return Cue(data["id"], _read_fraction(data["start"], location + ".start"),
                   _read_fraction(data["duration"], location + ".duration"),
                   data["source_voice_id"], _read_pitch(data["pitch"], location + ".pitch"),
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


def _read_v02_body(body: dict[str, Any]):
    voice_groups = []
    for index, item in enumerate(_list(body["voice_groups"], "score.voice_groups")):
        location = f"score.voice_groups[{index}]"
        data = _object(item, {"id", "name", "voice_ids"}, location, {"output_anchor"})
        voice_groups.append(VoiceGroup(data["id"], data["name"],
                                       _strings(data["voice_ids"], location + ".voice_ids"),
                                       data.get("output_anchor")))
    phrases = []
    for index, item in enumerate(_list(body["phrases"], "score.phrases")):
        location = f"score.phrases[{index}]"
        data = _object(item, {"id", "start_anchor", "end_anchor", "voice_ids",
                              "output_anchor"}, location)
        phrases.append(PhraseRegion(data["id"], data["start_anchor"], data["end_anchor"],
                                    _strings(data["voice_ids"], location + ".voice_ids"),
                                    data["output_anchor"]))
    relations = []
    for index, item in enumerate(_list(body["relations"], "score.relations")):
        location = f"score.relations[{index}]"
        data = _object(item, {"id", "connector", "input_anchors", "output_anchor"},
                       location, {"field_voice_id"})
        relations.append(Relation(data["id"], data["connector"],
                                  _strings(data["input_anchors"], location + ".input_anchors"),
                                  data["output_anchor"], data.get("field_voice_id")))
    sections = []
    for index, item in enumerate(_list(body["sections"], "score.sections")):
        location = f"score.sections[{index}]"
        data = _object(item, {"id", "name", "rehearsal_mark", "start_measure",
                              "end_measure", "parameter_voice_ids", "return_voice_ids"}, location)
        sections.append(Section(data["id"], data["name"], data["rehearsal_mark"],
                                data["start_measure"], data["end_measure"],
                                _strings(data["parameter_voice_ids"], location + ".parameter_voice_ids"),
                                _strings(data["return_voice_ids"], location + ".return_voice_ids")))
    references = []
    for index, item in enumerate(_list(body["section_references"], "score.section_references")):
        location = f"score.section_references[{index}]"
        data = _object(item, {"id", "section_id", "anchor", "argument_voice_ids",
                              "result_voice_ids"}, location)
        references.append(SectionReference(
            data["id"], data["section_id"], data["anchor"],
            _strings(data["argument_voice_ids"], location + ".argument_voice_ids"),
            _strings(data["result_voice_ids"], location + ".result_voice_ids")))
    repeats = []
    for index, item in enumerate(_list(body["repeats"], "score.repeats")):
        location = f"score.repeats[{index}]"
        data = _object(item, {"id", "start_measure", "end_measure", "test_at_end"},
                       location, {"iterator_voice_id", "times", "count_voice_id",
                                  "collection_voice_id",
                                  "condition_voice_id"})
        repeats.append(RepeatRegion(data["id"], data["start_measure"], data["end_measure"],
                                    data.get("iterator_voice_id"), data.get("times"),
                                    data.get("count_voice_id"), data.get("collection_voice_id"),
                                    data.get("condition_voice_id"),
                                    data["test_at_end"]))
    voltas = []
    for index, item in enumerate(_list(body["voltas"], "score.voltas")):
        location = f"score.voltas[{index}]"
        data = _object(item, {"id", "condition_voice_id", "endings"}, location)
        endings = []
        for ending_index, item_value in enumerate(_list(data["endings"], location + ".endings")):
            ending_location = f"{location}.endings[{ending_index}]"
            ending = _object(item_value, {"numbers", "start_measure", "end_measure"}, ending_location)
            numbers = tuple(_list(ending["numbers"], ending_location + ".numbers"))
            endings.append(VoltaEnding(numbers, ending["start_measure"], ending["end_measure"]))
        voltas.append(VoltaGroup(data["id"], data["condition_voice_id"], tuple(endings)))
    return (tuple(voice_groups), tuple(phrases), tuple(relations), tuple(sections),
            tuple(references), tuple(repeats), tuple(voltas))


def from_data(value: object) -> Score:
    _depth(value)
    root = _object(value, {"format", "format_version", "language_version", "score"}, "document")
    if root["format"] != FORMAT:
        raise SerializationError(f"Expected format {FORMAT!r}")
    version = root["language_version"]
    v02_fields = {"voice_groups", "phrases", "relations", "sections",
                  "section_references", "repeats", "voltas"}
    body = _object(root["score"], {"metadata", "parts", "spanners"} |
                   (v02_fields if version == "0.2" else set()), "score")
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
                    voice_data = _object(voice_value, {"id", "staff", "events"},
                                         f"{location}.voices[{vi}]", {"name"})
                    voices.append(Voice(voice_data["id"], voice_data["staff"], tuple(
                        _read_event(event, f"{location}.voices[{vi}].events[{ei}]")
                        for ei, event in enumerate(_list(voice_data["events"], f"{location}.voices[{vi}].events"))),
                        voice_data.get("name")))
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
    structures = _read_v02_body(body) if version == "0.2" else ((), (), (), (), (), (), ())
    try:
        return validate_score(Score(dict(metadata), tuple(parts), tuple(spanners),
                                    root["format_version"], root["language_version"],
                                    *structures))
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

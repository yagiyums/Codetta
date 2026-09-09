"""Plan phrase playback, synthesize PCM WAV, and play it on Windows.

Control phrases sound first. Enclosing time scales also affect nested control
phrases, but control durations never contribute to the numeric result.
"""

from __future__ import annotations

from array import array
from dataclasses import dataclass
from fractions import Fraction
import math
from pathlib import Path
import sys
import tempfile
from typing import Callable, Iterator
import wave

from codetta import ir
from codetta.semantics import CodettaError
from performer.evaluator import evaluate

SAMPLE_RATE = 44100
DEFAULT_MAX_SECONDS = 300


@dataclass(frozen=True)
class Sound:
    beats: Fraction
    pitch: int
    sign: int
    role: str
    location: str


@dataclass(frozen=True)
class Performance:
    sounds: tuple[Sound, ...]
    result: Fraction

    @property
    def beats(self) -> Fraction:
        return sum((sound.beats for sound in self.sounds), Fraction(0))


def _sounds(node: ir.Phrase | ir.Emit, stretch: Fraction, sign: int,
            role: str, location: str) -> Iterator[Sound]:
    if stretch == 0:
        return
    if isinstance(node, ir.Emit):
        yield from _sounds(node.body, stretch, sign, role, location + "/output")
    elif isinstance(node, ir.Span):
        yield Sound(Fraction(node.beats) * stretch, node.pitch, sign, role, location)
    elif isinstance(node, ir.Zero):
        return
    elif isinstance(node, ir.Invert):
        yield from _sounds(node.body, stretch, -sign, role, location + "/invert")
    elif isinstance(node, ir.Sequence):
        for i, child in enumerate(node.children, 1):
            yield from _sounds(child, stretch, sign, role, f"{location}/phrase[{i}]")
    elif isinstance(node, (ir.Scale, ir.Unscale)):
        yield from _sounds(node.factor, stretch, 1, "control", location + "/control")
        factor = evaluate(node.factor)
        if isinstance(node, ir.Unscale):
            factor = 1 / factor  # plan() has already checked every division.
        yield from _sounds(node.body, stretch * abs(factor),
                           sign * (-1 if factor < 0 else 1), role, location + "/body")
    else:
        raise TypeError(f"Unsupported IR node: {type(node).__name__}")


def plan(program: ir.Emit) -> Performance:
    # Validate first: e.g. 0 * (1 / 0) must still report division by zero.
    result = evaluate(program)
    try:
        sounds = tuple(_sounds(program, Fraction(1), 1, "body", "score"))
    except RecursionError as exc:
        raise CodettaError("Score nesting is too deep to play") from exc
    return Performance(sounds, result)


def _validate_audio(performance: Performance, bpm: int, max_seconds: int) -> None:
    if type(bpm) is not int or bpm <= 0:
        raise CodettaError("Tempo must be a positive integer BPM")
    if type(max_seconds) is not int or max_seconds <= 0:
        raise CodettaError("Maximum audio duration must be a positive integer")
    seconds = performance.beats * 60 / bpm
    if seconds > max_seconds:
        raise CodettaError(f"Performance exceeds {max_seconds} seconds; increase --max-seconds or use --no-play")


def _pcm(pitch: int, frames: int) -> Iterator[bytes]:
    frequency = 440.0 * 2 ** ((pitch - 69) / 12)
    # Skip tones beyond Nyquist rather than creating aliased pitches.
    if frequency >= SAMPLE_RATE / 2:
        raise CodettaError("Pitch exceeds the WAV sample rate's audible range")
    fade = max(1, min(220, frames // 2))
    for start in range(0, frames, 4096):
        chunk = array("h")
        for sample in range(start, min(start + 4096, frames)):
            envelope = min(1.0, sample / fade, (frames - 1 - sample) / fade)
            fundamental = math.sin(2 * math.pi * frequency * sample / SAMPLE_RATE)
            chunk.append(round(10000 * envelope * fundamental))
        if sys.byteorder != "little":
            chunk.byteswap()
        yield chunk.tobytes()


def write_wav(performance: Performance, path: str | Path, *, bpm: int = 120,
              max_seconds: int = DEFAULT_MAX_SECONDS) -> Path:
    _validate_audio(performance, bpm, max_seconds)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(destination), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        elapsed, written = Fraction(0), 0
        for sound in performance.sounds:
            elapsed += sound.beats
            end_frame = round(elapsed * 60 * SAMPLE_RATE / bpm)
            for chunk in _pcm(sound.pitch, end_frame - written):
                output.writeframesraw(chunk)
            written = end_frame
    return destination


def play(performance: Performance, *, bpm: int = 120,
         max_seconds: int = DEFAULT_MAX_SECONDS,
         on_sound: Callable[[Sound], None] | None = None) -> None:
    _validate_audio(performance, bpm, max_seconds)
    if sys.platform != "win32":
        raise CodettaError("Live playback requires Windows; use --no-play --wav output.wav")
    import winsound

    # A separate phrase WAV allows progress callbacks at the moment each phrase sounds.
    with tempfile.TemporaryDirectory(prefix="codetta-") as folder:
        path = Path(folder) / "phrase.wav"
        for sound in performance.sounds:
            write_wav(Performance((sound,), Fraction(0)), path, bpm=bpm, max_seconds=max_seconds)
            if on_sound is not None:
                on_sound(sound)
            try:
                winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_NODEFAULT)
            except RuntimeError as exc:
                raise CodettaError("Windows audio playback failed; use --no-play --wav output.wav") from exc

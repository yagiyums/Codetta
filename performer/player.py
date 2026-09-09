"""Play the notes in Score Model with simultaneous voices and exact timing."""

from __future__ import annotations

from array import array
from dataclasses import dataclass
from fractions import Fraction
import math
from pathlib import Path
import sys
import tempfile
import wave

from codetta.score_model import Chord, Note, Score, validate_score
from codetta.semantics import CodettaError

SAMPLE_RATE = 44_100
DEFAULT_MAX_SECONDS = 300


@dataclass(frozen=True)
class Sound:
    start: Fraction
    beats: Fraction
    pitches: tuple[int, ...]
    event_ids: tuple[str, ...]
    staff: int
    voice: int


@dataclass(frozen=True)
class Performance:
    sounds: tuple[Sound, ...]
    result: Fraction
    beats: Fraction


def plan(score: Score, result: Fraction) -> Performance:
    validate_score(score)
    part = score.parts[0]
    tie_next = {spanner.start_anchor: spanner.end_anchor for spanner in score.spanners
                if spanner.type == "tie"}
    tied_to = {spanner.end_anchor for spanner in score.spanners if spanner.type == "tie"}
    notes: dict[str, tuple[Note, Fraction, int, int]] = {}
    sounds = []
    total = Fraction(0)
    for staff_number, staff in enumerate(part.staves, 1):
        offset = Fraction(0)
        for measure in staff.measures:
            for voice_number, voice in enumerate(measure.voices, 1):
                for event in voice.events:
                    start = offset + event.start * 4
                    if isinstance(event, Note):
                        notes[event.id] = (event, start, staff_number, voice_number)
                    elif isinstance(event, Chord):
                        sounds.append(Sound(start, event.duration * 4,
                                            tuple(pitch.midi for pitch in event.pitches),
                                            (event.id,), staff_number, voice_number))
            offset += measure.duration * 4
        total = max(total, offset)
    visited: set[str] = set()
    for identifier, (note, start, staff, voice) in notes.items():
        if identifier in tied_to:
            continue
        ids = []
        duration = Fraction(0)
        current = identifier
        while current:
            if current in visited:
                raise CodettaError(f"Tie cycle while planning event {current}")
            visited.add(current)
            current_note, _, current_staff, current_voice = notes[current]
            if current_staff != staff or current_voice != voice or current_note.pitch != note.pitch:
                raise CodettaError("Invalid tie chain reached the player")
            ids.append(current)
            duration += current_note.duration * 4
            current = tie_next.get(current, "")
        sounds.append(Sound(start, duration, (note.pitch.midi,), tuple(ids), staff, voice))
    sounds.sort(key=lambda sound: (sound.start, sound.staff, sound.voice, sound.event_ids))
    return Performance(tuple(sounds), result, total)


def _validate(performance: Performance, bpm: int, max_seconds: int) -> int:
    if type(bpm) is not int or bpm <= 0:
        raise CodettaError("Tempo must be a positive integer BPM")
    if type(max_seconds) is not int or max_seconds <= 0:
        raise CodettaError("Maximum audio duration must be a positive integer")
    seconds = performance.beats * 60 / bpm
    if seconds > max_seconds:
        raise CodettaError(f"Performance exceeds {max_seconds} seconds")
    return round(seconds * SAMPLE_RATE)


def write_wav(performance: Performance, path: str | Path, *, bpm: int = 120,
              max_seconds: int = DEFAULT_MAX_SECONDS) -> Path:
    frame_count = _validate(performance, bpm, max_seconds)
    scheduled = []
    for sound in performance.sounds:
        start = round(sound.start * 60 * SAMPLE_RATE / bpm)
        end = round((sound.start + sound.beats) * 60 * SAMPLE_RATE / bpm)
        scheduled.append((sound, start, end))
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(destination), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        for chunk_start in range(0, frame_count, 4096):
            chunk_end = min(frame_count, chunk_start + 4096)
            samples = array("h")
            for frame in range(chunk_start, chunk_end):
                sample = 0.0
                active_tones = 0
                for sound, start, end in scheduled:
                    if not start <= frame < end:
                        continue
                    local = frame - start
                    fade = max(1, min(220, (end - start) // 2))
                    envelope = min(1.0, local / fade, (end - 1 - frame) / fade)
                    for pitch in sound.pitches:
                        frequency = 440.0 * 2 ** ((pitch - 69) / 12)
                        if frequency >= SAMPLE_RATE / 2:
                            raise CodettaError("Pitch exceeds the WAV sample rate's audible range")
                        sample += envelope * math.sin(2 * math.pi * frequency * local / SAMPLE_RATE)
                        active_tones += 1
                samples.append(round(12_000 * sample / max(1, active_tones)))
            if sys.byteorder != "little":
                samples.byteswap()
            output.writeframesraw(samples.tobytes())
    return destination


def play(performance: Performance, *, bpm: int = 120,
         max_seconds: int = DEFAULT_MAX_SECONDS) -> None:
    if sys.platform != "win32":
        raise CodettaError("Live playback requires Windows; use --no-play --wav output.wav")
    import winsound
    with tempfile.TemporaryDirectory(prefix="codetta-") as folder:
        path = write_wav(performance, Path(folder) / "performance.wav", bpm=bpm,
                         max_seconds=max_seconds)
        try:
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_NODEFAULT)
        except RuntimeError as exc:
            raise CodettaError("Windows audio playback failed; use --no-play --wav output.wav") from exc

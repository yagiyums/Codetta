"""Execute and optionally play a .codetta program."""

import argparse
from pathlib import Path
import sys

from codetta.semantics import CodettaError, format_value
from performer.player import Sound, plan, play, write_wav
from performer.runtime import run


def _trace(sound: Sound) -> None:
    pitches = ",".join(str(pitch) for pitch in sound.pitches)
    print(f"t={sound.start}  {sound.beats} beats  MIDI {pitches}  staff {sound.staff}  {'+'.join(sound.event_ids)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Execute and play a Codetta .codetta score.")
    parser.add_argument("score", type=Path)
    parser.add_argument("--no-play", action="store_true", help="Evaluate without an audio device")
    parser.add_argument("--wav", type=Path, help="Export the notated performance as WAV")
    parser.add_argument("--bpm", type=int, default=120)
    parser.add_argument("--max-seconds", type=int, default=300)
    parser.add_argument("--trace", action="store_true", help="List the notes in performance order")
    args = parser.parse_args(argv)
    if args.score.suffix.lower() != ".codetta":
        parser.error("Performer input must be a .codetta file")
    if args.bpm <= 0 or args.max_seconds <= 0:
        parser.error("--bpm and --max-seconds must be positive integers")
    try:
        executed = run(args.score)
        if not args.no_play or args.wav or args.trace:
            performance = plan(executed.score, executed.value)
            if args.trace:
                for sound in performance.sounds:
                    _trace(sound)
            if args.wav:
                write_wav(performance, args.wav, bpm=args.bpm, max_seconds=args.max_seconds)
            if not args.no_play:
                play(performance, bpm=args.bpm, max_seconds=args.max_seconds)
    except (CodettaError, OSError, UnicodeError, KeyError) as exc:
        print(f"Performer: {exc}", file=sys.stderr)
        return 1
    print(format_value(executed.value))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

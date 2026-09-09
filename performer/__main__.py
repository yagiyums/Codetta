"""python -m performer score.svg [--no-play] [--wav output.wav]"""

import argparse
from pathlib import Path
import sys

from codetta.semantics import CodettaError, format_value
from performer.evaluator import evaluate
from performer.player import Sound, plan, play, write_wav
from performer.score_reader import read_score


def _trace(sound: Sound) -> None:
    sign = "-" if sound.sign < 0 else "+"
    print(f"{sound.role:7} {sign}{sound.beats} beats  MIDI {sound.pitch}  {sound.location}", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read, evaluate, and play a Codetta SVG score.")
    parser.add_argument("score", type=Path)
    parser.add_argument("--no-play", action="store_true", help="Evaluate without using an audio device")
    parser.add_argument("--wav", type=Path, help="Also export a WAV performance")
    parser.add_argument("--bpm", type=int, default=120, help="Quarter notes per minute (default: 120)")
    parser.add_argument("--max-seconds", type=int, default=300, help="Audio duration limit (default: 300)")
    parser.add_argument("--trace", action="store_true", help="Show each phrase, including negative contributions")
    args = parser.parse_args(argv)
    if args.bpm <= 0 or args.max_seconds <= 0:
        parser.error("--bpm and --max-seconds must be positive integers")
    try:
        program = read_score(args.score)
        if args.no_play and not args.wav and not args.trace:
            result = evaluate(program)
        else:
            performance = plan(program)
            result = performance.result
            if args.wav:
                write_wav(performance, args.wav, bpm=args.bpm, max_seconds=args.max_seconds)
            if args.no_play:
                if args.trace:
                    for sound in performance.sounds:
                        _trace(sound)
            else:
                play(performance, bpm=args.bpm, max_seconds=args.max_seconds,
                     on_sound=_trace if args.trace else None)
    except (CodettaError, OSError, UnicodeError) as exc:
        print(f"Performer: {exc}", file=sys.stderr)
        return 1
    print(format_value(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

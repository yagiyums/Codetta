"""Musical phrases. Pitch is a performance annotation, never a numeric value."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class Span:
    beats: int
    pitch: int = 60  # MIDI C4

    def __post_init__(self) -> None:
        if type(self.beats) is not int or self.beats <= 0:
            raise ValueError("Span needs a positive integer number of beats")
        if type(self.pitch) is not int or not 0 <= self.pitch <= 127:
            raise ValueError("Pitch must be a MIDI integer from 0 to 127")


@dataclass(frozen=True)
class Zero:
    pass


@dataclass(frozen=True)
class Sequence:
    children: tuple[Phrase, ...]

    def __post_init__(self) -> None:
        if len(self.children) < 2:
            raise ValueError("A sequence needs at least two phrases")


@dataclass(frozen=True)
class Invert:
    body: Phrase


@dataclass(frozen=True)
class Scale:
    body: Phrase
    factor: Phrase


@dataclass(frozen=True)
class Unscale:
    body: Phrase
    factor: Phrase


Phrase = Union[Span, Zero, Sequence, Invert, Scale, Unscale]


@dataclass(frozen=True)
class Emit:
    body: Phrase

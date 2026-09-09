"""Small execution IR lowered from the score-derived Codetta AST."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import TypeAlias


@dataclass(frozen=True)
class Constant:
    value: Fraction


@dataclass(frozen=True)
class Add:
    terms: tuple[Value, ...]


@dataclass(frozen=True)
class Multiply:
    factors: tuple[Value, ...]


@dataclass(frozen=True)
class Negate:
    body: Value


@dataclass(frozen=True)
class Reciprocal:
    body: Value


Value: TypeAlias = Constant | Add | Multiply | Negate | Reciprocal


@dataclass(frozen=True)
class Block:
    body: Value


@dataclass(frozen=True)
class Program:
    blocks: tuple[Block, ...]

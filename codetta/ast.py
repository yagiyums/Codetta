"""Semantic syntax tree derived from Codetta notation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeAlias


@dataclass(frozen=True)
class SourceRef:
    event_ids: tuple[str, ...] = ()
    spanner_ids: tuple[str, ...] = ()
    measure_id: str | None = None


@dataclass(frozen=True)
class Integer:
    value: int
    source_ref: SourceRef = field(default_factory=SourceRef, compare=False)


@dataclass(frozen=True)
class Sum:
    terms: tuple[Expression, ...]
    source_ref: SourceRef = field(default_factory=SourceRef, compare=False)


@dataclass(frozen=True)
class Product:
    factors: tuple[Expression, ...]
    source_ref: SourceRef = field(default_factory=SourceRef, compare=False)


@dataclass(frozen=True)
class Negate:
    body: Expression
    source_ref: SourceRef = field(default_factory=SourceRef, compare=False)


@dataclass(frozen=True)
class Reciprocal:
    body: Expression
    source_ref: SourceRef = field(default_factory=SourceRef, compare=False)


Expression: TypeAlias = Integer | Sum | Product | Negate | Reciprocal


@dataclass(frozen=True)
class Block:
    expression: Expression
    source_ref: SourceRef = field(default_factory=SourceRef, compare=False)


@dataclass(frozen=True)
class Program:
    blocks: tuple[Block, ...]

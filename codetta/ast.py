"""Syntax tree of the input calculator language (before musical lowering)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class Integer:
    value: int


@dataclass(frozen=True)
class Negate:
    body: Expression


@dataclass(frozen=True)
class Add:
    left: Expression
    right: Expression


@dataclass(frozen=True)
class Subtract:
    left: Expression
    right: Expression


@dataclass(frozen=True)
class Multiply:
    left: Expression
    right: Expression


@dataclass(frozen=True)
class Divide:
    left: Expression
    right: Expression


Expression = Union[Integer, Negate, Add, Subtract, Multiply, Divide]


@dataclass(frozen=True)
class Output:
    body: Expression

"""Typed execution IR lowered from the score-derived Codetta AST."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import TypeAlias

from codetta.type_system import Type, VOID


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
class TypedConstant:
    value: object
    value_type: Type


@dataclass(frozen=True)
class Load:
    symbol: str
    value_type: Type


@dataclass(frozen=True)
class Unary:
    operator: str
    body: ValueV02
    value_type: Type


@dataclass(frozen=True)
class Binary:
    operator: str
    left: ValueV02
    right: ValueV02
    value_type: Type


@dataclass(frozen=True)
class Compare:
    operator: str
    left: ValueV02
    right: ValueV02
    value_type: Type


@dataclass(frozen=True)
class MakeArray:
    elements: tuple[ValueV02, ...]
    value_type: Type


@dataclass(frozen=True)
class Index:
    array: ValueV02
    index: ValueV02
    value_type: Type


@dataclass(frozen=True)
class MakeStruct:
    fields: tuple[tuple[str, ValueV02], ...]
    value_type: Type


@dataclass(frozen=True)
class GetField:
    value: ValueV02
    field_name: str
    value_type: Type


@dataclass(frozen=True)
class Call:
    function: str
    arguments: tuple[ValueV02, ...]
    value_type: Type


ValueV02: TypeAlias = (
    Value | TypedConstant | Load | Unary | Binary | Compare | MakeArray |
    Index | MakeStruct | GetField | Call
)


@dataclass(frozen=True)
class Store:
    symbol: str
    value: ValueV02
    value_type: Type


@dataclass(frozen=True)
class Branch:
    condition: ValueV02
    true_body: tuple[Instruction, ...]
    false_body: tuple[Instruction, ...]


@dataclass(frozen=True)
class ForLoop:
    iterator: str
    iterable: ValueV02
    body: tuple[Instruction, ...]


@dataclass(frozen=True)
class WhileLoop:
    condition: ValueV02
    body: tuple[Instruction, ...]
    test_at_end: bool = False


@dataclass(frozen=True)
class ReturnValue:
    value: ValueV02 | None = None


Instruction: TypeAlias = Store | Branch | ForLoop | WhileLoop | ReturnValue


@dataclass(frozen=True)
class Function:
    name: str
    parameters: tuple[tuple[str, Type], ...]
    body: tuple[Instruction, ...]
    result_type: Type = VOID


@dataclass(frozen=True)
class Block:
    body: Value


@dataclass(frozen=True)
class Program:
    blocks: tuple[Block, ...] = ()
    main: tuple[Instruction, ...] = ()
    functions: tuple[Function, ...] = ()
    result_symbol: str | None = None

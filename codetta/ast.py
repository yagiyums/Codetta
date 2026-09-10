"""Semantic syntax tree derived from Codetta notation.

The original expression nodes remain the Codetta v0.1 surface.  Codetta v0.2
adds statements, data structures and named sections without changing the v0.1
constructor shapes used by existing clients.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeAlias


@dataclass(frozen=True)
class SourceRef:
    event_ids: tuple[str, ...] = ()
    spanner_ids: tuple[str, ...] = ()
    measure_id: str | None = None
    voice_ids: tuple[str, ...] = ()
    structure_ids: tuple[str, ...] = ()


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
class FloatLiteral:
    significand: int
    exponent: int
    source_ref: SourceRef = field(default_factory=SourceRef, compare=False)


@dataclass(frozen=True)
class BoolLiteral:
    value: bool
    source_ref: SourceRef = field(default_factory=SourceRef, compare=False)


@dataclass(frozen=True)
class VariableRef:
    name: str
    source_ref: SourceRef = field(default_factory=SourceRef, compare=False)


@dataclass(frozen=True)
class UnaryExpr:
    operator: str
    body: ExpressionV02
    source_ref: SourceRef = field(default_factory=SourceRef, compare=False)


@dataclass(frozen=True)
class BinaryExpr:
    operator: str
    left: ExpressionV02
    right: ExpressionV02
    source_ref: SourceRef = field(default_factory=SourceRef, compare=False)


@dataclass(frozen=True)
class Comparison:
    operator: str
    left: ExpressionV02
    right: ExpressionV02
    source_ref: SourceRef = field(default_factory=SourceRef, compare=False)


@dataclass(frozen=True)
class ArrayLiteral:
    elements: tuple[ExpressionV02, ...]
    source_ref: SourceRef = field(default_factory=SourceRef, compare=False)


@dataclass(frozen=True)
class ArrayAccess:
    array: ExpressionV02
    index: ExpressionV02
    source_ref: SourceRef = field(default_factory=SourceRef, compare=False)


@dataclass(frozen=True)
class StructLiteral:
    fields: tuple[tuple[str, ExpressionV02], ...]
    source_ref: SourceRef = field(default_factory=SourceRef, compare=False)


@dataclass(frozen=True)
class FieldAccess:
    value: ExpressionV02
    field_name: str
    source_ref: SourceRef = field(default_factory=SourceRef, compare=False)


@dataclass(frozen=True)
class FunctionCall:
    function_name: str
    arguments: tuple[ExpressionV02, ...]
    source_ref: SourceRef = field(default_factory=SourceRef, compare=False)


ExpressionV02: TypeAlias = (
    Expression | FloatLiteral | BoolLiteral | VariableRef | UnaryExpr |
    BinaryExpr | Comparison | ArrayLiteral | ArrayAccess | StructLiteral |
    FieldAccess | FunctionCall
)


@dataclass(frozen=True)
class Assignment:
    target: str
    value: ExpressionV02
    source_ref: SourceRef = field(default_factory=SourceRef, compare=False)


@dataclass(frozen=True)
class If:
    condition: ExpressionV02
    true_body: tuple[Statement, ...]
    false_body: tuple[Statement, ...] = ()
    source_ref: SourceRef = field(default_factory=SourceRef, compare=False)


@dataclass(frozen=True)
class For:
    iterator: str
    iterable: ExpressionV02
    body: tuple[Statement, ...]
    source_ref: SourceRef = field(default_factory=SourceRef, compare=False)


@dataclass(frozen=True)
class While:
    condition: ExpressionV02
    body: tuple[Statement, ...]
    test_at_end: bool = False
    source_ref: SourceRef = field(default_factory=SourceRef, compare=False)


@dataclass(frozen=True)
class Return:
    value: ExpressionV02 | None = None
    source_ref: SourceRef = field(default_factory=SourceRef, compare=False)


Statement: TypeAlias = Assignment | If | For | While | Return


@dataclass(frozen=True)
class FunctionDecl:
    name: str
    parameters: tuple[str, ...]
    body: tuple[Statement, ...]
    source_ref: SourceRef = field(default_factory=SourceRef, compare=False)


@dataclass(frozen=True)
class Block:
    expression: Expression
    source_ref: SourceRef = field(default_factory=SourceRef, compare=False)


@dataclass(frozen=True)
class Program:
    blocks: tuple[Block, ...] = ()
    statements: tuple[Statement, ...] = ()
    functions: tuple[FunctionDecl, ...] = ()
    language_version: str = "0.1"

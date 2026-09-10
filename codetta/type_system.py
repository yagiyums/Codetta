"""Static types shared by Codetta semantic analysis and execution IR."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias


@dataclass(frozen=True)
class ScalarType:
    name: str

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True)
class ArrayType:
    element: Type

    def __str__(self) -> str:
        return f"Array<{self.element}>"


@dataclass(frozen=True)
class StructType:
    fields: tuple[tuple[str, Type], ...]

    def __str__(self) -> str:
        body = ", ".join(f"{name}: {kind}" for name, kind in self.fields)
        return f"Struct{{{body}}}"

    def field(self, name: str) -> Type | None:
        return next((kind for field_name, kind in self.fields if field_name == name), None)


@dataclass(frozen=True)
class FunctionType:
    parameters: tuple[Type, ...]
    result: Type

    def __str__(self) -> str:
        return f"Function<({', '.join(map(str, self.parameters))}) -> {self.result}>"


@dataclass(frozen=True)
class TupleType:
    items: tuple[Type, ...]

    def __str__(self) -> str:
        return f"Tuple<{', '.join(map(str, self.items))}>"


Type: TypeAlias = ScalarType | ArrayType | StructType | FunctionType | TupleType

INT = ScalarType("Int")
RATIONAL = ScalarType("Rational")
FLOAT = ScalarType("Float")
BOOL = ScalarType("Bool")
VOID = ScalarType("Void")


def is_numeric(kind: Type) -> bool:
    return kind in (INT, RATIONAL, FLOAT)


def numeric_result(left: Type, right: Type, *, division: bool = False) -> Type | None:
    if not is_numeric(left) or not is_numeric(right):
        return None
    if FLOAT in (left, right):
        return FLOAT
    if division or RATIONAL in (left, right):
        return RATIONAL
    return INT


def compatible(expected: Type, actual: Type) -> bool:
    """Return whether ``actual`` can be assigned without losing information."""
    if expected == actual:
        return True
    if expected == RATIONAL and actual == INT:
        return True
    if expected == FLOAT and is_numeric(actual):
        return True
    return False

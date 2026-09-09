"""Parser for the v0.1 arithmetic source accepted by Conductor."""

from codetta import ast
from codetta.semantics import CodettaError


class ParseError(CodettaError):
    pass


class _Parser:
    def __init__(self, source: str):
        self.source = source
        self.pos = 0

    def peek(self) -> str:
        while self.pos < len(self.source) and self.source[self.pos].isspace():
            self.pos += 1
        return self.source[self.pos:self.pos + 1]

    def error(self, message: str) -> ParseError:
        line = self.source.count("\n", 0, self.pos) + 1
        column = self.pos - self.source.rfind("\n", 0, self.pos)
        return ParseError(f"{message} at line {line}, column {column}")

    @staticmethod
    def add(left: ast.Expression, right: ast.Expression) -> ast.Sum:
        terms = left.terms + (right,) if isinstance(left, ast.Sum) else (left, right)
        return ast.Sum(terms)

    @staticmethod
    def multiply(left: ast.Expression, right: ast.Expression) -> ast.Product:
        factors = left.factors + (right,) if isinstance(left, ast.Product) else (left, right)
        return ast.Product(factors)

    def expression(self) -> ast.Expression:
        node = self.term()
        while self.peek() in ("+", "-"):
            operator = self.peek()
            self.pos += 1
            right = self.term()
            node = self.add(node, right if operator == "+" else ast.Negate(right))
        return node

    def term(self) -> ast.Expression:
        node = self.unary()
        while self.peek() in ("*", "/"):
            operator = self.peek()
            self.pos += 1
            right = self.unary()
            node = self.multiply(node, right if operator == "*" else ast.Reciprocal(right))
        return node

    def unary(self) -> ast.Expression:
        if self.peek() == "-":
            self.pos += 1
            return ast.Negate(self.unary())
        return self.primary()

    def primary(self) -> ast.Expression:
        character = self.peek()
        if character == "(":
            self.pos += 1
            result = self.expression()
            if self.peek() != ")":
                raise self.error("Expected ')'")
            self.pos += 1
            return result
        if character and character.isascii() and character.isdigit():
            start = self.pos
            while self.pos < len(self.source) and self.source[self.pos].isascii() and self.source[self.pos].isdigit():
                self.pos += 1
            try:
                return ast.Integer(int(self.source[start:self.pos]))
            except ValueError as exc:
                raise self.error("Integer literal is too long") from exc
        raise self.error("Expected an integer, '-' or '('")


def parse(source: str) -> ast.Program:
    parser = _Parser(source)
    try:
        expression = parser.expression()
    except RecursionError as exc:
        raise ParseError("Expression nesting is too deep") from exc
    if parser.peek():
        raise parser.error(f"Unexpected character {parser.peek()!r}")
    return ast.Program((ast.Block(expression),))

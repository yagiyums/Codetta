"""Recursive descent parser; never executes the source as Python."""

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

    def expression(self) -> ast.Expression:
        node = self.term()
        while self.peek() in ("+", "-"):
            op = self.peek()
            self.pos += 1
            right = self.term()
            node = ast.Add(node, right) if op == "+" else ast.Subtract(node, right)
        return node

    def term(self) -> ast.Expression:
        node = self.unary()
        while self.peek() in ("*", "/"):
            op = self.peek()
            self.pos += 1
            right = self.unary()
            node = ast.Multiply(node, right) if op == "*" else ast.Divide(node, right)
        return node

    def unary(self) -> ast.Expression:
        if self.peek() == "-":
            self.pos += 1
            return ast.Negate(self.unary())
        return self.primary()

    def primary(self) -> ast.Expression:
        char = self.peek()
        if char == "(":
            self.pos += 1
            node = self.expression()
            if self.peek() != ")":
                raise self.error("Expected ')'")
            self.pos += 1
            return node
        if char and "0" <= char <= "9":
            start = self.pos
            while self.pos < len(self.source) and "0" <= self.source[self.pos] <= "9":
                self.pos += 1
            try:
                return ast.Integer(int(self.source[start:self.pos]))
            except ValueError as exc:
                raise self.error("Integer literal is too long") from exc
        raise self.error("Expected an integer, '-' or '('")


def parse(source: str) -> ast.Output:
    parser = _Parser(source)
    try:
        result = parser.expression()
    except RecursionError as exc:
        raise ParseError("Expression nesting is too deep") from exc
    if parser.peek():
        raise parser.error(f"Unexpected character {parser.peek()!r}")
    return ast.Output(result)

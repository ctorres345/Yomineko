"""A fake tokenizer for tests, so they need neither SudachiPy nor its dictionary."""

from __future__ import annotations

from yomineko.analyze.tokenizer import Token


def tok(
    surface: str,
    reading: str | None = None,
    pos: str = "名詞",
    sub_pos: str = "普通名詞",
    normalized: str | None = None,
) -> Token:
    return Token(
        surface=surface,
        normalized=normalized or surface,
        reading=reading or surface,
        pos=pos,
        sub_pos=sub_pos,
    )


class FakeTokenizer:
    """Returns the tokens registered for a text, and remembers every text it was asked about."""

    def __init__(self, table: dict[str, list[Token]]):
        self.table = table
        self.calls: list[str] = []

    def tokenize(self, text: str) -> list[Token]:
        self.calls.append(text)
        return self.table.get(text, [])

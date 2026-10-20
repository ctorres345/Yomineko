"""Split Japanese text into words.

The tokenizer is optional: it needs SudachiPy and its 77 MB dictionary, installed with
``pip install yomineko[analyze]``. Nothing else in yomineko needs it, so the import happens
only when ``SudachiTokenizer`` is created.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from yomineko.analyze.dictionary.text import kata_to_hira
from yomineko.errors import MissingExtraError

INSTALL_HINT = 'Install the analysis tools with: pip install "yomineko[analyze]"'
_KANA_ONLY = re.compile(r"[ぁ-んァ-ヶー]+")


@dataclass(frozen=True)
class Token:
    surface: str  # as written in the text
    normalized: str  # the tokenizer's normalised form, used to guess the dictionary entry
    reading: str  # hiragana: the dictionary form for kana-only words, else the reading
    pos: str  # part of speech, e.g. "名詞"
    sub_pos: str = ""  # e.g. "固有名詞" (proper noun)

    @property
    def is_kana(self) -> bool:
        return bool(_KANA_ONLY.fullmatch(self.surface))


class Tokenizer(Protocol):
    def tokenize(self, text: str) -> list[Token]: ...


class SudachiTokenizer:
    """SudachiPy in split mode C (the longest units), as the prototype used."""

    def __init__(self) -> None:
        try:
            from sudachipy import dictionary
            from sudachipy import tokenizer as sudachi_tokenizer
        except ImportError as e:
            raise MissingExtraError(f"SudachiPy is not installed. {INSTALL_HINT}") from e
        try:
            self._tokenizer = dictionary.Dictionary().tokenizer()
        except Exception as e:  # the dictionary package is missing or damaged
            raise MissingExtraError(f"The Sudachi dictionary is missing. {INSTALL_HINT}") from e
        self._mode = sudachi_tokenizer.Tokenizer.SplitMode.C

    def tokenize(self, text: str) -> list[Token]:
        out = []
        for m in self._tokenizer.tokenize(text, self._mode):
            pos = m.part_of_speech()
            surface = m.surface()
            kana_only = bool(_KANA_ONLY.fullmatch(surface))
            reading = kata_to_hira(m.dictionary_form() if kana_only else m.reading_form())
            out.append(Token(surface, m.normalized_form(), reading, pos[0], pos[1]))
        return out

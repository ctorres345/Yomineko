"""The script data model (schema v4).

JSON is canonical: ``Script`` is what ``yomineko extract`` writes and every exporter reads.
Exporters must check ``schema_version`` before touching the data.
"""

from __future__ import annotations

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION: Final = 4
# versions ``read_script`` accepts: older files upgrade in memory (the fields they lack default)
READABLE_VERSIONS: Final = (1, 2, 3, 4)
# stands in for the player/partner name in readable text; the tokenizer sees a space instead
NAME_PLACEHOLDER: Final = "〇〇"

TranslationSource = Literal["official", "dictionary", "machine", "reviewed"]
LineKind = Literal["dialogue", "term"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Translation(_Model):
    text: str
    source: TranslationSource


class Line(_Model):
    """One string found in the ROM.

    ``address`` is the integer file offset; ``id`` is the bus address as 8 hex digits
    (``"%08X" % (pointer_base + address)``). ``raw`` round-trips exactly; ``text`` is the
    readable form. Repeats of the same ``text`` carry ``duplicate_of`` (the first line's id).
    ``word_ids`` are the JMdict ids of the words in the line after review, sentence-safe only,
    in order of appearance without repeats; ``analyze`` fills them (schema 3).
    """

    id: str = Field(pattern=r"^[0-9A-F]{8}$")
    address: int = Field(ge=0)
    bank: str
    raw: str
    text: str
    kind: LineKind
    referenced: bool = True
    duplicate_of: str | None = None
    scene: str | None = None
    seen: bool | None = None
    translation: Translation | None = None
    word_ids: list[int] = Field(default_factory=list)


class Word(_Model):
    """A dictionary word found in the script, with how often it occurs.

    ``examples`` are ids of lines the word appears in (the first few, in ROM order);
    ``freq`` counts every occurrence. ``pos`` is the tokenizer's part of speech of the first
    occurrence. ``sentence_safe`` is False when a review correction is right for most lines
    but not all, so sentence cards should not show this word's meaning.
    ``jmdict_rank`` is how common the word is in general, from JMdict's newspaper counts: 1 to
    48 for the 24,000 most frequent words in bands of 500 (1 is the commonest 500), 60 for
    other common words, 100 for the rest. ``analyze`` fills it (schema 4); ``None`` means the
    script was analysed before, so a level cannot skip the word yet.
    """

    jmdict_id: int
    written: str
    kana: str
    kanji: str = ""
    pos: str = ""
    common: bool = False
    jmdict_rank: int | None = Field(default=None, ge=1)
    sentence_safe: bool = True
    meanings: list[str] = Field(default_factory=list)
    freq: int = Field(default=0, ge=0)
    examples: list[str] = Field(default_factory=list)


class Term(_Model):
    """A game name (item, move, place ...). ``jmdict_id`` is set by ``analyze`` when the text
    matches exactly one dictionary entry; ``literal`` then holds that entry's meanings."""

    jp: str
    category: str
    index: int = Field(ge=0)
    line_id: str | None = None
    literal: str | None = None
    official_en: str | None = None
    jmdict_id: int | None = None


class GameInfo(_Model):
    profile_id: str
    title: str
    platform: str
    rom_sha1: str = Field(pattern=r"^[0-9a-f]{40}$")


class DictionarySource(_Model):
    """Which dictionary the words came from; exports must carry this credit."""

    name: str = "JMdict"
    date: str
    source: str
    credit: str


class Script(_Model):
    schema_version: Literal[4] = SCHEMA_VERSION
    generator: str
    game: GameInfo
    lines: list[Line] = Field(default_factory=list)
    words: list[Word] = Field(default_factory=list)
    terms: list[Term] = Field(default_factory=list)
    dictionary: DictionarySource | None = None

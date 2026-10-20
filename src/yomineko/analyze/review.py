"""The review file: corrections to the dictionary entries picked for kana-only text.

The game is written almost entirely in kana, so the matcher sometimes picks the wrong
homophone (こと as 琴 instead of 事). A review records the fix once, as data that can be shared:
it holds JMdict entry ids, ROM line ids and the reviewer's own English, never game text.

    schema_version: 1
    profile: pmd-red-jp
    words:
      - {from: 1313580, to: 1313590}                  # every occurrence uses another entry
      - {from: 1313600, to: 1313610, sentence_safe: false}   # right for most lines, not all
      - {from: 2028920, drop: true}                   # not a real word in context
      - {from: 1160790, gloss: "amazing; great"}      # show this meaning instead
    lines:
      - {line: "0810ABCD", from: 1313580, to: 1577980}       # an exception for one line
    sentences:
      exclude: ["0810ABCD"]    # never a sentence card (system text, fragments)
      pin: ["0810ABCE"]        # always a sentence card

A line rule beats a word rule. Corrections are one step (A to B, never A to B to C).
Sentence rules are line ids only, so a game's list can be shared without its script.
"""

from __future__ import annotations

import os
import re
import threading
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any, Final, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from yomineko.analyze.dictionary.store import Dictionary
from yomineko.errors import YominekoError
from yomineko.model import Word
from yomineko.profile.loader import load_yaml

REVIEW_SCHEMA_VERSION: Final = 1
JAPANESE = re.compile("[ぁ-んァ-ヶ" + chr(0x4E00) + "-" + chr(0x9FFF) + "]")


class ReviewError(YominekoError):
    """A review file is missing, malformed, or for another game."""


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class WordRule(_Model):
    from_: int = Field(alias="from", gt=0)
    to: int | None = Field(default=None, gt=0)
    drop: bool = False
    gloss: str | None = None
    sentence_safe: bool = True

    @field_validator("gloss")
    @classmethod
    def _english_only(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("gloss must not be empty")
        if JAPANESE.search(v):
            raise ValueError("gloss must be your own English: review files never hold game text")
        return v

    @model_validator(mode="after")
    def _one_action(self) -> WordRule:
        if self.drop and (self.to is not None or self.gloss is not None):
            raise ValueError("a rule that drops a word cannot also remap it or change its meaning")
        if not (self.drop or self.to is not None or self.gloss is not None):
            raise ValueError("a rule needs one of: to, drop, gloss")
        if self.to == self.from_:
            raise ValueError("'to' is the same entry as 'from'")
        return self


class LineRule(_Model):
    line: str
    from_: int = Field(alias="from", gt=0)
    to: int | None = Field(default=None, gt=0)
    drop: bool = False

    @field_validator("line", mode="before")
    @classmethod
    def _quoted_hex(cls, v: Any) -> Any:
        return _line_id(v)

    @model_validator(mode="after")
    def _one_action(self) -> LineRule:
        if self.drop == (self.to is not None):
            raise ValueError("a line rule needs exactly one of: to, drop")
        if self.to == self.from_:
            raise ValueError("'to' is the same entry as 'from'")
        return self


def _line_id(v: Any) -> Any:
    if isinstance(v, int):
        raise ValueError('quote the line id, e.g. "0810ABCD": YAML reads 0810 as a number')
    if not (isinstance(v, str) and re.fullmatch(r"[0-9A-F]{8}", v)):
        raise ValueError('a line id is 8 upper-case hex digits, e.g. "0810ABCD"')
    return v


class SentenceRules(_Model):
    """Lines that never become sentence cards (``exclude``) and lines that always do (``pin``)."""

    exclude: list[str] = Field(default_factory=list)
    pin: list[str] = Field(default_factory=list)

    @field_validator("exclude", "pin", mode="before")
    @classmethod
    def _quoted_hex(cls, v: Any) -> Any:
        if isinstance(v, list):
            for item in v:
                _line_id(item)
        return v

    @model_validator(mode="after")
    def _disjoint(self) -> SentenceRules:
        both = sorted(set(self.exclude) & set(self.pin))
        if both:
            raise ValueError(f"line {both[0]} is both excluded and pinned")
        return self


class Review(_Model):
    schema_version: Literal[1] = REVIEW_SCHEMA_VERSION
    profile: str | None = None
    rom_sha1: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    words: list[WordRule] = Field(default_factory=list)
    lines: list[LineRule] = Field(default_factory=list)
    sentences: SentenceRules = Field(default_factory=SentenceRules)

    @model_validator(mode="after")
    def _no_duplicates(self) -> Review:
        word_ids = [r.from_ for r in self.words]
        dupes = sorted({i for i in word_ids if word_ids.count(i) > 1})
        if dupes:
            raise ValueError(f"more than one word rule for entry {dupes[0]}")
        line_keys = [(r.line, r.from_) for r in self.lines]
        if len(set(line_keys)) != len(line_keys):
            raise ValueError("more than one line rule for the same line and entry")
        return self

    def check_for(self, rom_sha1: str, profile_id: str) -> None:
        """Refuse a review written for another ROM (line ids are ROM addresses)."""
        if self.rom_sha1 and self.rom_sha1 != rom_sha1:
            raise ReviewError(
                f"this review is for ROM {self.rom_sha1}, but the script is from {rom_sha1}"
            )
        if self.profile and self.profile != profile_id:
            raise ReviewError(f"this review is for {self.profile!r}, not {profile_id!r}")


def review_data(review: Review) -> dict[str, Any]:
    """The review as plain data in the file's own spelling (``from``, not ``from_``)."""
    data: dict[str, Any] = {"schema_version": review.schema_version}
    if review.profile:
        data["profile"] = review.profile
    if review.rom_sha1:
        data["rom_sha1"] = review.rom_sha1
    words = []
    for w in review.words:
        item: dict[str, Any] = {"from": w.from_}
        if w.drop:
            item["drop"] = True
        if w.to is not None:
            item["to"] = w.to
        if w.gloss:
            item["gloss"] = w.gloss
        if not w.sentence_safe:
            item["sentence_safe"] = False
        words.append(item)
    if words:
        data["words"] = words
    lines = [
        {"line": r.line, "from": r.from_, **({"drop": True} if r.drop else {"to": r.to})}
        for r in review.lines
    ]
    if lines:
        data["lines"] = lines
    sentences = {k: v for k, v in review.sentences.model_dump().items() if v}
    if sentences:
        data["sentences"] = sentences
    return data


def save_review(review: Review, path: str | Path) -> Path:
    """Write the review as YAML (comments in an older file are not kept)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(review_data(review), sort_keys=False, allow_unicode=True)
    header = "# Your corrections, written by yomineko: dictionary ids and your own English only.\n"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    temporary.write_text(header + body, encoding="utf-8", newline="\n")
    os.replace(temporary, path)  # never half a file, even if the app quits mid-write
    return path


def parse_review(data: Any, where: str = "review") -> Review:
    try:
        return Review.model_validate(data if data is not None else {})
    except ValidationError as e:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()[:6]
        )
        raise ReviewError(f"{where}: invalid review: {problems}") from e


def load_review(path: str | Path) -> Review:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ReviewError(f"{path}: cannot read review file: {e.strerror or e}") from e
    try:
        data = load_yaml(text)
    except yaml.YAMLError as e:
        raise ReviewError(f"{path}: not valid YAML: {e}") from e
    return parse_review(data, str(path))


def packaged_review(profile_id: str) -> Review | None:
    """The review shipped for a game (``reviews/<profile-id>.yaml``), if there is one."""
    item = resources.files("yomineko.reviews").joinpath(f"{profile_id}.yaml")
    return load_review(Path(str(item))) if item.is_file() else None


def merge_reviews(reviews: Iterable[Review]) -> Review:
    """Combine reviews; a later review's rule replaces an earlier rule for the same word/line."""
    words: dict[int, WordRule] = {}
    lines: dict[tuple[str, int], LineRule] = {}
    exclude: dict[str, None] = {}  # dicts keep order; a later pin or exclude overrides an earlier
    pin: dict[str, None] = {}
    for review in reviews:
        words.update({r.from_: r for r in review.words})
        lines.update({(r.line, r.from_): r for r in review.lines})
        for line_id in review.sentences.exclude:
            exclude[line_id] = None
            pin.pop(line_id, None)
        for line_id in review.sentences.pin:
            pin[line_id] = None
            exclude.pop(line_id, None)
    return Review(
        words=list(words.values()),
        lines=list(lines.values()),
        sentences=SentenceRules(exclude=list(exclude), pin=list(pin)),
    )


@dataclass(frozen=True)
class Resolution:
    entry_id: int | None  # the entry to use, or None to drop this occurrence
    safe: bool  # False: a correction that is right for most lines but not all


@dataclass
class ReviewReport:
    rules: int = 0
    applied: int = 0
    changed_occurrences: int = 0
    unused: list[str] = field(default_factory=list)  # rules that matched nothing (stale?)
    unknown_ids: list[int] = field(default_factory=list)  # ids that are not in the dictionary


class ReviewApplier:
    """Applies a review to word occurrences, and keeps count of which rules did anything."""

    def __init__(self, review: Review, dictionary: Dictionary):
        self._review = review
        self._words = {r.from_: r for r in review.words}
        self._lines = {(r.line, r.from_): r for r in review.lines}
        self._word_hits: Counter[int] = Counter()
        self._line_hits: Counter[tuple[str, int]] = Counter()
        self._changed = 0
        mentioned = {r.from_ for r in review.words} | {r.from_ for r in review.lines}
        mentioned |= {r.to for r in review.words if r.to is not None}
        mentioned |= {r.to for r in review.lines if r.to is not None}
        self.unknown_ids = sorted(i for i in mentioned if dictionary.entry(i) is None)
        self._unknown = set(self.unknown_ids)

    def has_rule(self, entry_id: int) -> bool:
        return entry_id in self._words or any(k[1] == entry_id for k in self._lines)

    def resolve(self, entry_id: int, line_id: str) -> Resolution:
        line_rule = self._lines.get((line_id, entry_id))
        if line_rule is not None and line_rule.to not in self._unknown:
            self._line_hits[(line_id, entry_id)] += 1
            self._changed += 1
            return Resolution(None if line_rule.drop else line_rule.to, True)
        rule = self._words.get(entry_id)
        if rule is None:
            return Resolution(entry_id, True)
        self._word_hits[entry_id] += 1
        if rule.drop:
            self._changed += 1
            return Resolution(None, True)
        if rule.to is not None and rule.to not in self._unknown:
            self._changed += 1
            return Resolution(rule.to, rule.sentence_safe)
        return Resolution(entry_id, True)  # a meaning-only rule keeps the entry

    def apply_glosses(self, words: Iterable[Word]) -> None:
        """Replace the meanings of words the review gives a gloss for."""
        gloss = {(r.to or r.from_): r.gloss for r in self._review.words if r.gloss}
        for word in words:
            text = gloss.get(word.jmdict_id)
            if text:
                word.meanings = [text]

    def report(self) -> ReviewReport:
        unused = [
            f"word {r.from_}" for r in self._review.words if self._word_hits[r.from_] == 0
        ] + [
            f"line {r.line} word {r.from_}"
            for r in self._review.lines
            if self._line_hits[(r.line, r.from_)] == 0
        ]
        rules = len(self._review.words) + len(self._review.lines)
        return ReviewReport(
            rules=rules,
            applied=rules - len(unused),
            changed_occurrences=self._changed,
            unused=unused,
            unknown_ids=self.unknown_ids,
        )

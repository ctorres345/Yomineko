"""A small analysed script for the sentence, deck and spreadsheet tests.

60 words (ids 1..60, ids and ranks agree: id 1 is the most frequent) and a handful of invented
dialogue lines that pass the sentence filters. No game text.
"""

from __future__ import annotations

from yomineko.model import DictionarySource, GameInfo, Line, Script, Term, Word

SHA1 = "0123456789abcdef0123456789abcdef01234567"
CREDIT = "JMdict, (c) EDRDG, CC BY-SA 4.0"

# (line number, text, word ids). Each opens differently and says something different.
LINE_SPECS = [
    (1, "ようこそ　あたらしいまちへ。", [1, 2]),
    (2, "きょうは　いいてんきですね。", [2, 50]),
    (3, "そのほんは　とてもおもしろい。", [1, 44, 51]),
    (4, "あしたは　みんなであそぼう。", [3, 52]),
    (5, "おなかが　すいたからたべよう。", [4, 53, 54]),
]


def line_id(n: int) -> str:
    return f"{0x08000000 + n:08X}"


def make_line(n: int, text: str, ids: list[int] | None = None, **kw: object) -> Line:
    base: dict[str, object] = {
        "id": line_id(n),
        "address": n,
        "bank": "b",
        "raw": text,
        "text": text,
        "kind": "dialogue",
        "word_ids": ids or [],
    }
    base.update(kw)
    return Line.model_validate(base)


def make_words(count: int = 60) -> list[Word]:
    words = []
    for i in range(1, count + 1):
        kanji = "事" if i == 1 else ""
        words.append(
            Word(
                jmdict_id=i,
                written=kanji or f"ことば{i}",
                kana=f"ことば{i}" if i != 1 else "こと",
                kanji=kanji,
                pos="名詞",
                common=True,
                meanings=[f"meaning {i}; extra {i}", f"second {i}"],
                freq=1000 - i,
            )
        )
    return words


def make_script(**kw: object) -> Script:
    base: dict[str, object] = {
        "generator": "yomineko-test",
        "game": GameInfo(profile_id="demo", title="Demo Game", platform="gba", rom_sha1=SHA1),
        "lines": [make_line(n, t, ids) for n, t, ids in LINE_SPECS],
        "words": make_words(),
        "terms": [
            Term(jp="ボタン", category="item", index=0, jmdict_id=900, literal="button"),
            Term(jp="ボタン", category="move", index=1, jmdict_id=900, literal="button"),
            Term(jp="ボタン", category="item", index=2, jmdict_id=900, literal="button"),
            Term(jp="ぴかぴか", category="item", index=3),
        ],
        "dictionary": DictionarySource(date="2026-10-03", source="https://x", credit=CREDIT),
    }
    base.update(kw)
    return Script.model_validate(base)

import sys

import pytest

from yomineko.analyze.tokenizer import INSTALL_HINT, SudachiTokenizer, Token
from yomineko.errors import MissingExtraError


def test_a_missing_package_asks_for_the_extra(monkeypatch):
    monkeypatch.setitem(sys.modules, "sudachipy", None)  # makes `import sudachipy` fail
    with pytest.raises(MissingExtraError) as error:
        SudachiTokenizer()
    assert INSTALL_HINT in str(error.value)
    assert 'pip install "yomineko[analyze]"' in str(error.value)


def test_a_missing_dictionary_package_asks_for_the_extra(monkeypatch):
    pytest.importorskip("sudachipy")
    from sudachipy import dictionary as sudachi_dictionary

    def broken(*args, **kwargs):
        raise OSError("no dictionary")

    monkeypatch.setattr(sudachi_dictionary, "Dictionary", broken)
    with pytest.raises(MissingExtraError, match="dictionary is missing"):
        SudachiTokenizer()


def test_token_is_immutable_and_comparable():
    a = Token("ねこ", "猫", "ねこ", "名詞")
    assert a == Token("ねこ", "猫", "ねこ", "名詞", "")
    with pytest.raises(AttributeError):
        a.surface = "x"  # type: ignore[misc]


@pytest.fixture(scope="module")
def real_tokenizer():
    pytest.importorskip("sudachipy")
    pytest.importorskip("sudachidict_core")
    return SudachiTokenizer()


@pytest.mark.sudachi
def test_kana_words_get_their_dictionary_form_as_reading(real_tokenizer):
    tokens = real_tokenizer.tokenize("ねこがおちゃをのむ")
    neko = tokens[0]
    assert (neko.surface, neko.pos, neko.reading) == ("ねこ", "名詞", "ねこ")
    assert neko.is_kana
    assert tokens[-1].pos == "動詞" and tokens[-1].reading == "のむ"


@pytest.mark.sudachi
def test_kanji_words_get_a_hiragana_reading(real_tokenizer):
    token = real_tokenizer.tokenize("猫")[0]
    assert (token.surface, token.reading, token.is_kana) == ("猫", "ねこ", False)


@pytest.mark.sudachi
def test_particles_and_symbols_are_reported_with_their_part_of_speech(real_tokenizer):
    by_surface = {t.surface: t for t in real_tokenizer.tokenize("ねこが！")}
    assert by_surface["が"].pos == "助詞"
    assert by_surface["！"].pos == "補助記号"


@pytest.mark.sudachi
def test_empty_text(real_tokenizer):
    assert real_tokenizer.tokenize("") == []

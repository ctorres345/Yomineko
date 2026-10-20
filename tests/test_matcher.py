import pytest
from support.tinydict import TinyDictionary, noun, verb
from support.tokens import tok

from yomineko.analyze.dictionary.xml_parser import Entry, Sense
from yomineko.analyze.matcher import POS_MAP, candidates, is_inflected, pos_agrees

KOTO, KOTO_ZITHER, KOTO_CAPITAL = 9000001, 9000002, 9000003
IRAI_REQUEST, IRAI_SINCE = 9000004, 9000005
KAERU_RETURN, KAERU_CHANGE, KAERU_FROG = 9000008, 9000009, 9000010


def test_kana_only_homophones_are_ranked_by_frequency(mini_dict):
    token = tok("こと", pos="名詞")
    assert candidates(mini_dict, token) == [KOTO, KOTO_ZITHER, KOTO_CAPITAL]


def test_part_of_speech_beats_frequency(mini_dict):
    """A verb token prefers the verbs even though the noun frog would otherwise compete."""
    verb = candidates(mini_dict, tok("かえる", pos="動詞", sub_pos="一般"))
    assert verb == [KAERU_RETURN, KAERU_CHANGE, KAERU_FROG]
    noun = candidates(mini_dict, tok("かえる", pos="名詞"))
    assert noun[0] == KAERU_FROG, "only the frog is a noun, so it wins despite being uncommon"


def test_a_kanji_surface_trusts_the_tokenizers_guess(mini_dict):
    """依頼 written in kanji: the guess matches, so 以来 (a better-ranked homophone) is not even
    a candidate."""
    token = tok("依頼", reading="いらい", normalized="依頼")
    assert candidates(mini_dict, token) == [IRAI_REQUEST]


def test_a_kana_surface_still_prefers_a_common_guess_but_keeps_the_alternatives(mini_dict):
    """Same word spelled in kana: all homophones compete, and the tokenizer's common guess leads."""
    token = tok("いらい", reading="いらい", normalized="依頼")
    assert candidates(mini_dict, token) == [IRAI_REQUEST, IRAI_SINCE]


def test_without_a_guess_the_better_rank_wins(mini_dict):
    token = tok("いらい", reading="いらい", normalized="いらい")
    assert candidates(mini_dict, token) == [IRAI_SINCE, IRAI_REQUEST]  # 以来 nf05 beats 依頼 nf10


def test_katakana_and_hiragana_readings_find_the_same_entries(mini_dict):
    assert candidates(mini_dict, tok("ボタン", reading="ぼたん")) == [9000012]
    assert candidates(mini_dict, tok("ボタン", reading="ボタン")) == [9000012]


def test_a_word_not_in_the_dictionary_has_no_candidates(mini_dict):
    assert candidates(mini_dict, tok("ゔゔゔ")) == []


def test_the_order_is_always_the_same(mini_dict):
    token = tok("こと")
    assert candidates(mini_dict, token) == candidates(mini_dict, token)


# ---------------------------------------------------------- part-of-speech map


def entry_with(*pos_texts):
    return Entry(1, (), (("あ", 100),), tuple(Sense((p,), (), ("x",)) for p in pos_texts))


def test_pos_agrees_matches_substrings_of_jmdicts_descriptions():
    assert pos_agrees(entry_with("noun (common) (futsuumeishi)"), "名詞")
    assert pos_agrees(entry_with("Ichidan verb"), "動詞")
    assert pos_agrees(entry_with("adjective (keiyoushi)"), "形容詞")
    assert not pos_agrees(entry_with("Ichidan verb"), "名詞")
    assert pos_agrees(entry_with("adjectival nouns or quasi-adjectives (keiyodoshi)"), "形状詞")


def test_a_part_of_speech_we_do_not_map_always_agrees():
    assert pos_agrees(entry_with("anything"), "助詞")
    assert "助詞" not in POS_MAP


# ------------------------------------------------- inflected verbs written with kanji


HEAR, STEM_NOUN = 9100001, 9100002
STOP, QUIT = 9100003, 9100004
COME = 9100005


@pytest.fixture
def tiny():
    return TinyDictionary(
        [
            verb(HEAR, "聞く", "きく"),
            noun(STEM_NOUN, "忌諱", "きい"),  # sounds like the inflected stem
            verb(STOP, "止める", "とめる"),
            verb(QUIT, "止める", "やめる"),
            verb(COME, "来る", "くる"),
        ],
        common={HEAR, STEM_NOUN, STOP, QUIT, COME},
    )


def test_an_inflected_verb_finds_its_dictionary_entry_not_a_noun_that_sounds_like_the_stem(tiny):
    """聞い (the stem of 聞いて) is read きい; the entry is きく, and 忌諱 must not win."""
    token = tok("聞い", reading="きい", pos="動詞", sub_pos="一般", normalized="聞く")
    assert candidates(tiny, token) == [HEAR]


def test_an_irregular_stem_whose_reading_shares_no_sound_still_finds_its_entry(tiny):
    token = tok("来", reading="き", pos="動詞", sub_pos="非自立可能", normalized="来る")
    assert candidates(tiny, token) == [COME]


def test_the_reading_still_separates_two_verbs_written_the_same(tiny):
    quit_it = tok("止め", reading="やめ", pos="動詞", sub_pos="一般", normalized="止める")
    stop_it = tok("止め", reading="とめ", pos="動詞", sub_pos="一般", normalized="止める")
    assert candidates(tiny, quit_it)[0] == QUIT
    assert candidates(tiny, stop_it)[0] == STOP


def test_a_verb_in_its_dictionary_form_is_matched_as_before(tiny):
    token = tok("聞く", reading="きく", pos="動詞", sub_pos="一般", normalized="聞く")
    assert candidates(tiny, token) == [HEAR]


def test_a_verb_written_in_kana_is_not_treated_as_inflected(tiny):
    token = tok("きい", reading="きく", pos="動詞", sub_pos="一般", normalized="聞く")
    assert not is_inflected(token)

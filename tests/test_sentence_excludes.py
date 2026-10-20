import re

import pytest
import sentence_excludes as tool
import yaml
from support.study import line_id, make_line, make_script

from yomineko.analyze.review import parse_review
from yomineko.script_io import write_script

REVIEW = """\
# a review
schema_version: 1
profile: demo
words:
  - {from: 1, to: 2}   # keep me
sentences:
  # old list
  exclude:
    - "08000009"
  pin:
    - "08000002"
"""


def patterns(tmp_path, *lines):
    path = tmp_path / "patterns.txt"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def test_patterns_skip_blanks_and_comments_and_report_bad_ones(tmp_path):
    found = tool.read_patterns(patterns(tmp_path, "# note", "", "あ+", "い"))
    assert [p.pattern for p in found] == ["あ+", "い"]
    with pytest.raises(SystemExit, match="line 1"):
        tool.read_patterns(patterns(tmp_path, "("))


def test_matching_ids_are_sorted_and_unique():
    lines = [("08000002", "あい"), ("08000001", "いう"), ("08000003", "うえ")]
    assert tool.matching_ids(lines, [re.compile("い"), re.compile("あ")]) == [
        "08000001",
        "08000002",
    ]


def test_the_sentences_block_is_replaced_and_the_rest_kept():
    cut = tool.drop_sentences_block(REVIEW)
    assert "sentences" not in cut and "old list" not in cut
    assert "# a review" in cut and "keep me" in cut and cut.endswith("\n")


def test_update_keeps_pins_and_writes_the_new_excludes():
    updated = tool.update_review(REVIEW, ["08000005", "08000006"])
    review = parse_review(yaml.safe_load(updated))
    assert review.sentences.exclude == ["08000005", "08000006"]
    assert review.sentences.pin == ["08000002"] and len(review.words) == 1
    assert "keep me" in updated


def test_an_id_that_is_pinned_cannot_also_be_excluded():
    with pytest.raises(tool.ReviewError, match="both excluded and pinned"):
        tool.update_review(REVIEW, ["08000002"])


def test_main_updates_the_file_and_prints_counts_only(tmp_path, capsys):
    script = write_script(
        make_script(
            lines=[
                make_line(1, "デバッグ　テスト", [2]),
                make_line(2, "きょうは　いいてんきですね。", [2, 50]),
                make_line(3, "デバッグ　テスト", [2], duplicate_of=line_id(1)),
            ]
        ),
        tmp_path / "script.json",
    )
    review = tmp_path / "review.yaml"
    review.write_text("schema_version: 1\n", encoding="utf-8")
    code = tool.main([str(script), str(patterns(tmp_path, "デバッグ")), "--review", str(review)])
    out = capsys.readouterr().out
    assert code == 0 and "1 of 2 distinct dialogue lines excluded" in out
    assert "デバッグ" not in out
    updated = parse_review(yaml.safe_load(review.read_text(encoding="utf-8")))
    assert updated.sentences.exclude == [line_id(1)]


def test_main_reports_an_invalid_result(tmp_path, capsys):
    script = write_script(make_script(lines=[make_line(2, "あああ", [1])]), tmp_path / "s.json")
    review = tmp_path / "r.yaml"
    review.write_text('schema_version: 1\nsentences:\n  pin: ["08000002"]\n', encoding="utf-8")
    code = tool.main([str(script), str(patterns(tmp_path, "あ")), "--review", str(review)])
    assert code == 1 and "both excluded and pinned" in capsys.readouterr().err

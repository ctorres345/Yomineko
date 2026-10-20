"""The release workflow's check and notes (tools/release_notes.py)."""

import pytest
import release_notes
from release_notes import ReleaseError, notes, unwrap

INIT = '"""yomineko."""\n\n__version__ = "1.2.3"\n'
CHANGELOG = """# Changelog

## Unreleased

- not yet

## 1.2.3 (2026-10-20)

- **A new thing.** It works.

## 1.2.2 (2026-10-01)

- An older thing.
"""


def test_the_notes_are_the_section_of_the_tagged_version_only():
    assert notes("v1.2.3", INIT, CHANGELOG) == "- **A new thing.** It works."


def test_the_last_section_runs_to_the_end_of_the_file():
    init = INIT.replace("1.2.3", "1.2.2")
    assert notes("v1.2.2", init, CHANGELOG) == "- An older thing."


@pytest.mark.parametrize("tag", ["v1.2.4", "1.2.3", "v1.2", "v1.2.3rc1"])
def test_a_tag_that_is_not_v_plus_the_package_version_is_refused(tag):
    with pytest.raises(ReleaseError, match="does not match"):
        notes(tag, INIT, CHANGELOG)


def test_wrapped_lines_are_joined_into_one_line_per_item_even_after_numbers_and_hashes():
    changelog = CHANGELOG.replace(
        "- **A new thing.** It works.",
        "- **A new thing.** It works\n  on every computer.\n"
        "- Fixes issue\n  #12 from\n  2026. Done.",
    )
    assert notes("v1.2.3", INIT, changelog) == (
        "- **A new thing.** It works on every computer.\n- Fixes issue #12 from 2026. Done."
    )


def test_unwrap_keeps_paragraphs_headings_and_code_apart():
    body = "A paragraph\nwrapped.\n\n### Fixed\n- one\n\n```\ncode\nkept\n```\nAfter."
    assert unwrap(body) == (
        "A paragraph wrapped.\n\n### Fixed\n- one\n\n```\ncode\nkept\n```\nAfter."
    )


def test_a_heading_with_trailing_spaces_still_counts():
    spaced = CHANGELOG.replace("## 1.2.3 (2026-10-20)", "## 1.2.3 (2026-10-20)  ")
    assert notes("v1.2.3", INIT, spaced) == "- **A new thing.** It works."


def test_a_version_without_a_changelog_section_is_refused():
    with pytest.raises(ReleaseError, match="no '## 1\\.2\\.3' section"):
        notes("v1.2.3", INIT, CHANGELOG.replace("## 1.2.3 (2026-10-20)", "## Unreleased too"))


def test_a_version_whose_section_is_empty_is_refused():
    empty = CHANGELOG.replace("- **A new thing.** It works.\n", "")
    with pytest.raises(ReleaseError, match="is empty"):
        notes("v1.2.3", INIT, empty)


def test_a_missing_version_is_refused():
    with pytest.raises(ReleaseError, match="no __version__"):
        notes("v1.2.3", '"""nothing."""\n', CHANGELOG)


def test_the_program_prints_the_notes_or_refuses(tmp_path, monkeypatch, capsys):
    (tmp_path / "init.py").write_text(INIT, encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text(CHANGELOG, encoding="utf-8")
    monkeypatch.setattr(release_notes, "VERSION_FILE", tmp_path / "init.py")
    monkeypatch.setattr(release_notes, "CHANGELOG", tmp_path / "CHANGELOG.md")
    assert release_notes.main(["v1.2.3"]) == 0
    assert capsys.readouterr().out.strip() == "- **A new thing.** It works."
    assert release_notes.main(["v1.2.4"]) == 1
    assert "does not match" in capsys.readouterr().err
    assert release_notes.main(["v1.2.3", "--extra"]) == 1  # an extra argument is not ignored
    assert release_notes.main(["--v1.2.3"]) == 1  # nor is an option in place of the tag

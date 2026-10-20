"""Command statistics for a draft profile: counts, surroundings and parameter guesses."""

import re

import pytest
from typer.testing import CliRunner

from yomineko.cli.app import app
from yomineko.core.rom.base import rom_from_bytes
from yomineko.profile.loader import load_profile
from yomineko.survey import render_report, run_survey
from yomineko.survey.commands import (
    CommandsError,
    CommandStat,
    measure_commands,
    suggest,
)

runner = CliRunner()
JAPANESE = re.compile("[぀-ヿ一-鿿]")


def by_code(report):
    return {s.code: s for s in report.stats}


def test_a_byte_stream_profiles_commands_are_counted_with_their_surroundings(table8_rom):
    report = measure_commands(table8_rom.rom, load_profile(table8_rom.profile_path))
    stats = by_code(report)
    assert report.kind == "table8" and report.profile_id == "synth-table8"
    assert stats[0x00].count == 5 and stats[0x00].declared == 0 and stats[0x00].line_break
    inside = stats[0x0B]  # a command in the middle of a sentence
    assert (inside.count, inside.before_text, inside.after_text) == (1, 1, 1)
    assert stats[0x0A].declared == -1 and stats[0x0A].after_command == 1
    unknown = stats[0x7E]  # not in the profile: the parameter probes are filled
    assert unknown.declared is None and unknown.probes[0] == 1
    assert [s.count for s in report.stats] == sorted((s.count for s in report.stats), reverse=True)


def test_glyph_id_command_tokens_are_counted_with_the_profiles_skip(lz16_rom):
    report = measure_commands(lz16_rom.rom, load_profile(lz16_rom.profile_path))
    stats = by_code(report)
    assert report.kind == "table16"
    assert stats[0x0E].declared == 1 and stats[0x0B].declared == 1
    assert stats[0x03].count == 4 and stats[0x03].before_text == 4
    assert all(0 <= s.isolated <= s.count for s in report.stats)


def test_a_profile_without_commands_is_refused(sjis_rom):
    with pytest.raises(CommandsError, match="only table8"):
        measure_commands(sjis_rom.rom, load_profile(sjis_rom.profile_path))


def stat(count=100, before=0, after=0, probes=(0, 0, 0, 0), declared=0, isolated=0):
    s = CommandStat(0x10, count=count, declared=declared)
    s.before_text, s.after_text, s.probes, s.isolated = before, after, list(probes), isolated
    return s


def test_a_command_in_the_middle_of_a_sentence_is_recognised():
    assert suggest(stat(before=90, after=90), "table8") == "inside a sentence"


def test_a_command_that_ends_a_line_is_recognised():
    assert suggest(stat(before=90, after=10), "table8") == "ends a line"


def test_a_command_that_starts_a_text_is_recognised():
    assert suggest(stat(before=10, after=90), "table8") == "starts a text"


def test_the_parameter_count_of_an_unknown_command_is_guessed_from_what_follows():
    guess = suggest(stat(declared=None, probes=(20, 100, 95, 30)), "table8")
    assert guess.startswith("probably 1 parameter bytes")


def test_glyph_id_arguments_show_as_lone_glyphs_after_the_command():
    assert suggest(stat(isolated=90), "table16").startswith("skip likely")
    assert suggest(stat(isolated=30), "table16").startswith("skip possible")
    assert suggest(stat(isolated=2), "table16") == ""


def test_a_rarely_seen_command_gets_no_guess():
    assert suggest(stat(count=5), "table8") == "too few to tell"


def test_the_report_has_a_commands_section_without_any_text(table8_rom):
    rom = rom_from_bytes(table8_rom.rom)
    text = render_report(run_survey(rom, command_profile=load_profile(table8_rom.profile_path)))
    assert "## 10. Commands of profile synth-table8 (table8)" in text
    assert "| 0x00 B |" in text and not JAPANESE.search(text)


def test_the_survey_command_measures_a_profiles_commands(
    tmp_path, monkeypatch, lz16_rom, write_rom
):
    monkeypatch.chdir(tmp_path)
    path = write_rom(lz16_rom.rom)
    result = runner.invoke(app, ["survey", str(path), "--commands", str(lz16_rom.profile_path)])
    assert result.exit_code == 0, result.output
    assert "## 10. Commands of profile synth-lz16 (table16)" in result.output
    assert not JAPANESE.search(result.output)

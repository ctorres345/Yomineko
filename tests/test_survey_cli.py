"""The survey report and the ``yomineko survey`` command."""

import re
import zipfile

import pytest
from support.synthrom import SynthRom
from support.synthsurvey import (
    RELATIVE_WORD,
    build_state,
    build_survey_rom,
    wrap_png_state,
    wrap_rzip,
)
from typer.testing import CliRunner

from yomineko.cli.app import app
from yomineko.core.rom.base import rom_from_bytes
from yomineko.survey import render_report, run_survey

runner = CliRunner()
JAPANESE = re.compile("[぀-ヿ一-鿿]")


def run(*args):
    return runner.invoke(app, [str(a) for a in args])


@pytest.fixture(scope="module")
def rom():
    return rom_from_bytes(build_survey_rom()[0])


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def rom_file(rom, tmp_path):
    path = tmp_path / "game.gba"
    path.write_bytes(rom.data)
    return path


def test_report_has_every_section_and_no_japanese(rom):
    steps: list[str] = []
    found = run_survey(
        rom,
        word=RELATIVE_WORD,
        state_file=wrap_png_state(build_state().state),
        sheets=True,
        progress=steps.append,
    )
    text = render_report(found)
    for heading in (
        "## Leads",
        "## 1. Extent and fill",
        "## 2. BIOS compression",
        "## 3. Plain text",
        "## 4. Pointers and offsets",
        "## 5. Font candidates",
        "## 6. Token streams",
        "## 7. Relative search",
        "## 8. Save state",
    ):
        assert heading in text
    assert JAPANESE.search(text) is None
    assert RELATIVE_WORD not in text
    assert len(steps) == 8
    assert "font-00A000.png" in text
    assert "is rendered at run time" in text  # the state's tiles are not in this ROM


def test_leads_name_what_was_found(rom):
    text = render_report(run_survey(rom))
    assert "LZ77 streams of 8000 bytes or more" in text
    assert "decoded LZ77 blocks" in text
    assert "glyph ids" in text
    assert "font-candidate" in text
    assert "## 7" not in text and "## 8" not in text


def test_leads_for_plain_text():
    rom = SynthRom("PLAIN", "PLNT", size=0x4000)
    rom.put(0x100, b"".join("ねこがおちゃをのむ".encode("shift_jis") + b"\0" for _ in range(12)))
    text = render_report(run_survey(rom_from_bytes(rom.finish()[0])))
    assert "Shift-JIS profile" in text


def test_leads_when_nothing_matches():
    rom = SynthRom("EMPTY", "EMPT", size=0x4000)
    text = render_report(run_survey(rom_from_bytes(rom.finish()[0])))
    assert "Nothing matched" in text
    assert "No fill runs" not in text  # the zero-filled image has them
    assert "No stretch of 8 KB" in text
    assert "No 8 KB window" in text


def test_a_state_with_no_text_rectangle_is_reported():
    rom = rom_from_bytes(build_survey_rom()[0])
    text = render_report(run_survey(rom, state_file=build_state(text=False).state))
    assert "No rectangle of consecutive tile numbers" in text


def test_command_prints_the_report(rom_file):
    result = run("survey", rom_file)
    assert result.exit_code == 0, result.output
    assert "## 3. Plain text" in result.output
    assert JAPANESE.search(result.output) is None
    assert "checking token streams" in result.output  # progress goes to stderr


def test_command_reads_a_zip(rom, tmp_path):
    path = tmp_path / "game.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("game.gba", rom.data)
    result = run("survey", path)
    assert result.exit_code == 0, result.output


def test_command_with_a_word_and_a_state(rom_file, tmp_path):
    state_file = tmp_path / "game.state"
    state_file.write_bytes(wrap_rzip(build_state().state))
    result = run("survey", rom_file, "--word", RELATIVE_WORD, "--state", state_file)
    assert result.exit_code == 0, result.output
    assert "## 7. Relative search" in result.output
    assert "## 8. Save state" in result.output
    assert RELATIVE_WORD not in result.output


def test_command_refuses_a_bad_word(rom_file):
    result = run("survey", rom_file, "--word", "猫")
    assert result.exit_code == 1
    assert "kana" in result.output


def test_command_refuses_a_bad_state(rom_file, tmp_path):
    state_file = tmp_path / "bad.state"
    state_file.write_bytes(b"not a state at all")
    result = run("survey", rom_file, "--state", state_file)
    assert result.exit_code == 1
    assert "I/O" in result.output


def test_report_option_writes_the_report_and_sheets(workdir, rom_file):
    result = run("survey", rom_file, "--report")
    assert result.exit_code == 0, result.output
    folder = workdir / "yomineko-out" / "srvy"
    report = (folder / "survey.md").read_text(encoding="utf-8")
    assert report.startswith("# Survey: SYNTH SURVEY (SRVY)")
    assert (folder / "font-00A000.png").read_bytes().startswith(b"\x89PNG")
    assert "survey.md and 1 sheets" in result.output


def test_report_goes_under_the_profile_id_when_one_matches(workdir, sjis_rom, write_rom):
    from yomineko.profile.loader import load_profile

    profile = load_profile(sjis_rom.profile_path)
    path = write_rom(sjis_rom.rom)
    result = run("survey", path, "--report")
    assert result.exit_code == 0, result.output
    # the synthetic profile is not packaged, so the folder is named after the game code
    assert (workdir / "yomineko-out" / profile.profile.rom.game_code.lower() / "survey.md").exists()


def test_survey_is_listed_in_the_help():
    assert "survey" in run("--help").output

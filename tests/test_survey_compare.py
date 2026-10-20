"""Comparing two versions of a ROM: constant-shift runs and the ranges present in one only."""

from itertools import islice

from support.synthrom import SynthRom, lcg_bytes
from typer.testing import CliRunner

from yomineko.cli.app import app
from yomineko.core.rom.base import rom_from_bytes
from yomineko.survey import render_report, run_survey
from yomineko.survey.compare import compare_roms

runner = CliRunner()


def noise(seed: int, size: int) -> bytes:
    return bytes(islice(lcg_bytes(seed), size))


A = noise(1, 20000) + noise(2, 20000)  # 40,000 bytes
INSERTED = noise(3, 8192)
B = A[:20000] + INSERTED + A[20000:] + noise(4, 6000)  # the other version has more of everything


def test_identical_images_are_one_run_with_no_shift():
    c = compare_roms(A, A)
    assert [(r.start, r.shift) for r in c.runs] == [(0, 0)]
    assert c.runs[0].end == len(A) and c.matched == len(A)
    assert c.only_a == [] and c.only_b == []


def test_an_inserted_block_shifts_everything_after_it():
    c = compare_roms(A, B)
    first, second = c.runs
    assert (first.start, first.shift) == (0, 0) and 19000 <= first.end <= 20000
    assert second.shift == len(INSERTED) and second.end == len(A)
    assert c.matched >= len(A) - 64


def test_data_that_exists_only_in_the_other_image_is_reported_as_such():
    c = compare_roms(A, B)
    inserted = [r for r in c.only_b if r[0] <= 20000 + 32 and r[1] >= 20000 + len(INSERTED) - 32]
    assert inserted, c.only_b
    assert any(end == len(B) for _, end in c.only_b)  # the extra tail
    assert c.only_a == []


def test_fill_does_not_match_fill_somewhere_else():
    a = noise(5, 8000) + bytes(8000) + noise(6, 8000)
    b = noise(6, 8000) + bytes(8000) + noise(5, 8000)
    c = compare_roms(a, b)
    assert all(not (8000 <= r.start < 16000) for r in c.runs)  # nothing inside the zero fill
    assert {r.shift for r in c.runs} == {16000, -16000}


def test_a_short_coincidence_is_not_a_run():
    a = noise(7, 8000)
    b = noise(8, 4000) + a[1000:1100] + noise(9, 4000)  # 100 shared bytes: under the minimum
    assert compare_roms(a, b).runs == []


def test_the_survey_report_has_a_comparison_section():
    rom = rom_from_bytes(SynthRom("ONE", "ABCJ", size=0x8000).finish()[0])
    other = rom_from_bytes(SynthRom("TWO", "ABCE", size=0x8000).finish()[0])
    text = render_report(run_survey(rom, other=other))
    assert "## 9. Comparison with another version" in text
    assert "Shifts (offset in the other image minus offset here)" in text


def test_the_survey_command_compares_two_files(tmp_path, monkeypatch, write_rom):
    monkeypatch.chdir(tmp_path)
    first = write_rom(SynthRom("ONE", "ABCJ", size=0x8000).finish()[0], "one.gba")
    second = write_rom(SynthRom("TWO", "ABCE", size=0x8000).finish()[0], "two.gba")
    result = runner.invoke(app, ["survey", str(first), "--compare", str(second)])
    assert result.exit_code == 0, result.output
    assert "## 9. Comparison with another version" in result.output
    assert "Counts and offsets only" in result.output

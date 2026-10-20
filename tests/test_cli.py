import csv
import hashlib
import json
import re
import subprocess
import sys

import pytest
import yaml
from support.synthrom import SynthRom
from typer.testing import CliRunner

from yomineko import __version__
from yomineko.cli.app import app
from yomineko.core.roundtrip import VerifyResult
from yomineko.model import Script
from yomineko.profile.loader import load_profile
from yomineko.profile.schema import Profile

runner = CliRunner()


ANSI = re.compile(chr(27) + r"\[[0-9;]*m")  # colour codes


def run(*args):
    return runner.invoke(app, [str(a) for a in args])


def plain(result):
    """Output without colour codes: CI terminals get rich colouring that splits words."""
    return ANSI.sub("", result.output)


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """Run in an empty folder so default outputs (yomineko-out/) land there."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def rom_file(sjis_rom, write_rom):
    return write_rom(sjis_rom.rom)


@pytest.fixture
def script_file(workdir, rom_file, sjis_rom):
    result = run("extract", rom_file, "--profile", sjis_rom.profile_path)
    assert result.exit_code == 0, result.output
    return workdir / "yomineko-out" / "synth-sjis" / "script.json"


def assert_clean_failure(result, *fragments):
    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert result.output.startswith(("error:", "FAIL", "MISMATCH")) or "error:" in result.output
    for f in fragments:
        assert f in result.output


# ------------------------------------------------------------------ top level


def test_version():
    result = run("--version")
    assert result.exit_code == 0
    assert result.output.strip() == f"yomineko {__version__}"


def test_no_arguments_shows_help():
    result = run()
    assert "Usage" in plain(result) and "extract" in plain(result)


@pytest.mark.parametrize(
    "command",
    [
        ("extract",),
        ("verify",),
        ("analyze",),
        ("export",),
        ("survey",),
        ("serve",),
        ("profile", "new"),
        ("review", "worklist"),
    ],
)
def test_help_has_no_japanese(command):
    # A cp1252 Windows console cannot print Japanese, and `--help` must never crash there.
    out = plain(run(*command, "--help"))
    assert "Usage" in out
    assert not [c for c in out if "　" <= c <= "鿿"]


def test_module_entry_point_runs():
    out = subprocess.run(
        [sys.executable, "-m", "yomineko", "--version"], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == f"yomineko {__version__}"


# ----------------------------------------------------------------------- info


def test_info_with_a_profile(rom_file, sjis_rom):
    result = run("info", rom_file, "--profile", sjis_rom.profile_path)
    assert result.exit_code == 0
    for text in ("SYNTH TEST", "TSTJ", sjis_rom.sha1, "synth-sjis", "gba"):
        assert text in result.output


@pytest.fixture
def usa_rom_file(write_rom):
    return write_rom(SynthRom("USA GAME", "USAE", size=0x4000).finish()[0])


def test_info_for_a_rom_that_is_not_japanese_says_so(usa_rom_file):
    result = run("info", usa_rom_file)
    assert result.exit_code == 0
    assert "USAE" in result.output and "reads Japanese games" in result.output


def test_info_for_an_unsupported_rom_says_so(rom_file):
    result = run("info", rom_file)
    assert result.exit_code == 0
    assert "none (this ROM is not supported yet)" in result.output


# -------------------------------------------------------------------- extract


def test_extract_writes_the_default_path_and_a_valid_script(workdir, rom_file, sjis_rom):
    result = run("extract", rom_file, "--profile", sjis_rom.profile_path)
    assert result.exit_code == 0, result.output
    assert "Extracted 11 strings in 4 banks" in result.output
    dest = workdir / "yomineko-out" / "synth-sjis" / "script.json"
    assert f"Wrote {dest.relative_to(workdir)}" in result.output
    script = Script.model_validate_json(dest.read_text(encoding="utf-8"))
    assert len(script.lines) == 11 and script.game.rom_sha1 == sjis_rom.sha1


def test_extract_to_a_chosen_file(workdir, rom_file, sjis_rom):
    result = run("extract", rom_file, "-p", sjis_rom.profile_path, "-o", workdir / "my" / "s.json")
    assert result.exit_code == 0
    assert (workdir / "my" / "s.json").is_file()


def test_extract_without_a_matching_profile(workdir, rom_file, sjis_rom):
    result = run("extract", rom_file)
    assert_clean_failure(result, "no profile for this ROM", sjis_rom.sha1, "pmd-red-jp")
    assert not (workdir / "yomineko-out").exists()


def test_extract_refuses_a_rom_that_is_not_japanese(workdir, usa_rom_file, sjis_rom):
    for args in ((), ("--profile", sjis_rom.profile_path)):
        result = run("extract", usa_rom_file, *args)
        assert_clean_failure(result, "reads Japanese games", "USAE")
    assert not (workdir / "yomineko-out").exists()


def test_verify_refuses_a_rom_that_is_not_japanese(usa_rom_file):
    assert_clean_failure(run("verify", usa_rom_file), "reads Japanese games", "USAE")


def test_extract_with_a_profile_for_another_rom(rom_file, tbl_rom):
    result = run("extract", rom_file, "--profile", tbl_rom.profile_path)
    assert_clean_failure(result, "is for ROM")


def test_extract_with_an_unknown_profile_id(rom_file):
    assert_clean_failure(run("extract", rom_file, "--profile", "nope"), "no profile named")


def test_extract_a_file_that_is_not_a_rom(workdir):
    junk = workdir / "junk.gba"
    junk.write_bytes(b"x" * 5000)
    assert_clean_failure(run("extract", junk), "not a GBA or Game Boy ROM")


def test_extract_a_missing_file(workdir):
    assert_clean_failure(run("extract", workdir / "missing.gba"), "no such file")


def spelled_out_rom(tbl_rom, tmp_path):
    """The table ROM with one string spelled so it will not rebuild identically, plus a
    profile whose checksum matches the modified ROM."""
    codec = load_profile(tbl_rom.profile_path).codec()
    rom = bytearray(tbl_rom.rom)
    spelled = codec.encode("ね") + codec.encode("こ") + codec.encode("が") + b"\xff"
    rom[0x500 : 0x500 + len(spelled)] = spelled
    rom[0x2010:0x2014] = (0x08000500).to_bytes(4, "little")
    header_sum = (-(sum(rom[0xA0:0xBD]) + 0x19)) & 0xFF
    assert rom[0xBD] == header_sum  # the header was untouched
    data = yaml.safe_load(tbl_rom.profile_path.read_text(encoding="utf-8"))
    data["rom"]["sha1"] = hashlib.sha1(rom).hexdigest()
    data["encoding"]["table"] = str(tbl_rom.profile_path.parent.parent / "fake.tbl")
    profile = tmp_path / "tbl-modified.yaml"
    profile.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return bytes(rom), profile


def test_strings_that_do_not_rebuild_identically_are_reported_not_hidden(
    workdir, tbl_rom, write_rom
):
    rom, profile = spelled_out_rom(tbl_rom, workdir)
    path = write_rom(rom, "tbl.gba")
    extracted = run("extract", path, "--profile", profile)
    assert extracted.exit_code == 0
    assert "1 strings were left out" in extracted.output
    verified = run("verify", path, "--profile", profile)
    assert verified.exit_code == 0 and "OK:" in verified.output
    assert "1 strings were left out and are untouched" in verified.output


# --------------------------------------------------------------------- verify


def test_verify_ok(rom_file, sjis_rom):
    result = run("verify", rom_file, "--profile", sjis_rom.profile_path)
    assert result.exit_code == 0
    assert f"OK: the rebuilt ROM matches the original (sha1 {sjis_rom.sha1})" in result.output


def test_verify_reports_a_mismatch_and_exits_1(rom_file, sjis_rom, monkeypatch):
    bad = VerifyResult(ok=False, sha1="a" * 40, expected_sha1="b" * 40, mismatches=[1, 2])
    monkeypatch.setattr("yomineko.cli.app.verify_rom", lambda *args, **kwargs: bad)
    result = run("verify", rom_file, "--profile", sjis_rom.profile_path)
    assert result.exit_code == 1
    assert "MISMATCH" in result.output and "2 lines re-encode differently" in result.output


# --------------------------------------------------------------------- export


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def test_export_csv_next_to_the_script(script_file):
    result = run("export", script_file, "--format", "csv")
    assert result.exit_code == 0, result.output
    out = script_file.with_name("script.export.csv")
    assert "Exported 11 lines" in result.output
    assert out.read_bytes().startswith(b"\xef\xbb\xbf")
    rows = read_csv(out)
    assert len(rows) == 11 and rows[0]["address"] == "0x100"


def test_export_json_with_a_kind_filter(script_file):
    out = script_file.parent / "terms.json"
    result = run("export", script_file, "-f", "json", "--kind", "term", "-o", out)
    assert result.exit_code == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert {x["kind"] for x in data["lines"]} == {"term"}
    assert Script.model_validate(data).game.profile_id == "synth-sjis"


def test_export_all_flag_is_accepted(script_file):
    assert run("export", script_file, "-f", "csv", "--all").exit_code == 0


def test_export_will_not_overwrite_its_own_input(script_file):
    result = run("export", script_file, "-f", "json", "-o", script_file)
    assert_clean_failure(result, "would overwrite")
    assert json.loads(script_file.read_text(encoding="utf-8"))["schema_version"] == 4


def test_export_requires_a_format(script_file):
    result = run("export", script_file)
    assert result.exit_code == 2 and "--format" in plain(result)


def test_export_rejects_an_unknown_format(script_file):
    assert run("export", script_file, "-f", "ods").exit_code == 2


def test_export_of_a_missing_or_damaged_script(workdir):
    assert_clean_failure(run("export", workdir / "none.json", "-f", "csv"), "cannot read")
    bad = workdir / "bad.json"
    bad.write_text("{", encoding="utf-8")
    assert_clean_failure(run("export", bad, "-f", "csv"), "not a valid script file")


def test_export_of_a_script_from_another_version(workdir):
    old = workdir / "old.json"
    old.write_text('{"schema_version": 9}', encoding="utf-8")
    assert_clean_failure(run("export", old, "-f", "csv"), "version is 9")


# -------------------------------------------------------------------- profile


def test_profile_list_shows_the_packaged_profile():
    result = run("profile", "list")
    assert result.exit_code == 0
    assert "pmd-red-jp" in result.output and "B24J" in result.output


def test_profile_validate_packaged():
    result = run("profile", "validate")
    assert result.exit_code == 0 and "ok   pmd-red-jp" in result.output


def test_profile_validate_files(sjis_rom, tbl_rom, workdir):
    ok = run("profile", "validate", sjis_rom.profile_path, tbl_rom.profile_path)
    assert ok.exit_code == 0 and ok.output.count("ok   ") == 2

    bad = workdir / "bad.yaml"
    bad.write_text("id: Bad Id\n", encoding="utf-8")
    result = run("profile", "validate", sjis_rom.profile_path, bad)
    assert result.exit_code == 1
    assert "ok   " in result.output and "FAIL" in result.output and "bad.yaml" in result.output


def test_profile_validate_catches_a_missing_table_file(tbl_rom, workdir):
    data = yaml.safe_load(tbl_rom.profile_path.read_text(encoding="utf-8"))
    data["encoding"]["table"] = "missing.tbl"
    path = workdir / "p.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    result = run("profile", "validate", path)
    assert result.exit_code == 1 and "cannot read table" in result.output


def test_profile_new_writes_a_valid_skeleton(workdir):
    result = run("profile", "new", "my-game")
    assert result.exit_code == 0, result.output
    path = workdir / "my-game.yaml"
    profile = Profile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    assert profile.id == "my-game"
    assert "TODO" in path.read_text(encoding="utf-8")
    assert run("profile", "validate", path).exit_code == 0


def test_profile_new_will_not_overwrite_without_force(workdir):
    run("profile", "new", "g")
    result = run("profile", "new", "g")
    assert_clean_failure(result, "already exists")
    assert run("profile", "new", "g", "--force").exit_code == 0


def test_profile_new_checks_the_id_and_honours_output(workdir):
    assert_clean_failure(run("profile", "new", "Bad Id"), "not a valid id")
    out = workdir / "sub" / "x.yaml"
    assert run("profile", "new", "x", "-o", out).exit_code == 0 and out.is_file()

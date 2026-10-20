"""The skeleton `yomineko profile new` writes. It is a valid profile (so `profile validate`
passes) with placeholder values to replace."""

from __future__ import annotations

SKELETON = """\
# Profile for {id}. Offsets, encoding and control codes only: never put game text here.
# Fill in every value marked TODO, then check it:
#   yomineko profile validate {id}.yaml
#   yomineko verify game.gba --profile {id}.yaml      (the rebuild must match the checksum)
schema_version: 1
id: {id}
title: TODO Game title (region)
platform: gba            # or gbc (Game Boy Color)
rom:
  sha1: "0000000000000000000000000000000000000000"   # TODO sha1 of the ROM dump
  game_code: XXXJ                                      # TODO from `yomineko info`; ends in J
  revision: 0
encoding:
  type: shift_jis        # or: table (then set `table:` to a .tbl file next to this profile)
  terminator: 0x00
  single_byte_kana: native   # "hiragana" if the single-byte kana range is drawn as hiragana
  custom_leads: []           # lead-byte ranges used for custom glyphs, e.g. [[0x84, 0x87]]
text:
  regions:
    - {{start: 0x0, end: 0x100000}}   # TODO the part of the ROM that holds text
  pointer_base: 0x08000000
  pointer_align: 4
  bank_gap: 0x40
discover:
  min_score: 0.7
  unreferenced: {{min_japanese: 3, min_kana_ratio: 0.8}}
  ignore: []   # regexes for control codes to ignore when scoring, e.g. '#C.'
plain: []      # ordered rewrites to readable text: - {{pattern: '#P', replace: "\\n"}}
kinds: {{dialogue_min_length: 12}}
tables: []     # pointer tables: - {{category: item, base: 0x0, stride: 4, count: 10}}
# Optional, for sentence selection (addresses and counts only):
# sentences:
#   exclude_ranges: [{{start: 0x0, end: 0x1000}}]   # file offsets of tables that read as rule text
#   caps: {{name_quote: 100, name_subject: 150}}    # at most this many of each structural kind
"""


def render_skeleton(profile_id: str) -> str:
    return SKELETON.format(id=profile_id)

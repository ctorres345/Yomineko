"""Render a survey as Markdown. Counts and offsets only: no byte of the ROM's text appears."""

from __future__ import annotations

from collections import Counter

from yomineko.survey.bios import LARGE_STREAM
from yomineko.survey.commands import suggest
from yomineko.survey.run import Survey

LISTED = 12  # rows shown in a list before "and N more"


def _hex(n: int) -> str:
    return f"0x{n:X}"


def _more(shown: int, total: int) -> list[str]:
    return [f"- ... and {total - shown} more"] if total > shown else []


def hints(s: Survey) -> list[str]:
    """Plain-language leads, each backed by a number in the sections below."""
    out = []
    if s.plain.hiragana_runs >= 10:
        out.append(
            f"{s.plain.hiragana_runs} runs of plain Shift-JIS hiragana: try a Shift-JIS profile."
        )
    large = [x for x in s.lz77 if x.size >= LARGE_STREAM]
    if large:
        out.append(
            f"{len(large)} LZ77 streams of {LARGE_STREAM} bytes or more: the script may be "
            "compressed (see the token-stream check)."
        )
    in_blocks = [t for t in s.tokens if t.source != "rom"]
    if in_blocks:
        out.append(
            f"Token-stream windows inside {len({t.source for t in in_blocks})} decoded LZ77 "
            "blocks: text stored as glyph ids behind compression."
        )
    if any(t.source == "rom" for t in s.tokens):
        out.append("Token-stream windows in the raw image: text stored as glyph ids.")
    if s.fonts:
        out.append(f"{len(s.fonts)} font-candidate ranges (few byte values, many zeros).")
    if not out:
        out.append(
            "Nothing matched the known layouts: the text may be compressed in a custom way, "
            "or built at run time. A save state (--state) shows how it is drawn."
        )
    return out


def render_report(s: Survey) -> str:
    lines = [
        f"# Survey: {s.title or '(no title)'} ({s.game_code})",
        "",
        f"SHA-1 `{s.sha1}`, {s.extent.size:,} bytes. Counts and offsets only.",
        "",
        "## Leads",
        "",
        *[f"- {h}" for h in hints(s)],
        "",
    ]
    lines += _extent(s)
    lines += _bios(s)
    lines += _plain(s)
    lines += _tables(s)
    lines += _fonts(s)
    lines += _tokens(s)
    if s.relative:
        lines += _relative(s)
    if s.state:
        lines += _state(s)
    if s.comparison:
        lines += _comparison(s)
    if s.commands:
        lines += _commands(s)
    return "\n".join(lines).rstrip() + "\n"


def _extent(s: Survey) -> list[str]:
    e = s.extent
    block = "512 KB"
    out = [
        "## 1. Extent and fill",
        "",
        f"Entropy in bits per byte for each {block} (8.0 is random or well compressed, "
        "low is code or sparse data):",
        "",
        "```",
        *[
            " ".join(f"{i * 0x80000:06X}:{v:.1f}" for i, v in enumerate(e.entropy[k : k + 8], k))
            for k in range(0, len(e.entropy), 8)
        ],
        "```",
        "",
    ]
    if e.fills:
        out.append(f"Fill runs of 4 KB or more ({len(e.fills)}):")
        out.append("")
        for f in e.fills[:LISTED]:
            size_kb = (f.end - f.start) >> 10
            out.append(f"- {_hex(f.start)}-{_hex(f.end)} ({size_kb} KB) of 0x{f.value:02X}")
        out += _more(LISTED, len(e.fills))
    else:
        out.append("No fill runs of 4 KB or more.")
    if e.tail_fill_start is not None:
        out.append("")
        out.append(f"The image ends in fill from {_hex(e.tail_fill_start)}.")
    return [*out, ""]


def _bios(s: Survey) -> list[str]:
    large = sorted((x for x in s.lz77 if x.size >= LARGE_STREAM), key=lambda x: x.offset)
    out = [
        "## 2. BIOS compression",
        "",
        f"LZ77 streams that decode cleanly: {len(s.lz77)} "
        f"({len(large)} of {LARGE_STREAM} bytes or more).",
    ]
    sizes = Counter(x.size for x in s.lz77).most_common(5)
    if sizes:
        out.append("")
        out.append("Most common decoded sizes: " + ", ".join(f"{k} (x{v})" for k, v in sizes) + ".")
    if large:
        out += ["", "Large streams (offset, decoded, packed):", ""]
        for x in large[:LISTED]:
            out.append(f"- {_hex(x.offset)}: {x.size} bytes, packed {x.packed}")
        out += _more(LISTED, len(large))
    out.append("")
    out.append(
        "Huffman and run-length at pointer targets (a header byte alone is noise; "
        "only streams that decode to their declared size count):"
    )
    out.append("")
    for o in s.other_streams:
        examples = ", ".join(f"{_hex(a)} ({n})" for a, n in o.examples[:4])
        out.append(
            f"- {o.kind}: {o.headers} plausible headers, {o.decoded} decode"
            + (f"; e.g. {examples}" if examples else "")
        )
    return [*out, ""]


def _plain(s: Survey) -> list[str]:
    p = s.plain
    out = [
        "## 3. Plain text",
        "",
        f"Shift-JIS hiragana runs of 4 or more characters: {p.hiragana_runs}; "
        f"katakana runs: {p.katakana_runs}; hiragana runs touching ASCII: {p.ascii_neighbours}.",
    ]
    if p.examples:
        out.append("")
        first = ", ".join(f"{_hex(a)} ({n})" for a, n in p.examples)
        out.append(f"First runs (offset, bytes): {first}")
    return [*out, ""]


def _tables(s: Survey) -> list[str]:
    out = ["## 4. Pointers and offsets", ""]
    out.append(f"Pointer runs of 32 or more words: {len(s.pointer_runs)}.")
    if s.pointer_runs:
        out += ["", "Offset, count, ascending, and what the first targets are:", ""]
        for r in s.pointer_runs[:LISTED]:
            kinds = ", ".join(f"{k} x{v}" for k, v in sorted(r.labels.items()))
            out.append(
                f"- {_hex(r.offset)}: {r.count} pointers, "
                f"{'ascending' if r.ascending else 'unordered'}; {kinds}"
            )
        out += _more(LISTED, len(s.pointer_runs))
    out += ["", f"Increasing offset runs of 120 or more: {len(s.offset_runs)}."]
    if s.offset_runs:
        out += ["", "Offset, entry size, count, first, last, opens its own block:", ""]
        for o in s.offset_runs[:LISTED]:
            out.append(
                f"- {_hex(o.offset)}: {o.width}-byte x{o.count}, {o.first:#x}-{o.last:#x}, "
                f"{'yes' if o.opens_block else 'no'}"
            )
        out += _more(LISTED, len(s.offset_runs))
    out += [
        "",
        "Most such tables are animation or object records, not text: look at the target labels.",
    ]
    return [*out, ""]


def _fonts(s: Survey) -> list[str]:
    out = ["## 5. Font candidates", ""]
    if not s.fonts:
        return [*out, "No stretch of 8 KB or more with 8 or fewer byte values.", ""]
    out.append(f"Stretches of 8 KB or more with 8 or fewer byte values: {len(s.fonts)}.")
    out += ["", "Range, byte values, glyph cell size (bytes), blank share, row stride hint:", ""]
    for c in s.fonts[:LISTED]:
        g = s.geometry.get(c.start)
        shape = f"{g.unit}, {g.blank_share:.2f}, {g.row_stride}" if g else "too short to measure"
        values = " ".join(f"{v:02X}" for v in c.values)
        out.append(f"- {_hex(c.start)}-{_hex(c.end)}: {values}; {shape}")
    out += _more(LISTED, len(s.fonts))
    if s.sheets:
        out += ["", "Sheets written: " + ", ".join(sorted(s.sheets)) + "."]
    return [*out, ""]


def _tokens(s: Survey) -> list[str]:
    out = ["## 6. Token streams", ""]
    if not s.tokens:
        return [*out, "No 8 KB window has the profile of 16-bit glyph ids.", ""]
    by_source = Counter(t.source for t in s.tokens)
    out.append(f"Ranges with a token-stream profile: {len(s.tokens)} in {len(by_source)} sources.")
    out.append("")
    for t in s.tokens[:LISTED]:
        out.append(f"- {t.source}: {_hex(t.start)}-{_hex(t.end)}")
    out += _more(LISTED, len(s.tokens))
    return [*out, ""]


def _relative(s: Survey) -> list[str]:
    r = s.relative
    assert r is not None
    out = [
        "## 7. Relative search",
        "",
        f"A word of {r.kana} kana (not shown). Random bytes would give about {r.expected8} "
        f"1-byte and {r.expected16} 2-byte hits.",
        "",
        f"- 1-byte table: {r.hits8} hits; per 64 KB: "
        + (", ".join(f"{_hex(a)}:{n}" for a, n in r.blocks8) or "none"),
        f"- 2-byte table: {r.hits16} hits; per 64 KB: "
        + (", ".join(f"{_hex(a)}:{n}" for a, n in r.blocks16) or "none"),
    ]
    return [*out, ""]


def _state(s: Survey) -> list[str]:
    st = s.state
    assert st is not None
    out = [
        "## 8. Save state",
        "",
        f"I/O block at {_hex(st.io_offset)}; DISPCNT {st.dispcnt:#06x} (mode {st.mode}).",
        "",
    ]
    for layer in st.layers:
        depth = 8 if layer.colors8 else 4
        out.append(
            f"- BG{layer.index}: priority {layer.priority}, char base {_hex(layer.char_base)}, "
            f"screen base {_hex(layer.screen_base)}, {depth} bits per pixel, "
            f"size code {layer.size}"
        )
    t = st.text
    out.append("")
    if t is None:
        out.append("No rectangle of consecutive tile numbers found in the tile maps.")
        return [*out, ""]
    out += [
        f"Text tiles on BG{t.layer}: a {t.width}x{t.height} rectangle at column {t.column}, "
        f"row {t.row}, tile numbers from {t.first_tile}; {t.tiles} distinct inked tiles.",
        "",
        f"- exact in the ROM: {t.in_rom_exact}; same ink shape in the ROM: {t.in_rom_shape}",
        f"- exact in EWRAM: {t.in_ewram}; in IWRAM: {t.in_iwram}",
        "- EWRAM mirror of the whole rectangle: "
        + (f"0x{t.ewram_mirror:08X}" if t.ewram_mirror is not None else "none"),
    ]
    if t.in_rom_exact == 0 and t.in_rom_shape == 0 and (t.in_ewram or t.ewram_mirror):
        out += [
            "",
            "The tiles are not in the ROM but are in RAM: the text is rendered at run time "
            "from a font that is not stored as plain tiles.",
        ]
    return [*out, ""]


def _comparison(s: Survey) -> list[str]:
    c = s.comparison
    assert c is not None
    shares: Counter[int] = Counter()
    for run in c.runs:
        shares[run.shift] += run.end - run.start
    out = [
        "## 9. Comparison with another version",
        "",
        f"This image is {c.size_a:,} bytes, the other {c.size_b:,}. {c.matched:,} bytes of this "
        f"image ({c.matched * 100 // max(c.size_a, 1)}%) match the other one in "
        f"{len(c.runs)} runs.",
        "",
        "Shifts (offset in the other image minus offset here) that cover the most bytes:",
        "",
    ]
    for shift, size in shares.most_common(LISTED):
        first = next(r for r in c.runs if r.shift == shift)
        last = [r for r in c.runs if r.shift == shift][-1]
        sign = "-" if shift < 0 else "+"
        out.append(
            f"- {sign}0x{abs(shift):X}: {size:,} bytes, "
            f"from {_hex(first.start)} to {_hex(last.end)}"
        )
    out += _more(LISTED, len(shares))
    for label, ranges in (("this image only", c.only_a), ("the other image only", c.only_b)):
        largest = sorted(sorted(ranges, key=lambda r: r[0] - r[1])[:LISTED])
        out += [
            "",
            f"Ranges of 4 KB or more in {label} ({len(ranges)}; the largest, by offset):",
            "",
        ]
        for start, end in largest:
            out.append(f"- {_hex(start)}-{_hex(end)} ({(end - start) >> 10} KB)")
        out += _more(LISTED, len(ranges))
    out.append("")
    out.append(
        "The script is often in a range that exists in one version only, or in the first range "
        "where the shift changes."
    )
    return [*out, ""]


def _commands(s: Survey) -> list[str]:
    c = s.commands
    assert c is not None
    out = [
        f"## 10. Commands of profile {c.profile_id} ({c.kind})",
        "",
    ]
    if c.kind == "table8":
        out += [
            "Per command: how often, the parameter count the profile gives, the share that follows "
            "text and the share followed by text (after its parameters), and a guess. `B` marks "
            "the profile's line breaks.",
            "",
            "| code | seen | params | after text | before text | guess |",
            "|---|---|---|---|---|---|",
        ]
    else:
        out += [
            "Per command token (a token the table does not know): how often, the argument count "
            "the profile gives (`skip`), the share that follows text, the share followed by one "
            "lone glyph and then a command (a parameter that reads as text) and a guess.",
            "",
            "| token | seen | skip | after text | lone glyph after | guess |",
            "|---|---|---|---|---|---|",
        ]
    shown = c.stats[: 3 * LISTED]
    for st in shown:
        declared = "?" if st.declared is None else str(st.declared)
        mark = " B" if st.line_break else ""
        if c.kind == "table8":
            cells = (
                f"0x{st.code:02X}{mark}",
                str(st.count),
                declared,
                f"{st.share_before:.0%}",
                f"{st.share_after:.0%}",
                suggest(st, c.kind),
            )
        else:
            cells = (
                f"0x{st.code:04X}",
                str(st.count),
                declared,
                f"{st.share_before:.0%}",
                f"{st.share_isolated:.0%}",
                suggest(st, c.kind),
            )
        out.append("| " + " | ".join(cells) + " |")
    out += _more(len(shown), len(c.stats))
    return [*out, ""]

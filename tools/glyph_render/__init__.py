"""Read a game's character table by rendering every code in an emulator.

For a game whose font is not stored as plain tiles (the text is drawn at run time), put a message on
screen in a save state, then replace the message bytes in the ROM with each code in turn, let the
emulator draw it and crop the glyph. The result is a sheet of pictures to read, not text.

    python -m glyph_render render --core mgba_libretro.dll --rom game.gba --state game.state
        --pointer 0x3C2E65 --template "FF03FF3520{code}FF0C30" --window 192,240,145,158
        --out yomineko-out/glyphs.json
    python -m glyph_render sheets yomineko-out/glyphs.json --out yomineko-out/sheets
    python -m glyph_render table transcription.tsv --out my-game.tbl

See ``.claude/skills/read-glyph-table/SKILL.md`` for the whole method.
"""

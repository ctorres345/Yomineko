"""A minimal libretro host for an mGBA core (``mgba_libretro.dll`` or ``.so``), over ctypes.

Only what the glyph tools need: load a ROM (a writable copy, so the caller can patch bytes before
the game starts), load a save state, run frames, read the last video frame. No sound, and input
only for optional button presses.
"""

from __future__ import annotations

import ctypes as C
import zipfile
from pathlib import Path
from typing import Any

_ENV = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
_VIDEO = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
_AUDIO = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
_AUDIO_BATCH = C.CFUNCTYPE(C.c_size_t, C.c_void_p, C.c_size_t)
_POLL = C.CFUNCTYPE(None)
_INPUT = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)

BUTTONS = {
    "B": 0,
    "Y": 1,
    "SELECT": 2,
    "START": 3,
    "UP": 4,
    "DOWN": 5,
    "LEFT": 6,
    "RIGHT": 7,
    "A": 8,
    "X": 9,
    "L": 10,
    "R": 11,
}

XRGB8888 = 1


class _GameInfo(C.Structure):
    _fields_ = [
        ("path", C.c_char_p),
        ("data", C.c_void_p),
        ("size", C.c_size_t),
        ("meta", C.c_char_p),
    ]


def read_rom(path: str | Path) -> bytes:
    """The bytes of a ``.gba`` file, or of the one ROM inside a ``.zip``."""
    path = Path(path)
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.lower().endswith(".gba"))
            return z.read(name)
    return path.read_bytes()


class Core:
    def __init__(self, core_path: str | Path, rom: bytes):
        self.lib: Any = C.CDLL(str(core_path))
        self.rom = C.create_string_buffer(bytes(rom), len(rom))  # writable copy, kept alive
        self.keys: set[int] = set()
        self.frame: tuple[bytes, int, int, int] | None = None  # data, width, height, pitch
        self.pixel_format = 2  # RGB565 unless the core asks otherwise
        self._dirs = C.create_string_buffer(b".")

        def env(cmd: int, data: Any) -> bool:
            if cmd == 10:  # SET_PIXEL_FORMAT
                self.pixel_format = C.cast(data, C.POINTER(C.c_int)).contents.value
                return True
            if cmd in (9, 30, 31):  # system, core assets, save directory
                C.cast(data, C.POINTER(C.c_char_p)).contents.value = C.cast(
                    self._dirs, C.c_char_p
                ).value
                return True
            if cmd == 3:  # GET_CAN_DUPE
                C.cast(data, C.POINTER(C.c_bool)).contents.value = True
                return True
            return cmd == 16  # SET_VARIABLES

        def video(data: Any, w: int, h: int, pitch: int) -> None:
            if data:
                self.frame = (C.string_at(data, pitch * h), w, h, pitch)

        self._callbacks = (
            _ENV(env),
            _VIDEO(video),
            _AUDIO(lambda left, right: None),
            _AUDIO_BATCH(lambda data, n: n),
            _POLL(lambda: None),
            _INPUT(lambda port, dev, idx, key: int(port == 0 and dev == 1 and key in self.keys)),
        )
        lib = self.lib
        lib.retro_set_environment(self._callbacks[0])
        lib.retro_init()
        lib.retro_set_video_refresh(self._callbacks[1])
        lib.retro_set_audio_sample(self._callbacks[2])
        lib.retro_set_audio_sample_batch(self._callbacks[3])
        lib.retro_set_input_poll(self._callbacks[4])
        lib.retro_set_input_state(self._callbacks[5])
        info = _GameInfo(b"game.gba", C.cast(self.rom, C.c_void_p), len(rom), None)
        if not lib.retro_load_game(C.byref(info)):
            raise RuntimeError("the core refused the ROM")
        lib.retro_serialize_size.restype = C.c_size_t
        self.state_size = int(lib.retro_serialize_size())

    def run(self, frames: int = 1) -> None:
        for _ in range(frames):
            self.lib.retro_run()

    def press(self, *names: str, frames: int = 3, release: int = 3) -> None:
        self.keys = {BUTTONS[n] for n in names}
        self.run(frames)
        self.keys = set()
        self.run(release)

    def load_state(self, state: bytes) -> bool:
        """Load an emulator state in the core's own format (for a RetroArch or PNG state, pass it
        through ``yomineko.survey.state.unwrap_state`` first)."""
        buf = C.create_string_buffer(state, len(state))
        return bool(self.lib.retro_unserialize(buf, len(state)))

    def gray_window(self, x0: int, x1: int, y0: int, y1: int) -> list[list[int]]:
        """Brightness (0-255) of a rectangle of the last frame, one list per row."""
        if self.frame is None:
            raise RuntimeError("no frame yet: run the core first")
        raw, _, _, pitch = self.frame
        rows = []
        for y in range(y0, y1):
            row = raw[y * pitch : (y + 1) * pitch]
            line = []
            for x in range(x0, x1):
                if self.pixel_format == XRGB8888:
                    line.append((row[x * 4] + row[x * 4 + 1] + row[x * 4 + 2]) // 3)
                else:
                    p = row[x * 2] | row[x * 2 + 1] << 8
                    r, g, b = (p >> 11) * 255 // 31, (p >> 5 & 63) * 255 // 63, (p & 31) * 255 // 31
                    line.append((r + g + b) // 3)
            rows.append(line)
        return rows

    def close(self) -> None:
        self.lib.retro_unload_game()
        self.lib.retro_deinit()

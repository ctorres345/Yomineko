import pytest
from support.synthrom import lcg_bytes, lz77_compress

from yomineko.core.compression.lz77 import (
    MAX_SIZE,
    CompressionError,
    compressed_size,
    decompress,
    decompress_measured,
)
from yomineko.errors import YominekoError


def _random(n: int, seed: int = 7) -> bytes:
    gen = lcg_bytes(seed)
    return bytes(next(gen) for _ in range(n))


PAYLOADS = {
    "empty": b"",
    "one byte": b"a",
    "short": b"abcabcabcabc",
    "run": b"\x00" * 300,  # overlapping copies, distance 1
    "random": _random(700),
    "window": _random(5000) + _random(5000),  # longer than the 4096-byte reference window
    "repeats": "ねこがおちゃをのむ。".encode() * 40,
}


@pytest.mark.parametrize("name", PAYLOADS)
@pytest.mark.parametrize("literals_only", [False, True])
def test_roundtrip_with_the_test_encoder(name, literals_only):
    payload = PAYLOADS[name]
    stream = lz77_compress(payload, literals_only=literals_only)
    assert decompress(stream) == payload
    assert compressed_size(stream) == len(stream)


def _plain_decode(stream: bytes) -> bytes:
    """The format read one byte at a time, as the hardware does: the reference to compare with."""
    size = int.from_bytes(stream[1:4], "little")
    out = bytearray()
    pos = 4
    while len(out) < size:
        flags = stream[pos]
        pos += 1
        for bit in range(7, -1, -1):
            if len(out) >= size:
                break
            if not flags >> bit & 1:
                out.append(stream[pos])
                pos += 1
                continue
            hi, lo = stream[pos], stream[pos + 1]
            pos += 2
            distance = ((hi & 0x0F) << 8 | lo) + 1
            for _ in range((hi >> 4) + 3):
                out.append(out[-distance])
    return bytes(out[:size])


def _random_stream(seed: int) -> bytes:
    """Literals and references of every length and distance, overlapping or not."""
    gen = lcg_bytes(seed)
    body = bytearray()
    written = 0
    while written < 3000:
        flags, group = 0, bytearray()
        for bit in range(7, -1, -1):
            if next(gen) % 3 and written:  # two references for every literal
                distance = min(next(gen) % 24 + 1, written)  # often shorter than the length
                length = next(gen) % 16 + 3
                flags |= 1 << bit
                group += bytes([(length - 3) << 4 | (distance - 1) >> 8, (distance - 1) & 0xFF])
                written += length
            else:
                group.append(next(gen))
                written += 1
        body += bytes([flags]) + group
    return bytes([0x10]) + written.to_bytes(3, "little") + bytes(body)


@pytest.mark.parametrize("seed", range(20))
def test_the_decoder_matches_a_byte_by_byte_reading_on_random_streams(seed):
    stream = _random_stream(seed)
    assert decompress(stream) == _plain_decode(stream)


def test_references_actually_shrink_repetitive_data():
    assert len(lz77_compress(b"\x00" * 300)) < 300 // 5


def test_hand_built_stream_with_a_known_result():
    # flags 0b00100000: two literals, then a reference (length 3, distance 2)
    stream = bytes([0x10, 5, 0, 0, 0x20, ord("a"), ord("b"), 0x00, 0x01])
    assert decompress(stream) == b"ababa"


def test_decoding_starts_at_the_offset_and_ignores_trailing_bytes():
    stream = lz77_compress(b"hello hello hello")
    blob = b"\xff" * 5 + stream + b"\xaa" * 9
    assert decompress(blob, 5) == b"hello hello hello"
    assert compressed_size(blob, 5) == len(stream)


def test_decompress_measured_gives_both_from_one_decode():
    stream = lz77_compress(b"hello hello hello")
    blob = b"\xff" * 5 + stream + b"\xaa" * 9
    assert decompress_measured(blob, 5) == (b"hello hello hello", len(stream))


def test_a_reference_running_past_the_declared_size_is_cut():
    stream = bytes([0x10, 4, 0, 0, 0x20, ord("a"), ord("b"), 0x10, 0x01])  # copies 4, 2 needed
    assert decompress(stream) == b"abab"


@pytest.mark.parametrize(
    ("blob", "message"),
    [
        (b"\x10\x01", "no LZ77 header"),
        (b"\x11\x01\x00\x00\x00a", "not an LZ77 stream"),
        (b"\x10\x05\x00\x00\x00ab", "ends early"),  # literals cut off
        (b"\x10\x05\x00\x00", "ends early"),  # no data at all
        (b"\x10\x05\x00\x00\x80\x00", "ends early"),  # a reference with one byte left
        (bytes([0x10, 9, 0, 0, 0x80, 0x00, 0x00]), "back"),  # nothing written to copy from
        (b"\x10" + (MAX_SIZE + 1).to_bytes(3, "little") + b"\x00", "too large"),
    ],
)
def test_malformed_streams_raise_a_yomineko_error(blob, message):
    with pytest.raises(CompressionError, match=message) as info:
        decompress(blob)
    assert isinstance(info.value, YominekoError)


def test_offset_outside_the_data_is_reported():
    with pytest.raises(CompressionError, match="no LZ77 header"):
        decompress(b"\x10\x00\x00\x00", 10)
    with pytest.raises(CompressionError, match="no LZ77 header"):
        decompress(b"\x10\x00\x00\x00", -1)

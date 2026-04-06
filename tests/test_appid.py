"""Tests for Steam AppID generation."""

from lutris_bridge.steam_appid import (
    generate_grid_id,
    generate_shortcut_id,
    generate_signed_appid,
)


def test_shortcut_id_top_bit_set():
    """The shortcut ID must always have the top bit set (>= 0x80000000)."""
    result = generate_shortcut_id('"test.exe"', "Test Game")
    assert result >= 0x80000000


def test_shortcut_id_deterministic():
    """Same inputs must produce the same ID."""
    a = generate_shortcut_id('"game.exe"', "My Game")
    b = generate_shortcut_id('"game.exe"', "My Game")
    assert a == b


def test_shortcut_id_different_for_different_inputs():
    """Different exe or name must produce different IDs."""
    a = generate_shortcut_id('"game1.exe"', "Game One")
    b = generate_shortcut_id('"game2.exe"', "Game Two")
    assert a != b


def test_shortcut_id_fits_32_bits():
    """Result must fit in a 32-bit unsigned integer."""
    result = generate_shortcut_id('"some/path/to/game.sh"', "A Very Long Game Name")
    assert 0 <= result <= 0xFFFFFFFF


def test_signed_appid_is_negative():
    """Since the top bit is always set, the signed appid should be negative."""
    result = generate_signed_appid('"test.exe"', "Test Game")
    assert result < 0


def test_signed_appid_roundtrip():
    """Signed appid converted back to unsigned must match shortcut_id."""
    exe, name = '"game.exe"', "My Game"
    unsigned = generate_shortcut_id(exe, name)
    signed = generate_signed_appid(exe, name)
    # Convert signed back to unsigned
    roundtrip = signed & 0xFFFFFFFF
    assert roundtrip == unsigned


def test_grid_id_matches_shortcut_id():
    """Grid ID is the same as the unsigned shortcut ID."""
    exe, name = '"game.exe"', "My Game"
    assert generate_grid_id(exe, name) == generate_shortcut_id(exe, name)


def test_known_value():
    """Test against a manually computed CRC32 value.

    CRC32 of '"test.exe"Test' = some known value, OR'd with 0x80000000.
    """
    import binascii

    exe = '"test.exe"'
    name = "Test"
    expected_crc = binascii.crc32((exe + name).encode("utf-8")) & 0xFFFFFFFF
    expected = expected_crc | 0x80000000
    assert generate_shortcut_id(exe, name) == expected

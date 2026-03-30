"""Create a sample shortcuts.vdf binary fixture for testing."""

import struct
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def write_string(key: str, value: str) -> bytes:
    return b"\x01" + key.encode() + b"\x00" + value.encode() + b"\x00"


def write_uint32(key: str, value: int) -> bytes:
    return b"\x02" + key.encode() + b"\x00" + struct.pack("<I", value & 0xFFFFFFFF)


def write_obj_start(key: str) -> bytes:
    return b"\x00" + key.encode() + b"\x00"


def write_obj_end() -> bytes:
    return b"\x08"


def create_test_vdf():
    FIXTURES_DIR.mkdir(exist_ok=True)

    parts = []
    # Root: \x00"shortcuts"\x00
    parts.append(write_obj_start("shortcuts"))

    # Entry 0: A manually added non-Steam game
    parts.append(write_obj_start("0"))
    parts.append(write_uint32("appid", 2947583910))
    parts.append(write_string("AppName", "Manual Game"))
    parts.append(write_string("Exe", '"/usr/bin/manual-game"'))
    parts.append(write_string("StartDir", '"/usr/bin"'))
    parts.append(write_string("icon", ""))
    parts.append(write_string("ShortcutPath", ""))
    parts.append(write_string("LaunchOptions", ""))
    parts.append(write_uint32("IsHidden", 0))
    parts.append(write_uint32("AllowDesktopConfig", 1))
    parts.append(write_uint32("AllowOverlay", 1))
    parts.append(write_uint32("OpenVR", 0))
    parts.append(write_uint32("Devkit", 0))
    parts.append(write_string("DevkitGameID", ""))
    parts.append(write_uint32("DevkitOverrideAppID", 0))
    parts.append(write_uint32("LastPlayTime", 1711800000))
    parts.append(write_string("FlatpakAppID", ""))
    # tags: empty
    parts.append(write_obj_start("tags"))
    parts.append(write_obj_end())
    parts.append(write_obj_end())  # end entry 0

    # Entry 1: A lutris-bridge managed game
    parts.append(write_obj_start("1"))
    parts.append(write_uint32("appid", 3100000001))
    parts.append(write_string("AppName", "Managed Game"))
    parts.append(write_string("Exe", '"/home/user/.local/share/lutris-bridge/scripts/managed-game.sh"'))
    parts.append(write_string("StartDir", '"/home/user/.local/share/lutris-bridge/scripts"'))
    parts.append(write_string("icon", ""))
    parts.append(write_string("ShortcutPath", ""))
    parts.append(write_string("LaunchOptions", ""))
    parts.append(write_uint32("IsHidden", 0))
    parts.append(write_uint32("AllowDesktopConfig", 1))
    parts.append(write_uint32("AllowOverlay", 1))
    parts.append(write_uint32("OpenVR", 0))
    parts.append(write_uint32("Devkit", 0))
    parts.append(write_string("DevkitGameID", ""))
    parts.append(write_uint32("DevkitOverrideAppID", 0))
    parts.append(write_uint32("LastPlayTime", 0))
    parts.append(write_string("FlatpakAppID", ""))
    # tags: has "lutris-bridge"
    parts.append(write_obj_start("tags"))
    parts.append(write_string("0", "lutris-bridge"))
    parts.append(write_obj_end())
    parts.append(write_obj_end())  # end entry 1

    # End shortcuts object
    parts.append(write_obj_end())
    # End root
    parts.append(write_obj_end())

    vdf_path = FIXTURES_DIR / "shortcuts.vdf"
    vdf_path.write_bytes(b"".join(parts))
    print(f"Created test VDF at {vdf_path} ({len(b''.join(parts))} bytes)")


if __name__ == "__main__":
    create_test_vdf()

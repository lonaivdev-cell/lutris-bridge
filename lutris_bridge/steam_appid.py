"""Steam non-Steam shortcut AppID generation.

Generates the unique identifiers Steam uses internally for non-Steam game
shortcuts. These must match Steam's own calculation or artwork won't display
and shortcut management will break.
"""

import binascii


def generate_shortcut_id(exe: str, app_name: str) -> int:
    """Generate Steam's non-Steam game shortcut ID.

    This matches the algorithm Steam uses internally: CRC32 of the
    concatenation of exe and app_name, with the top bit set.

    Args:
        exe: The executable path as stored in shortcuts.vdf (including quotes).
        app_name: The display name of the shortcut.

    Returns:
        A 32-bit unsigned integer shortcut ID.
    """
    unique_id = exe + app_name
    id_int = binascii.crc32(unique_id.encode("utf-8")) & 0xFFFFFFFF
    return id_int | 0x80000000


def generate_signed_appid(exe: str, app_name: str) -> int:
    """Generate the signed 32-bit appid as stored in shortcuts.vdf.

    Steam stores the appid field as a signed 32-bit integer in shortcuts.vdf.
    This converts the unsigned shortcut ID to its signed representation.

    Args:
        exe: The executable path as stored in shortcuts.vdf (including quotes).
        app_name: The display name of the shortcut.

    Returns:
        A signed 32-bit integer appid (may be negative).
    """
    unsigned = generate_shortcut_id(exe, app_name)
    if unsigned >= 0x80000000:
        return unsigned - 0x100000000
    return unsigned


def generate_grid_id(exe: str, app_name: str) -> int:
    """Generate the ID used for Steam grid artwork filenames.

    Steam uses the unsigned shortcut ID directly for grid artwork filenames
    in the userdata/<id>/config/grid/ directory. Files are named like:
    {grid_id}p.png (portrait), {grid_id}_hero.png, {grid_id}_logo.png, etc.

    Args:
        exe: The executable path as stored in shortcuts.vdf (including quotes).
        app_name: The display name of the shortcut.

    Returns:
        The artwork grid ID (same as unsigned shortcut ID).
    """
    return generate_shortcut_id(exe, app_name)

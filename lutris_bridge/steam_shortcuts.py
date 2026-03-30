"""Binary VDF parser and writer for Steam's shortcuts.vdf.

This is the most critical module in lutris-bridge. A malformed shortcuts.vdf
will cause Steam to delete all non-Steam shortcuts. The binary format must be
handled with extreme precision.

Binary VDF format:
    \\x00 + key + \\x00        = start of a sub-object
    \\x01 + key + \\x00 + val + \\x00 = string value
    \\x02 + key + \\x00 + 4_bytes_le  = uint32 value
    \\x08                      = end of current object
"""

import logging
import shutil
import struct
from collections import OrderedDict
from pathlib import Path

logger = logging.getLogger(__name__)

# VDF type tags
VDF_TYPE_OBJECT = 0x00
VDF_TYPE_STRING = 0x01
VDF_TYPE_UINT32 = 0x02
VDF_TYPE_END = 0x08


def _read_string(data: bytes, offset: int) -> tuple[str, int]:
    """Read a null-terminated string from data at offset.

    Returns:
        Tuple of (string, new_offset past the null terminator).
    """
    end = data.index(b"\x00", offset)
    s = data[offset:end].decode("utf-8", errors="replace")
    return s, end + 1


def _read_object(data: bytes, offset: int) -> tuple[OrderedDict, int]:
    """Recursively read a VDF object from binary data.

    Returns:
        Tuple of (OrderedDict of key-value pairs, new_offset).
    """
    obj = OrderedDict()

    while offset < len(data):
        type_byte = data[offset]
        offset += 1

        if type_byte == VDF_TYPE_END:
            return obj, offset

        # Read the key name
        key, offset = _read_string(data, offset)

        if type_byte == VDF_TYPE_OBJECT:
            value, offset = _read_object(data, offset)
            obj[key] = value

        elif type_byte == VDF_TYPE_STRING:
            value, offset = _read_string(data, offset)
            obj[key] = value

        elif type_byte == VDF_TYPE_UINT32:
            value = struct.unpack_from("<I", data, offset)[0]
            offset += 4
            obj[key] = value

        else:
            raise ValueError(
                f"Unknown VDF type byte 0x{type_byte:02x} at offset {offset - 1}"
            )

    return obj, offset


def _write_object(obj: OrderedDict) -> bytes:
    """Serialize a VDF object to binary format."""
    parts = []

    for key, value in obj.items():
        key_bytes = key.encode("utf-8") + b"\x00"

        if isinstance(value, OrderedDict):
            parts.append(bytes([VDF_TYPE_OBJECT]) + key_bytes)
            parts.append(_write_object(value))
            parts.append(bytes([VDF_TYPE_END]))

        elif isinstance(value, dict):
            # Convert regular dicts to OrderedDict for serialization
            parts.append(bytes([VDF_TYPE_OBJECT]) + key_bytes)
            parts.append(_write_object(OrderedDict(value)))
            parts.append(bytes([VDF_TYPE_END]))

        elif isinstance(value, int):
            parts.append(bytes([VDF_TYPE_UINT32]) + key_bytes)
            parts.append(struct.pack("<I", value & 0xFFFFFFFF))

        elif isinstance(value, str):
            parts.append(bytes([VDF_TYPE_STRING]) + key_bytes)
            parts.append(value.encode("utf-8") + b"\x00")

        else:
            raise TypeError(f"Unsupported VDF value type: {type(value)} for key '{key}'")

    return b"".join(parts)


def read_shortcuts(path: Path) -> list[OrderedDict]:
    """Parse a Steam shortcuts.vdf file.

    Args:
        path: Path to shortcuts.vdf.

    Returns:
        List of shortcut entry OrderedDicts. Returns empty list if file
        doesn't exist or is empty.
    """
    if not path.exists():
        logger.info("shortcuts.vdf not found at %s, starting fresh", path)
        return []

    data = path.read_bytes()
    if not data:
        return []

    try:
        root, _ = _read_object(data, 0)
    except Exception:
        logger.error("Failed to parse shortcuts.vdf at %s", path, exc_info=True)
        raise

    # The root object should contain a "shortcuts" key with numbered entries
    shortcuts_obj = root.get("shortcuts", root)

    # Extract numbered entries in order
    shortcuts = []
    for key in sorted(shortcuts_obj.keys(), key=lambda k: int(k) if k.isdigit() else float("inf")):
        if key.isdigit():
            entry = shortcuts_obj[key]
            if isinstance(entry, (dict, OrderedDict)):
                shortcuts.append(
                    OrderedDict(entry) if not isinstance(entry, OrderedDict) else entry
                )

    return shortcuts


def write_shortcuts(path: Path, shortcuts: list[dict | OrderedDict]) -> None:
    """Write shortcuts to a Steam shortcuts.vdf file.

    Args:
        path: Path to write shortcuts.vdf.
        shortcuts: List of shortcut entry dicts.
    """
    # Build the root structure: \x00"shortcuts"\x00 { numbered entries } \x08
    # The file starts with the type byte for the root "shortcuts" object
    parts = []

    # Root object start: type 0x00 + "shortcuts" + \x00
    parts.append(bytes([VDF_TYPE_OBJECT]) + b"shortcuts\x00")

    # Write each shortcut as a numbered entry
    for i, shortcut in enumerate(shortcuts):
        entry = OrderedDict(shortcut) if not isinstance(shortcut, OrderedDict) else shortcut
        key_bytes = str(i).encode("utf-8") + b"\x00"
        parts.append(bytes([VDF_TYPE_OBJECT]) + key_bytes)
        parts.append(_write_object(entry))
        parts.append(bytes([VDF_TYPE_END]))

    # End of shortcuts object
    parts.append(bytes([VDF_TYPE_END]))
    # End of root object
    parts.append(bytes([VDF_TYPE_END]))

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(parts))
    logger.info("Wrote %d shortcuts to %s", len(shortcuts), path)


def backup_shortcuts(path: Path) -> Path | None:
    """Create a backup of shortcuts.vdf before modifying it.

    Args:
        path: Path to shortcuts.vdf.

    Returns:
        Path to the backup file, or None if original doesn't exist.
    """
    if not path.exists():
        return None

    backup_path = path.with_suffix(".vdf.lutris-bridge-backup")
    shutil.copy2(path, backup_path)
    logger.info("Backed up shortcuts.vdf to %s", backup_path)
    return backup_path


def find_managed_shortcuts(
    shortcuts: list[dict | OrderedDict], tag: str = "lutris-bridge"
) -> list[dict | OrderedDict]:
    """Filter shortcuts to only those managed by lutris-bridge.

    Managed shortcuts are identified by having the given tag in their tags
    sub-object.

    Args:
        shortcuts: List of shortcut entries.
        tag: Tag string to look for.

    Returns:
        Filtered list of managed shortcuts.
    """
    managed = []
    for shortcut in shortcuts:
        tags = shortcut.get("tags", {})
        if isinstance(tags, (dict, OrderedDict)):
            if tag in tags.values():
                managed.append(shortcut)
    return managed


def _has_tag(shortcut: dict | OrderedDict, tag: str) -> bool:
    """Check if a shortcut has a specific tag."""
    tags = shortcut.get("tags", {})
    if isinstance(tags, (dict, OrderedDict)):
        return tag in tags.values()
    return False


def _ensure_tag(shortcut: dict | OrderedDict, tag: str) -> None:
    """Ensure a shortcut has the given tag."""
    if "tags" not in shortcut:
        shortcut["tags"] = OrderedDict()

    tags = shortcut["tags"]
    if not isinstance(tags, (dict, OrderedDict)):
        shortcut["tags"] = OrderedDict()
        tags = shortcut["tags"]

    # Check if tag already exists
    if tag in tags.values():
        return

    # Add tag with next available numeric key
    existing_keys = [int(k) for k in tags.keys() if k.isdigit()]
    next_key = str(max(existing_keys) + 1) if existing_keys else "0"
    tags[next_key] = tag


def upsert_shortcut(
    shortcuts: list[dict | OrderedDict],
    new_shortcut: dict | OrderedDict,
    tag: str = "lutris-bridge",
) -> list[dict | OrderedDict]:
    """Add or update a shortcut in the list.

    Matches by appid. If a shortcut with the same appid exists, it's updated.
    Otherwise, the new shortcut is appended.

    Args:
        shortcuts: Current list of shortcuts.
        new_shortcut: The shortcut to add or update.
        tag: Tag to apply to the managed shortcut.

    Returns:
        Updated list of shortcuts.
    """
    new_shortcut = OrderedDict(new_shortcut) if not isinstance(new_shortcut, OrderedDict) else new_shortcut
    _ensure_tag(new_shortcut, tag)

    target_appid = new_shortcut.get("appid")

    for i, existing in enumerate(shortcuts):
        if existing.get("appid") == target_appid:
            # Preserve any user-added tags
            if "tags" in existing:
                existing_tags = existing["tags"]
                if isinstance(existing_tags, (dict, OrderedDict)):
                    merged_tags = OrderedDict(existing_tags)
                    new_tags = new_shortcut.get("tags", {})
                    if isinstance(new_tags, (dict, OrderedDict)):
                        for k, v in new_tags.items():
                            if v not in merged_tags.values():
                                next_key = str(max((int(x) for x in merged_tags.keys() if x.isdigit()), default=-1) + 1)
                                merged_tags[next_key] = v
                    new_shortcut["tags"] = merged_tags

            shortcuts[i] = new_shortcut
            logger.debug("Updated shortcut: %s (appid=%s)", new_shortcut.get("AppName"), target_appid)
            return shortcuts

    shortcuts.append(new_shortcut)
    logger.debug("Added shortcut: %s (appid=%s)", new_shortcut.get("AppName"), target_appid)
    return shortcuts


def remove_shortcut_by_appid(
    shortcuts: list[dict | OrderedDict], appid: int
) -> list[dict | OrderedDict]:
    """Remove a shortcut by its appid.

    Args:
        shortcuts: Current list of shortcuts.
        appid: The appid to remove.

    Returns:
        Updated list with the shortcut removed.
    """
    original_len = len(shortcuts)
    shortcuts = [s for s in shortcuts if s.get("appid") != appid]
    if len(shortcuts) < original_len:
        logger.debug("Removed shortcut with appid=%s", appid)
    return shortcuts


def build_shortcut_entry(
    app_name: str,
    exe_path: str,
    start_dir: str,
    appid: int,
    icon: str = "",
    launch_options: str = "",
) -> OrderedDict:
    """Build a shortcut entry dict with all required fields.

    Args:
        app_name: Display name of the game.
        exe_path: Path to the launch script (will be quoted).
        start_dir: Start directory (will be quoted).
        appid: The shortcut's appid.
        icon: Path to icon file.
        launch_options: Additional launch options.

    Returns:
        OrderedDict with all shortcut fields populated.
    """
    return OrderedDict([
        ("appid", appid & 0xFFFFFFFF),
        ("AppName", app_name),
        ("Exe", f'"{exe_path}"'),
        ("StartDir", f'"{start_dir}"'),
        ("icon", icon),
        ("ShortcutPath", ""),
        ("LaunchOptions", launch_options),
        ("IsHidden", 0),
        ("AllowDesktopConfig", 1),
        ("AllowOverlay", 1),
        ("OpenVR", 0),
        ("Devkit", 0),
        ("DevkitGameID", ""),
        ("DevkitOverrideAppID", 0),
        ("LastPlayTime", 0),
        ("FlatpakAppID", ""),
        ("tags", OrderedDict()),
    ])

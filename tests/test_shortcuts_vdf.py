"""Exhaustive tests for Steam shortcuts.vdf binary parser/writer.

The VDF module is the most critical part of lutris-bridge — a malformed
shortcuts.vdf will cause Steam to delete all non-Steam shortcuts. These
tests verify round-trip fidelity, edge cases, and data integrity.
"""

from collections import OrderedDict
from pathlib import Path

import pytest

from lutris_bridge.steam_shortcuts import (
    backup_shortcuts,
    build_shortcut_entry,
    find_managed_shortcuts,
    read_shortcuts,
    remove_shortcut_by_appid,
    upsert_shortcut,
    write_shortcuts,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
TEST_VDF = FIXTURES_DIR / "shortcuts.vdf"


class TestReadShortcuts:
    def test_reads_fixture(self):
        shortcuts = read_shortcuts(TEST_VDF)
        assert len(shortcuts) == 2

    def test_first_entry_is_manual(self):
        shortcuts = read_shortcuts(TEST_VDF)
        assert shortcuts[0]["AppName"] == "Manual Game"
        assert shortcuts[0]["appid"] == 2947583910

    def test_second_entry_is_managed(self):
        shortcuts = read_shortcuts(TEST_VDF)
        assert shortcuts[1]["AppName"] == "Managed Game"
        assert shortcuts[1]["appid"] == 3100000001

    def test_string_fields_preserved(self):
        shortcuts = read_shortcuts(TEST_VDF)
        assert shortcuts[0]["Exe"] == '"/usr/bin/manual-game"'
        assert shortcuts[0]["StartDir"] == '"/usr/bin"'

    def test_uint32_fields_preserved(self):
        shortcuts = read_shortcuts(TEST_VDF)
        assert shortcuts[0]["IsHidden"] == 0
        assert shortcuts[0]["AllowDesktopConfig"] == 1
        assert shortcuts[0]["LastPlayTime"] == 1711800000

    def test_tags_parsed(self):
        shortcuts = read_shortcuts(TEST_VDF)
        # Manual game has empty tags
        assert shortcuts[0]["tags"] == OrderedDict()
        # Managed game has lutris-bridge tag
        assert shortcuts[1]["tags"]["0"] == "lutris-bridge"

    def test_nonexistent_file_returns_empty(self, tmp_path):
        shortcuts = read_shortcuts(tmp_path / "nonexistent.vdf")
        assert shortcuts == []

    def test_empty_file_returns_empty(self, tmp_path):
        empty_vdf = tmp_path / "empty.vdf"
        empty_vdf.write_bytes(b"")
        shortcuts = read_shortcuts(empty_vdf)
        assert shortcuts == []


class TestWriteShortcuts:
    def test_write_creates_file(self, tmp_path):
        vdf_path = tmp_path / "shortcuts.vdf"
        shortcuts = [build_shortcut_entry("Test", "/test.sh", "/", 12345)]
        write_shortcuts(vdf_path, shortcuts)
        assert vdf_path.exists()
        assert vdf_path.stat().st_size > 0

    def test_write_creates_parent_dirs(self, tmp_path):
        vdf_path = tmp_path / "deep" / "nested" / "shortcuts.vdf"
        write_shortcuts(vdf_path, [])
        assert vdf_path.exists()


class TestRoundTrip:
    """Round-trip tests: read → write → read must produce identical data."""

    def test_roundtrip_fixture(self, tmp_path):
        """Read the fixture, write it, read again — must match."""
        original = read_shortcuts(TEST_VDF)
        assert len(original) == 2

        output_path = tmp_path / "shortcuts.vdf"
        write_shortcuts(output_path, original)

        roundtripped = read_shortcuts(output_path)
        assert len(roundtripped) == len(original)

        for orig, rt in zip(original, roundtripped):
            assert orig["appid"] == rt["appid"]
            assert orig["AppName"] == rt["AppName"]
            assert orig["Exe"] == rt["Exe"]
            assert orig["StartDir"] == rt["StartDir"]
            assert orig["IsHidden"] == rt["IsHidden"]
            assert orig["AllowDesktopConfig"] == rt["AllowDesktopConfig"]
            assert orig["AllowOverlay"] == rt["AllowOverlay"]
            assert orig["LastPlayTime"] == rt["LastPlayTime"]

    def test_roundtrip_preserves_tags(self, tmp_path):
        original = read_shortcuts(TEST_VDF)
        output_path = tmp_path / "shortcuts.vdf"
        write_shortcuts(output_path, original)
        roundtripped = read_shortcuts(output_path)

        assert roundtripped[1]["tags"]["0"] == "lutris-bridge"

    def test_roundtrip_empty_list(self, tmp_path):
        output_path = tmp_path / "shortcuts.vdf"
        write_shortcuts(output_path, [])
        roundtripped = read_shortcuts(output_path)
        assert roundtripped == []

    def test_roundtrip_single_entry(self, tmp_path):
        entry = build_shortcut_entry(
            "Round Trip Game",
            "/path/to/game.sh",
            "/path/to",
            0xDEADBEEF,
            icon="/path/to/icon.png",
        )
        entry["tags"] = OrderedDict([("0", "test-tag"), ("1", "another-tag")])

        output_path = tmp_path / "shortcuts.vdf"
        write_shortcuts(output_path, [entry])
        roundtripped = read_shortcuts(output_path)

        assert len(roundtripped) == 1
        rt = roundtripped[0]
        assert rt["AppName"] == "Round Trip Game"
        assert rt["appid"] == 0xDEADBEEF
        assert rt["icon"] == "/path/to/icon.png"
        assert rt["tags"]["0"] == "test-tag"
        assert rt["tags"]["1"] == "another-tag"

    def test_roundtrip_many_entries(self, tmp_path):
        entries = []
        for i in range(20):
            entry = build_shortcut_entry(
                f"Game {i}",
                f"/scripts/game_{i}.sh",
                "/scripts",
                0x80000000 + i,
            )
            entries.append(entry)

        output_path = tmp_path / "shortcuts.vdf"
        write_shortcuts(output_path, entries)
        roundtripped = read_shortcuts(output_path)

        assert len(roundtripped) == 20
        for i, rt in enumerate(roundtripped):
            assert rt["AppName"] == f"Game {i}"
            assert rt["appid"] == 0x80000000 + i

    def test_roundtrip_special_characters(self, tmp_path):
        entry = build_shortcut_entry(
            "Game: Special & Characters!",
            "/path/to/my game (2024).sh",
            "/path/to",
            0x90000001,
        )
        output_path = tmp_path / "shortcuts.vdf"
        write_shortcuts(output_path, [entry])
        roundtripped = read_shortcuts(output_path)

        assert roundtripped[0]["AppName"] == "Game: Special & Characters!"
        assert "my game (2024)" in roundtripped[0]["Exe"]

    def test_roundtrip_binary_identical(self, tmp_path):
        """Write → read → write should produce identical bytes."""
        original = read_shortcuts(TEST_VDF)

        path1 = tmp_path / "first.vdf"
        write_shortcuts(path1, original)

        reread = read_shortcuts(path1)
        path2 = tmp_path / "second.vdf"
        write_shortcuts(path2, reread)

        assert path1.read_bytes() == path2.read_bytes()


class TestFindManagedShortcuts:
    def test_finds_managed(self):
        shortcuts = read_shortcuts(TEST_VDF)
        managed = find_managed_shortcuts(shortcuts)
        assert len(managed) == 1
        assert managed[0]["AppName"] == "Managed Game"

    def test_excludes_unmanaged(self):
        shortcuts = read_shortcuts(TEST_VDF)
        managed = find_managed_shortcuts(shortcuts)
        names = {s["AppName"] for s in managed}
        assert "Manual Game" not in names

    def test_custom_tag(self):
        shortcuts = read_shortcuts(TEST_VDF)
        managed = find_managed_shortcuts(shortcuts, tag="nonexistent-tag")
        assert len(managed) == 0


class TestUpsertShortcut:
    def test_add_new(self):
        shortcuts = read_shortcuts(TEST_VDF)
        new = build_shortcut_entry("New Game", "/new.sh", "/", 0xAAAAAAAA)
        result = upsert_shortcut(shortcuts, new)
        assert len(result) == 3
        assert result[-1]["AppName"] == "New Game"

    def test_update_existing(self):
        shortcuts = read_shortcuts(TEST_VDF)
        updated = build_shortcut_entry("Updated Managed Game", "/updated.sh", "/", 3100000001)
        result = upsert_shortcut(shortcuts, updated)
        assert len(result) == 2  # No new entry added
        # Find the updated one
        managed = [s for s in result if s["appid"] == 3100000001]
        assert managed[0]["AppName"] == "Updated Managed Game"

    def test_adds_tag(self):
        shortcuts = []
        new = build_shortcut_entry("Tagged Game", "/game.sh", "/", 0xBBBBBBBB)
        result = upsert_shortcut(shortcuts, new, tag="lutris-bridge")
        assert "lutris-bridge" in result[0]["tags"].values()

    def test_preserves_unmanaged(self):
        shortcuts = read_shortcuts(TEST_VDF)
        new = build_shortcut_entry("New", "/new.sh", "/", 0xCCCCCCCC)
        result = upsert_shortcut(shortcuts, new)
        manual = [s for s in result if s["AppName"] == "Manual Game"]
        assert len(manual) == 1
        assert manual[0]["appid"] == 2947583910


class TestRemoveShortcut:
    def test_removes_by_appid(self):
        shortcuts = read_shortcuts(TEST_VDF)
        result = remove_shortcut_by_appid(shortcuts, 3100000001)
        assert len(result) == 1
        assert result[0]["AppName"] == "Manual Game"

    def test_preserves_others(self):
        shortcuts = read_shortcuts(TEST_VDF)
        result = remove_shortcut_by_appid(shortcuts, 3100000001)
        assert result[0]["appid"] == 2947583910

    def test_nonexistent_appid_noop(self):
        shortcuts = read_shortcuts(TEST_VDF)
        result = remove_shortcut_by_appid(shortcuts, 9999999)
        assert len(result) == 2


class TestBackup:
    def test_creates_backup(self, tmp_path):
        vdf = tmp_path / "shortcuts.vdf"
        vdf.write_bytes(b"test data")
        backup_path = backup_shortcuts(vdf)
        assert backup_path is not None
        assert backup_path.exists()
        assert backup_path.read_bytes() == b"test data"
        assert "lutris-bridge-backup" in backup_path.name

    def test_nonexistent_returns_none(self, tmp_path):
        result = backup_shortcuts(tmp_path / "nonexistent.vdf")
        assert result is None


class TestBuildShortcutEntry:
    def test_has_all_required_fields(self):
        entry = build_shortcut_entry("Game", "/game.sh", "/", 12345)
        assert "appid" in entry
        assert "AppName" in entry
        assert "Exe" in entry
        assert "StartDir" in entry
        assert "tags" in entry

    def test_quotes_exe(self):
        entry = build_shortcut_entry("Game", "/path/to/game.sh", "/", 12345)
        assert entry["Exe"] == '"/path/to/game.sh"'

    def test_controller_flags_set(self):
        entry = build_shortcut_entry("Game", "/game.sh", "/", 12345)
        assert entry["AllowDesktopConfig"] == 1
        assert entry["AllowOverlay"] == 1

    def test_appid_masked(self):
        entry = build_shortcut_entry("Game", "/game.sh", "/", 0x1FFFFFFFF)
        assert entry["appid"] == 0xFFFFFFFF

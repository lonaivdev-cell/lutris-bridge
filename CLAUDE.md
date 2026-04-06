# CLAUDE.md — lutris-bridge

## What this project does

lutris-bridge syncs Lutris-installed games into Steam as non-Steam shortcuts, optimized for Bazzite's Steam Gaming Mode (Gamescope session). It generates standalone bash launch scripts that replicate the environment Lutris sets up, so games launch directly without the Lutris GUI.

## Critical design constraints

1. **No Lutris GUI at runtime** — launch scripts are self-contained bash scripts with baked-in environment variables. They do NOT shell out to `lutris`.
2. **No nested gamescope** — scripts must NEVER invoke `gamescope`. Bazzite Gaming Mode already runs inside a session-level Gamescope compositor. Nesting breaks display and controller input (bazzite issue #1500). A runtime assertion in `script_gen.py` enforces this.
3. **Controller passthrough** — all shortcuts set `AllowDesktopConfig=1` and `AllowOverlay=1` so Steam Input passes controller events through Gamescope -> Xwayland -> game.
4. **Bazzite-safe** — no root required, no rpm-ostree layering. Pure Python with pip-installable dependencies.

## Build and test

```bash
# Install dependencies
pip install pyyaml requests pytest

# Run tests
python -m pytest tests/ -v

# Run a single test file
python -m pytest tests/test_shortcuts_vdf.py -v
```

No build step is needed — this is a pure Python project. For editable install: `pip install -e ".[dev]"` (requires setuptools).

## Project layout

```
lutris_bridge/
  __init__.py          # Version string
  cli.py               # argparse entry: sync, list, clean, status, generate-script
  config.py            # Path detection: Steam, Lutris (native/Flatpak), XDG dirs
  lutris_db.py         # Read Lutris pga.db (SQLite, read-only)
  lutris_config.py     # Parse Lutris game/runner YAML configs with cascade merge
  script_gen.py        # Generate standalone bash launch scripts per game
  steam_shortcuts.py   # Binary VDF parser/writer for shortcuts.vdf
  steam_appid.py       # Non-Steam shortcut AppID calculation (CRC32-based)
  artwork.py           # SteamGridDB API: fetch grid/hero/logo/icon artwork
  sync.py              # Orchestrator: discover -> diff -> generate -> write
  state.py             # JSON state persistence (~/.local/share/lutris-bridge/state.json)
tests/
  test_appid.py        # AppID generation tests
  test_lutris_db.py    # Database reader tests (uses fixtures/pga.db)
  test_script_gen.py   # Launch script generation tests
  test_shortcuts_vdf.py # Binary VDF round-trip tests (uses fixtures/shortcuts.vdf)
  fixtures/            # Test fixture files (sample pga.db, shortcuts.vdf)
```

## Module dependency order

```
steam_appid.py          (pure, no deps)
config.py               (filesystem detection)
lutris_db.py            (depends on config for paths)
lutris_config.py        (depends on config for paths)
script_gen.py           (depends on lutris_config, lutris_db)
steam_shortcuts.py      (depends on steam_appid)
state.py                (standalone JSON persistence)
artwork.py              (depends on steam_appid, config)
sync.py                 (orchestrates all above)
cli.py                  (thin wrapper around sync)
```

## Key implementation details

### Binary VDF (steam_shortcuts.py) — highest risk module

The binary VDF format used by `shortcuts.vdf` is undocumented. A malformed file causes Steam to delete all non-Steam shortcuts. Key rules:

- Type tags: `\x00` = sub-object, `\x01` = string, `\x02` = uint32, `\x08` = end
- Uses `OrderedDict` to preserve field ordering (critical for round-trip fidelity)
- Always back up `shortcuts.vdf` before writing (saved as `.lutris-bridge-backup`)
- Never modify shortcuts without the `lutris-bridge` tag — user-created shortcuts are untouched
- The `write -> read -> write` cycle must produce byte-identical output (tested in `TestRoundTrip`)

### AppID calculation (steam_appid.py)

```
shortcut_id = CRC32(exe + app_name) | 0x80000000
```

The `exe` string must include quotes exactly as stored in shortcuts.vdf (e.g., `'"path/to/script.sh"'`). Getting this wrong means artwork won't display.

### Config cascade (lutris_config.py)

Lutris configs merge: game YAML > runner YAML > defaults. The `_deep_merge()` function handles nested dict merging. Config sections (`game`, `wine`, `system`) are validated as dicts before access.

### Script generation (script_gen.py)

- Wine scripts: set WINEPREFIX, WINEDLLOVERRIDES, DXVK vars, resolve wine binary from Lutris runners dir
- Linux scripts: cd + exec
- Fallback: `lutris lutris:rungameid/{id}` (for dosbox, scummvm, etc.)
- `gamemoderun` prefix when gamemode is enabled in config
- `umu-run` when umu-launcher is configured

### State tracking (state.py)

State file at `~/.local/share/lutris-bridge/state.json` tracks managed games for incremental sync. Uses atomic writes (temp file + rename) to prevent corruption. On load failure, corrupted file is backed up and a fresh state is created.

## Coding conventions

- Python 3.11+ (Bazzite ships 3.12)
- Type hints on all public functions
- Logging via `logging` module (not print in library code)
- Dependencies: only `pyyaml`, `requests` (Pillow optional for artwork resize)
- Errors at system boundaries (file I/O, network, DB) are caught specifically — not blanket `except Exception`

## Common tasks

### Adding a new shortcut field
1. Add the field to `build_shortcut_entry()` in `steam_shortcuts.py`
2. Update the round-trip test in `test_shortcuts_vdf.py`
3. If it affects the launch script, update the template in `script_gen.py`

### Supporting a new Lutris runner
1. Add a new `generate_{runner}_script()` function in `script_gen.py`
2. Add the runner branch to `generate_launch_script()`
3. Add tests in `test_script_gen.py`
4. Ensure the new function passes `_assert_no_gamescope()`

### Modifying the state schema
1. Add fields to `ManagedGame` dataclass in `state.py` with defaults
2. The loader filters to known fields, so old state files won't break
3. Test with both old and new state files

## Dangerous operations

- **Writing shortcuts.vdf** — always call `backup_shortcuts()` first. A malformed write destroys all non-Steam shortcuts.
- **Steam must not be running** during sync — Steam overwrites shortcuts.vdf on exit. The sync warns but doesn't block.
- **Deleting scripts in ~/.local/share/lutris-bridge/scripts/** — these are the actual executables Steam launches. Removing them breaks the shortcuts.

## Test fixtures

- `tests/fixtures/pga.db` — regenerate with `python tests/create_test_db.py`
- `tests/fixtures/shortcuts.vdf` — regenerate with `python tests/create_test_vdf.py`

Both fixtures are committed binary files. If you change the test data structure, regenerate them.

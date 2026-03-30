"""Orchestrator for lutris-bridge sync workflow.

Discovers Lutris games, generates launch scripts, fetches artwork,
and writes Steam shortcuts. Supports incremental updates via state tracking.
"""

import hashlib
import logging
import subprocess
from pathlib import Path

from lutris_bridge.artwork import fetch_artwork
from lutris_bridge.config import Config
from lutris_bridge.lutris_config import parse_game_config
from lutris_bridge.lutris_db import LutrisGame, discover_games
from lutris_bridge.script_gen import generate_launch_script
from lutris_bridge.state import (
    BridgeState,
    ManagedGame,
    load_state,
    now_iso,
    save_state,
)
from lutris_bridge.steam_appid import generate_shortcut_id, generate_grid_id
from lutris_bridge.steam_shortcuts import (
    backup_shortcuts,
    build_shortcut_entry,
    read_shortcuts,
    remove_shortcut_by_appid,
    upsert_shortcut,
    write_shortcuts,
)

logger = logging.getLogger(__name__)


def _is_steam_running() -> bool:
    """Check if Steam is currently running."""
    try:
        result = subprocess.run(
            ["pgrep", "-x", "steam"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _config_hash(game_config_path: Path) -> str:
    """Compute a hash of a game's config file for change detection."""
    if not game_config_path.exists():
        return ""
    content = game_config_path.read_bytes()
    return f"sha256:{hashlib.sha256(content).hexdigest()[:16]}"


def sync(
    config: Config,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, int]:
    """Main sync workflow.

    Discovers Lutris games, generates launch scripts, fetches artwork,
    and writes Steam shortcuts.

    Args:
        config: Resolved configuration.
        dry_run: If True, don't write anything to disk.
        force: If True, regenerate all scripts and re-sync all games.

    Returns:
        Dict with counts: {"added": N, "removed": N, "updated": N, "total": N}
    """
    # 1. Check if Steam is running
    if not dry_run and _is_steam_running():
        logger.warning(
            "Steam appears to be running. Changes to shortcuts.vdf may be "
            "overwritten when Steam exits. Consider closing Steam first."
        )

    # 2. Load state from previous run
    state = load_state()
    state.steam_user_id = config.steam_user_id

    # 3. Discover Lutris games
    lutris_games = discover_games(config.lutris.db_path)
    logger.info("Found %d Lutris games", len(lutris_games))

    # 4. Read current Steam shortcuts
    shortcuts = read_shortcuts(config.shortcuts_vdf_path)
    logger.info("Read %d existing Steam shortcuts", len(shortcuts))

    # 5. Determine diff
    current_slugs = {g.slug for g in lutris_games}
    managed_slugs = set(state.managed_games.keys())
    to_add = current_slugs - managed_slugs
    to_remove = managed_slugs - current_slugs
    to_check = current_slugs & managed_slugs

    games_by_slug = {g.slug: g for g in lutris_games}
    counts = {"added": 0, "removed": 0, "updated": 0, "total": 0}

    # 6. Process additions and updates
    for slug in sorted(current_slugs):
        game = games_by_slug[slug]
        is_new = slug in to_add

        # Check if config has changed for existing games
        needs_update = is_new or force
        if not needs_update and slug in to_check:
            config_path = config.lutris.games_config_dir / f"{game.configpath}.yml"
            current_hash = _config_hash(config_path)
            managed = state.managed_games.get(slug)
            if managed and managed.config_hash != current_hash:
                needs_update = True

        if not needs_update:
            continue

        # Parse game config
        game_config = parse_game_config(
            config.lutris.games_config_dir,
            config.lutris.config_dir,
            game.configpath,
            game.runner,
        )

        if dry_run:
            action = "Would add" if is_new else "Would update"
            logger.info("%s: %s (%s)", action, game.name, game.runner)
            counts["added" if is_new else "updated"] += 1
            continue

        # Generate launch script
        script_path = generate_launch_script(
            game, game_config, config.bridge_scripts_dir, config.lutris.runners_dir
        )

        # Calculate IDs
        exe_str = f'"{script_path}"'
        appid = generate_shortcut_id(exe_str, game.name)
        grid_id = generate_grid_id(exe_str, game.name)

        # Fetch artwork
        fetch_artwork(
            game.name,
            grid_id,
            config.grid_dir,
            api_key=config.steamgriddb_api_key,
            lutris_data_dir=config.lutris.data_dir,
        )

        # Build and upsert shortcut
        shortcut = build_shortcut_entry(
            app_name=game.name,
            exe_path=str(script_path),
            start_dir=str(config.bridge_scripts_dir),
            appid=appid,
        )
        shortcuts = upsert_shortcut(shortcuts, shortcut)

        # Update state
        config_path = config.lutris.games_config_dir / f"{game.configpath}.yml"
        state.managed_games[slug] = ManagedGame(
            appid=appid,
            script_path=str(script_path),
            name=game.name,
            runner=game.runner,
            last_synced=now_iso(),
            config_hash=_config_hash(config_path),
        )

        action = "Added" if is_new else "Updated"
        logger.info("%s: %s (%s)", action, game.name, game.runner)
        counts["added" if is_new else "updated"] += 1

    # 7. Remove orphaned shortcuts
    for slug in sorted(to_remove):
        managed = state.managed_games.get(slug)
        if not managed:
            continue

        if dry_run:
            logger.info("Would remove: %s", managed.name)
            counts["removed"] += 1
            continue

        shortcuts = remove_shortcut_by_appid(shortcuts, managed.appid)

        # Remove script file
        script_path = Path(managed.script_path)
        if script_path.exists():
            script_path.unlink()
            logger.debug("Removed script: %s", script_path)

        del state.managed_games[slug]
        logger.info("Removed: %s", managed.name)
        counts["removed"] += 1

    # 8. Write shortcuts.vdf and state
    if not dry_run:
        backup_shortcuts(config.shortcuts_vdf_path)
        write_shortcuts(config.shortcuts_vdf_path, shortcuts)
        save_state(state)

    counts["total"] = len(state.managed_games)
    return counts


def clean(config: Config) -> int:
    """Remove all lutris-bridge-managed shortcuts and scripts.

    Args:
        config: Resolved configuration.

    Returns:
        Number of shortcuts removed.
    """
    state = load_state()
    if not state.managed_games:
        logger.info("No managed games to clean")
        return 0

    shortcuts = read_shortcuts(config.shortcuts_vdf_path)

    removed = 0
    for slug, managed in state.managed_games.items():
        shortcuts = remove_shortcut_by_appid(shortcuts, managed.appid)
        script_path = Path(managed.script_path)
        if script_path.exists():
            script_path.unlink()
        removed += 1
        logger.info("Cleaned: %s", managed.name)

    backup_shortcuts(config.shortcuts_vdf_path)
    write_shortcuts(config.shortcuts_vdf_path, shortcuts)

    state.managed_games.clear()
    save_state(state)

    return removed

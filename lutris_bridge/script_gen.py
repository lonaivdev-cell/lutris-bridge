"""Generate standalone bash launch scripts for Lutris games.

Scripts are self-contained and do not require the Lutris GUI or lutris-bridge
at runtime. They replicate the environment Lutris would set up by reading
the game's YAML config at generation time.

CRITICAL: Scripts must NOT invoke gamescope — the session-level Gamescope
in Bazzite Gaming Mode handles compositing. Nested gamescope breaks display
and controller input.
"""

import logging
import re
import stat
from datetime import datetime, timezone
from pathlib import Path

from lutris_bridge.lutris_config import GameConfig
from lutris_bridge.lutris_db import LutrisGame

logger = logging.getLogger(__name__)


def _sanitize_filename(slug: str) -> str:
    """Sanitize a game slug for use as a filename."""
    safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", slug)
    return safe.strip("_") or "game"


def _resolve_wine_binary(
    runners_dir: Path, wine_version: str | None
) -> str:
    """Resolve the full path to the Wine binary.

    Args:
        runners_dir: Lutris runners directory.
        wine_version: Wine version string from config (e.g., "lutris-GE-Proton8-14-x86_64").

    Returns:
        Full path to the wine binary, or "wine" as fallback.
    """
    if not wine_version:
        return "wine"

    wine_path = runners_dir / "wine" / wine_version / "bin" / "wine"
    if wine_path.exists():
        return str(wine_path)

    # Try without architecture suffix
    for candidate in (runners_dir / "wine").iterdir() if (runners_dir / "wine").is_dir() else []:
        if candidate.name.startswith(wine_version.split("-x86_64")[0]):
            bin_path = candidate / "bin" / "wine"
            if bin_path.exists():
                return str(bin_path)

    logger.warning("Wine binary not found for version %s, falling back to system wine", wine_version)
    return "wine"


def _shell_escape(s: str) -> str:
    """Escape a string for safe use in bash double quotes."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`")


def generate_wine_script(
    game: LutrisGame,
    game_config: GameConfig,
    runners_dir: Path,
) -> str:
    """Generate a bash launch script for a Wine/Proton game.

    Args:
        game: The Lutris game entry.
        game_config: Parsed game configuration.
        runners_dir: Path to Lutris runners directory.

    Returns:
        Script content as a string.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Determine if using umu-launcher
    if game_config.use_umu:
        wine_binary = "umu-run"
    else:
        wine_binary = _resolve_wine_binary(runners_dir, game_config.wine_version)

    lines = [
        "#!/bin/bash",
        f"# lutris-bridge launch script for: {game.name}",
        f"# Generated: {timestamp} | Slug: {game.slug} | DO NOT EDIT — will be overwritten",
        "",
    ]

    # WINEPREFIX
    if game_config.prefix:
        lines.append(f'export WINEPREFIX="{_shell_escape(game_config.prefix)}"')

    # DLL overrides
    if game_config.dll_overrides:
        lines.append(f'export WINEDLLOVERRIDES="{_shell_escape(game_config.dll_overrides)}"')

    # Standard Wine/DXVK environment
    lines.append('export WINE_LARGE_ADDRESS_AWARE=1')
    lines.append('export STAGING_SHARED_MEMORY=1')

    if game_config.prefix:
        lines.append(f'export DXVK_STATE_CACHE_PATH="{_shell_escape(game_config.prefix)}"')

    if game_config.dxvk:
        lines.append('export DXVK_LOG_LEVEL=none')
        lines.append('export DXVK_HUD=0')

    # Extra environment variables from config
    for key, value in sorted(game_config.env.items()):
        lines.append(f'export {key}="{_shell_escape(value)}"')

    lines.append("")

    # Working directory
    if game_config.working_dir:
        lines.append(f'cd "{_shell_escape(game_config.working_dir)}"')
        lines.append("")

    # Build launch command
    cmd_prefix = ""
    if game_config.gamemode:
        cmd_prefix = "gamemoderun "

    exe = game_config.exe or ""
    args = game_config.args

    lines.append(f'{cmd_prefix}"{_shell_escape(wine_binary)}" "{_shell_escape(exe)}" {args}'.rstrip())
    lines.append("")

    return "\n".join(lines)


def generate_linux_script(
    game: LutrisGame,
    game_config: GameConfig,
) -> str:
    """Generate a bash launch script for a native Linux game."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    lines = [
        "#!/bin/bash",
        f"# lutris-bridge launch script for: {game.name}",
        f"# Generated: {timestamp} | Slug: {game.slug} | DO NOT EDIT — will be overwritten",
        "",
    ]

    # Extra environment variables
    for key, value in sorted(game_config.env.items()):
        lines.append(f'export {key}="{_shell_escape(value)}"')

    if game_config.env:
        lines.append("")

    # Working directory
    working_dir = game_config.working_dir
    if working_dir:
        lines.append(f'cd "{_shell_escape(working_dir)}"')

    # Build launch command
    cmd_prefix = ""
    if game_config.gamemode:
        cmd_prefix = "gamemoderun "

    exe = game_config.exe or ""
    args = game_config.args

    lines.append(f'{cmd_prefix}"{_shell_escape(exe)}" {args}'.rstrip())
    lines.append("")

    return "\n".join(lines)


def generate_fallback_script(game: LutrisGame) -> str:
    """Generate a fallback script that launches via the Lutris client.

    Used for runners we don't natively support (dosbox, scummvm, retroarch, etc.).
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return "\n".join([
        "#!/bin/bash",
        f"# lutris-bridge launch script for: {game.name}",
        f"# Generated: {timestamp} | Slug: {game.slug} | DO NOT EDIT — will be overwritten",
        f"# Fallback: using Lutris client for runner '{game.runner}'",
        "",
        f'lutris "lutris:rungameid/{game.id}"',
        "",
    ])


def generate_launch_script(
    game: LutrisGame,
    game_config: GameConfig,
    scripts_dir: Path,
    runners_dir: Path,
) -> Path:
    """Generate a launch script for a game and write it to disk.

    Args:
        game: The Lutris game entry.
        game_config: Parsed game configuration.
        scripts_dir: Directory to write scripts to.
        runners_dir: Path to Lutris runners directory.

    Returns:
        Path to the generated script.
    """
    filename = f"{_sanitize_filename(game.slug)}.sh"
    script_path = scripts_dir / filename

    if game.runner == "wine":
        content = generate_wine_script(game, game_config, runners_dir)
    elif game.runner == "linux":
        content = generate_linux_script(game, game_config)
    else:
        content = generate_fallback_script(game)

    script_path.write_text(content)
    script_path.chmod(script_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    logger.info("Generated launch script: %s", script_path)
    return script_path

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


def _assert_no_gamescope(script: str) -> str:
    """Validate that a generated script never invokes gamescope.

    Nested gamescope breaks display and controller input in Bazzite's
    Gaming Mode (Gamescope session). See bazzite issue #1500.
    """
    if "gamescope" in script.lower():
        raise RuntimeError(
            "BUG: Generated script contains 'gamescope'. "
            "Scripts must never invoke gamescope — the session-level "
            "Gamescope in Gaming Mode handles compositing."
        )
    return script


def _sanitize_filename(slug: str) -> str:
    """Sanitize a game slug for use as a filename."""
    safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", slug)
    return safe.strip("_") or "game"


def _resolve_wine_binary(
    runners_dir: Path, wine_version: str | None
) -> str:
    """Resolve the full path to the Wine binary.

    Checks, in order:
    1. Exact match: runners/wine/{version}/bin/wine
    2. Prefix match without arch suffix (x86_64, i686)
    3. Fallback to system "wine"

    Args:
        runners_dir: Lutris runners directory.
        wine_version: Wine version string from config (e.g., "lutris-GE-Proton8-14-x86_64").

    Returns:
        Full path to the wine binary, or "wine" as fallback.
    """
    if not wine_version:
        return "wine"

    # 1. Exact match
    wine_path = runners_dir / "wine" / wine_version / "bin" / "wine"
    if wine_path.exists():
        return str(wine_path)

    # 2. Strip architecture suffix and try prefix match
    wine_dir = runners_dir / "wine"
    if wine_dir.is_dir():
        # Strip common arch suffixes from the end
        base_version = wine_version
        for arch_suffix in ("-x86_64", "-i686", "-x86"):
            if base_version.endswith(arch_suffix):
                base_version = base_version[: -len(arch_suffix)]
                break

        for candidate in sorted(wine_dir.iterdir()):
            if candidate.name.startswith(base_version) and candidate.is_dir():
                bin_path = candidate / "bin" / "wine"
                if bin_path.exists():
                    return str(bin_path)

    logger.warning(
        "Wine binary not found for version '%s', falling back to system wine",
        wine_version,
    )
    return "wine"


def _script_preamble(slug: str) -> list[str]:
    """Return bash preamble lines for error handling and logging.

    Adds set -eo pipefail so failures aren't silent, and an ERR trap that
    logs the failing line and exit code to a persistent log file. This is
    critical because Steam does not capture stderr from non-Steam shortcuts.
    """
    return [
        "set -eo pipefail",
        "",
        '_LB_LOG="$HOME/.local/share/lutris-bridge/launch-errors.log"',
        "_lb_err() {",
        f'    echo "[$(date -Iseconds)] FAIL {slug}: line ${{1}} exited ${{2}}" >> "$_LB_LOG"',
        "}",
        "trap '_lb_err ${LINENO} $?' ERR",
        "",
    ]


def _command_check_lines(slug: str, cmd: str) -> list[str]:
    """Return bash lines that verify a command exists at launch time."""
    return [
        f'if ! command -v "{cmd}" >/dev/null 2>&1; then',
        f'    echo "[$(date -Iseconds)] FAIL {slug}: command not found: {cmd}" >> "$_LB_LOG"',
        "    exit 1",
        "fi",
    ]


def _workdir_check_lines(slug: str, path: str) -> list[str]:
    """Return bash lines that verify a working directory exists."""
    escaped = _shell_quote(path)
    return [
        f'if [ ! -d "{escaped}" ]; then',
        f'    echo "[$(date -Iseconds)] FAIL {slug}: working dir not found: {path}" >> "$_LB_LOG"',
        "    exit 1",
        "fi",
    ]


def _file_exec_check_lines(slug: str, path: str) -> list[str]:
    """Return bash lines that verify a file exists and is executable."""
    escaped = _shell_quote(path)
    return [
        f'if [ ! -x "{escaped}" ]; then',
        f'    echo "[$(date -Iseconds)] FAIL {slug}: exe not found or not executable: {path}" >> "$_LB_LOG"',
        "    exit 1",
        "fi",
    ]


def _shell_quote(s: str) -> str:
    """Escape a string for safe embedding inside bash double quotes.

    Escapes backslashes, double quotes, dollar signs, and backticks —
    the four characters that are special inside double-quoted strings in bash.
    """
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
    if not game_config.exe:
        raise ValueError(
            f"Wine game '{game.name}' (slug={game.slug}) has no exe configured "
            "— cannot generate launch script"
        )

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

    # Error handling preamble
    lines.extend(_script_preamble(game.slug))

    # WINEPREFIX
    if game_config.prefix:
        lines.append(f'export WINEPREFIX="{_shell_quote(game_config.prefix)}"')

    # DLL overrides
    if game_config.dll_overrides:
        lines.append(f'export WINEDLLOVERRIDES="{_shell_quote(game_config.dll_overrides)}"')

    # Standard Wine/DXVK environment
    lines.append('export WINE_LARGE_ADDRESS_AWARE=1')
    lines.append('export STAGING_SHARED_MEMORY=1')

    if game_config.prefix:
        lines.append(f'export DXVK_STATE_CACHE_PATH="{_shell_quote(game_config.prefix)}"')

    if game_config.dxvk:
        lines.append('export DXVK_LOG_LEVEL=none')
        lines.append('export DXVK_HUD=0')

    # Extra environment variables from config
    for key, value in sorted(game_config.env.items()):
        lines.append(f'export {key}="{_shell_quote(value)}"')

    lines.append("")

    # Pre-flight checks
    lines.extend(_command_check_lines(game.slug, wine_binary))
    if game_config.gamemode:
        lines.extend(_command_check_lines(game.slug, "gamemoderun"))

    # Working directory
    if game_config.working_dir:
        lines.extend(_workdir_check_lines(game.slug, game_config.working_dir))
        lines.append(f'cd "{_shell_quote(game_config.working_dir)}"')
        lines.append("")

    # Build launch command
    cmd_prefix = ""
    if game_config.gamemode:
        cmd_prefix = "gamemoderun "

    exe = game_config.exe
    args = game_config.args

    lines.append(f'{cmd_prefix}"{_shell_quote(wine_binary)}" "{_shell_quote(exe)}" {args}'.rstrip())
    lines.append("")

    return _assert_no_gamescope("\n".join(lines))


def generate_linux_script(
    game: LutrisGame,
    game_config: GameConfig,
) -> str:
    """Generate a bash launch script for a native Linux game."""
    if not game_config.exe:
        raise ValueError(
            f"Linux game '{game.name}' (slug={game.slug}) has no exe configured "
            "— cannot generate launch script"
        )

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    lines = [
        "#!/bin/bash",
        f"# lutris-bridge launch script for: {game.name}",
        f"# Generated: {timestamp} | Slug: {game.slug} | DO NOT EDIT — will be overwritten",
        "",
    ]

    # Error handling preamble
    lines.extend(_script_preamble(game.slug))

    # Extra environment variables
    for key, value in sorted(game_config.env.items()):
        lines.append(f'export {key}="{_shell_quote(value)}"')

    if game_config.env:
        lines.append("")

    # Pre-flight checks
    lines.extend(_file_exec_check_lines(game.slug, game_config.exe))
    if game_config.gamemode:
        lines.extend(_command_check_lines(game.slug, "gamemoderun"))

    # Working directory
    working_dir = game_config.working_dir
    if working_dir:
        lines.extend(_workdir_check_lines(game.slug, working_dir))
        lines.append(f'cd "{_shell_quote(working_dir)}"')

    # Build launch command
    cmd_prefix = ""
    if game_config.gamemode:
        cmd_prefix = "gamemoderun "

    exe = game_config.exe
    args = game_config.args

    lines.append(f'{cmd_prefix}"{_shell_quote(exe)}" {args}'.rstrip())
    lines.append("")

    return _assert_no_gamescope("\n".join(lines))


def generate_fallback_script(game: LutrisGame) -> str:
    """Generate a fallback script that launches via the Lutris client.

    Used for runners we don't natively support (dosbox, scummvm, retroarch, etc.).
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    lines = [
        "#!/bin/bash",
        f"# lutris-bridge launch script for: {game.name}",
        f"# Generated: {timestamp} | Slug: {game.slug} | DO NOT EDIT — will be overwritten",
        f"# Fallback: using Lutris client for runner '{game.runner}'",
        "",
    ]

    # Error handling preamble
    lines.extend(_script_preamble(game.slug))

    # Pre-flight check
    lines.extend(_command_check_lines(game.slug, "lutris"))
    lines.append("")
    lines.append(f'lutris "lutris:rungameid/{game.id}"')
    lines.append("")

    return _assert_no_gamescope("\n".join(lines))


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

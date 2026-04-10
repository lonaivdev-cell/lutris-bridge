"""Path detection and configuration for lutris-bridge.

Auto-detects Steam installation, Lutris installation (native vs Flatpak),
and creates working directories.
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

FLATPAK_LUTRIS_DATA = Path.home() / ".var/app/net.lutris.Lutris/data/lutris"
FLATPAK_LUTRIS_CONFIG = Path.home() / ".var/app/net.lutris.Lutris/config/lutris"
NATIVE_LUTRIS_DATA = Path.home() / ".local/share/lutris"
NATIVE_LUTRIS_CONFIG = Path.home() / ".config/lutris"

BRIDGE_DATA_DIR = Path.home() / ".local/share/lutris-bridge"
BRIDGE_CONFIG_DIR = Path.home() / ".config/lutris-bridge"
BRIDGE_SCRIPTS_DIR = BRIDGE_DATA_DIR / "scripts"


@dataclass
class LutrisInstall:
    """Detected Lutris installation paths."""

    install_type: str  # "flatpak" or "native"
    data_dir: Path  # Contains pga.db, runners/, banners/, icons/
    config_dir: Path  # Contains games/*.yml, runners/*.yml
    db_path: Path  # pga.db path
    runners_dir: Path  # runners/wine/ directory
    games_config_dir: Path  # games/ YAML config directory


@dataclass
class Config:
    """Resolved configuration for a lutris-bridge session."""

    steam_dir: Path
    steam_user_id: str
    shortcuts_vdf_path: Path
    grid_dir: Path
    lutris: LutrisInstall
    bridge_data_dir: Path = field(default=BRIDGE_DATA_DIR)
    bridge_scripts_dir: Path = field(default=BRIDGE_SCRIPTS_DIR)
    bridge_config_dir: Path = field(default=BRIDGE_CONFIG_DIR)
    steamgriddb_api_key: str | None = None


def detect_steam_dir() -> Path | None:
    """Find the Steam installation directory.

    Checks, in order: $STEAM_DIR env var, ~/.steam/steam, ~/.local/share/Steam.

    Returns:
        Path to Steam directory, or None if not found.
    """
    env_dir = os.environ.get("STEAM_DIR")
    if env_dir:
        p = Path(env_dir)
        if p.is_dir():
            logger.debug("Steam dir from $STEAM_DIR: %s", p)
            return p

    candidates = [
        Path.home() / ".steam" / "steam",
        Path.home() / ".local" / "share" / "Steam",
    ]
    for candidate in candidates:
        if candidate.is_dir():
            logger.debug("Steam dir found: %s", candidate)
            return candidate

    return None


def find_steam_user_ids(steam_dir: Path) -> list[str]:
    """Find all Steam user IDs from the userdata directory.

    Args:
        steam_dir: Path to the Steam installation directory.

    Returns:
        List of user ID strings (e.g., ["12345678", "87654321"]).
    """
    userdata = steam_dir / "userdata"
    if not userdata.is_dir():
        return []

    user_ids = []
    for entry in sorted(userdata.iterdir()):
        if entry.is_dir() and entry.name.isdigit():
            config_dir = entry / "config"
            if config_dir.is_dir():
                user_ids.append(entry.name)

    logger.debug("Found Steam user IDs: %s", user_ids)
    return user_ids


def get_most_recent_user(steam_dir: Path, user_ids: list[str]) -> str | None:
    """Determine the most recently active Steam user.

    Uses the modification time of the user's localconfig.vdf as a proxy.

    Args:
        steam_dir: Path to Steam installation.
        user_ids: List of user ID strings.

    Returns:
        The most recently active user ID, or None.
    """
    if not user_ids:
        return None
    if len(user_ids) == 1:
        return user_ids[0]

    best_id = None
    best_mtime = 0.0
    for uid in user_ids:
        localconfig = steam_dir / "userdata" / uid / "config" / "localconfig.vdf"
        if localconfig.exists():
            mtime = localconfig.stat().st_mtime
            if mtime > best_mtime:
                best_mtime = mtime
                best_id = uid

    return best_id or user_ids[0]


def detect_lutris_install() -> LutrisInstall | None:
    """Detect Lutris installation (Flatpak preferred over native).

    Returns:
        LutrisInstall with resolved paths, or None if not found.
    """
    # Prefer Flatpak (more common on Bazzite)
    if FLATPAK_LUTRIS_DATA.is_dir() and (FLATPAK_LUTRIS_DATA / "pga.db").exists():
        logger.info("Detected Flatpak Lutris installation")
        return LutrisInstall(
            install_type="flatpak",
            data_dir=FLATPAK_LUTRIS_DATA,
            config_dir=FLATPAK_LUTRIS_CONFIG,
            db_path=FLATPAK_LUTRIS_DATA / "pga.db",
            runners_dir=FLATPAK_LUTRIS_DATA / "runners",
            games_config_dir=FLATPAK_LUTRIS_CONFIG / "games",
        )

    if NATIVE_LUTRIS_DATA.is_dir() and (NATIVE_LUTRIS_DATA / "pga.db").exists():
        logger.info("Detected native Lutris installation")
        return LutrisInstall(
            install_type="native",
            data_dir=NATIVE_LUTRIS_DATA,
            config_dir=NATIVE_LUTRIS_CONFIG,
            db_path=NATIVE_LUTRIS_DATA / "pga.db",
            runners_dir=NATIVE_LUTRIS_DATA / "runners",
            games_config_dir=NATIVE_LUTRIS_CONFIG / "games",
        )

    return None


def shortcuts_vdf_path(steam_dir: Path, user_id: str) -> Path:
    """Get the path to shortcuts.vdf for a given Steam user."""
    return steam_dir / "userdata" / user_id / "config" / "shortcuts.vdf"


def steam_grid_dir(steam_dir: Path, user_id: str) -> Path:
    """Get the path to the grid artwork directory for a given Steam user."""
    return steam_dir / "userdata" / user_id / "config" / "grid"


def ensure_working_dirs() -> None:
    """Create lutris-bridge working directories if they don't exist."""
    BRIDGE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    BRIDGE_SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    BRIDGE_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    logger.debug("Working directories ensured at %s", BRIDGE_DATA_DIR)


def build_config(
    steam_user: str | None = None,
    steamgriddb_api_key: str | None = None,
) -> Config:
    """Build a fully resolved Config by auto-detecting paths.

    Args:
        steam_user: Override Steam user ID. If None, uses most recent.
        steamgriddb_api_key: SteamGridDB API key for artwork fetching.

    Returns:
        Resolved Config object.

    Raises:
        RuntimeError: If Steam or Lutris cannot be found.
    """
    steam_dir = detect_steam_dir()
    if not steam_dir:
        raise RuntimeError(
            "Steam installation not found. Set $STEAM_DIR or install Steam."
        )

    user_ids = find_steam_user_ids(steam_dir)
    if not user_ids:
        raise RuntimeError(
            f"No Steam user profiles found in {steam_dir / 'userdata'}"
        )

    if steam_user:
        if steam_user not in user_ids:
            raise RuntimeError(
                f"Steam user '{steam_user}' not found. Available: {user_ids}"
            )
        user_id = steam_user
    else:
        user_id = get_most_recent_user(steam_dir, user_ids)

    lutris = detect_lutris_install()
    if not lutris:
        raise RuntimeError(
            "Lutris installation not found. Install Lutris (native or Flatpak)."
        )

    ensure_working_dirs()

    vdf_path = shortcuts_vdf_path(steam_dir, user_id)
    grid = steam_grid_dir(steam_dir, user_id)
    grid.mkdir(parents=True, exist_ok=True)

    # Try loading API key from config file if not provided
    api_key = steamgriddb_api_key
    if not api_key:
        api_key = _load_api_key_from_config()

    return Config(
        steam_dir=steam_dir,
        steam_user_id=user_id,
        shortcuts_vdf_path=vdf_path,
        grid_dir=grid,
        lutris=lutris,
        steamgriddb_api_key=api_key,
    )


def _load_api_key_from_config() -> str | None:
    """Try to load SteamGridDB API key from config file."""
    config_file = BRIDGE_CONFIG_DIR / "config.toml"
    if not config_file.exists():
        return None

    try:
        # Simple TOML parsing for just the API key — avoid extra dependency
        for line in config_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("steamgriddb_api_key"):
                _, _, value = line.partition("=")
                return value.strip().strip('"').strip("'")
    except Exception:
        logger.warning("Failed to read config file: %s", config_file, exc_info=True)

    return None

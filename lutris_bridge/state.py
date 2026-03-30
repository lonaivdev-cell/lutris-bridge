"""State tracking for lutris-bridge.

Persists information about managed games between sync runs to support
incremental updates and orphan removal.
"""

import json
import logging
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_STATE_PATH = Path.home() / ".local/share/lutris-bridge/state.json"


@dataclass
class ManagedGame:
    """State for a single managed game."""

    appid: int
    script_path: str
    name: str
    runner: str
    last_synced: str = ""
    config_hash: str = ""


@dataclass
class BridgeState:
    """Persistent state for lutris-bridge."""

    version: int = 1
    steam_user_id: str = ""
    managed_games: dict[str, ManagedGame] = field(default_factory=dict)


def load_state(path: Path = DEFAULT_STATE_PATH) -> BridgeState:
    """Load state from disk.

    Args:
        path: Path to state.json.

    Returns:
        BridgeState, or a fresh state if file doesn't exist.
    """
    if not path.exists():
        logger.debug("No state file found, starting fresh")
        return BridgeState()

    try:
        data = json.loads(path.read_text())
        state = BridgeState(
            version=data.get("version", 1),
            steam_user_id=data.get("steam_user_id", ""),
        )
        for slug, game_data in data.get("managed_games", {}).items():
            # Filter to only known fields to survive version upgrades
            known_fields = {f.name for f in ManagedGame.__dataclass_fields__.values()}
            filtered = {k: v for k, v in game_data.items() if k in known_fields}
            try:
                state.managed_games[slug] = ManagedGame(**filtered)
            except TypeError:
                logger.warning("Skipping malformed game entry: %s", slug)
        return state
    except Exception:
        # Preserve corrupted state file for manual recovery
        backup = path.with_suffix(".json.corrupted")
        try:
            shutil.copy2(path, backup)
            logger.error(
                "State file corrupted, backed up to %s and starting fresh. "
                "Orphaned shortcuts may need manual removal.",
                backup,
            )
        except OSError:
            logger.error("State file corrupted and could not create backup, starting fresh")
        return BridgeState()


def save_state(state: BridgeState, path: Path = DEFAULT_STATE_PATH) -> None:
    """Save state to disk.

    Args:
        state: The BridgeState to persist.
        path: Path to write state.json.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": state.version,
        "steam_user_id": state.steam_user_id,
        "managed_games": {
            slug: asdict(game) for slug, game in state.managed_games.items()
        },
    }
    # Atomic write: write to temp file then rename to prevent corruption on crash
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(data, indent=2) + "\n")
    tmp_path.replace(path)
    logger.debug("Saved state to %s", path)


def now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()

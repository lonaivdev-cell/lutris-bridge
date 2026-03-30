"""Parse Lutris game YAML configs and runner configs.

Implements Lutris's config cascade: game config > runner config > defaults.
Extracts all settings needed to generate standalone launch scripts.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


@dataclass
class GameConfig:
    """Parsed and merged game configuration."""

    exe: str | None = None
    prefix: str | None = None  # WINEPREFIX
    args: str = ""
    working_dir: str | None = None
    wine_version: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    gamemode: bool = False
    dxvk: bool = True
    vkd3d: bool = False
    dxvk_version: str | None = None
    dll_overrides: str = ""
    disable_runtime: bool = False
    use_umu: bool = False


def load_yaml_config(path: Path) -> dict:
    """Load a YAML config file.

    Args:
        path: Path to the YAML file.

    Returns:
        Parsed dict, or empty dict if file doesn't exist or fails to parse.
    """
    if not path.exists():
        logger.debug("Config file not found: %s", path)
        return {}

    try:
        with open(path) as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        logger.warning("Failed to parse YAML config: %s", path, exc_info=True)
        return {}


def load_game_config(games_config_dir: Path, configpath: str) -> dict:
    """Load a Lutris game-specific YAML config.

    Args:
        games_config_dir: Directory containing game YAML files.
        configpath: The configpath value from pga.db (filename without .yml).

    Returns:
        Parsed config dict.
    """
    path = games_config_dir / f"{configpath}.yml"
    return load_yaml_config(path)


def load_runner_config(config_dir: Path, runner: str) -> dict:
    """Load a Lutris runner-level YAML config.

    Args:
        config_dir: Lutris config directory (e.g., ~/.config/lutris/).
        runner: Runner name (e.g., "wine", "linux").

    Returns:
        Parsed config dict.
    """
    path = config_dir / "runners" / f"{runner}.yml"
    return load_yaml_config(path)


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base, with override taking precedence.

    For nested dicts, merges recursively. For other types, override wins.
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _get_nested(data: dict, *keys, default=None):
    """Safely get a nested value from a dict."""
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
        if current is default:
            return default
    return current


def merge_configs(game_raw: dict, runner_raw: dict) -> GameConfig:
    """Merge game config over runner config and extract a GameConfig.

    Implements Lutris's cascade: game-level settings override runner defaults.

    Args:
        game_raw: Raw game YAML config dict.
        runner_raw: Raw runner YAML config dict.

    Returns:
        Merged GameConfig with all fields resolved.
    """
    merged = _deep_merge(runner_raw, game_raw)

    game_section = merged.get("game") or {}
    if not isinstance(game_section, dict):
        game_section = {}
    wine_section = merged.get("wine") or {}
    if not isinstance(wine_section, dict):
        wine_section = {}
    system_section = merged.get("system") or {}
    if not isinstance(system_section, dict):
        system_section = {}

    # Resolve working directory: explicit > exe's directory
    exe = game_section.get("exe")
    working_dir = game_section.get("working_dir")
    if not working_dir and exe:
        working_dir = str(Path(exe).parent)

    # Environment variables from system.env
    env = {}
    raw_env = system_section.get("env", {})
    if isinstance(raw_env, dict):
        env = {str(k): str(v) for k, v in raw_env.items()}

    # Detect umu-launcher usage
    use_umu = bool(wine_section.get("umu"))

    return GameConfig(
        exe=exe,
        prefix=game_section.get("prefix"),
        args=str(game_section.get("args", "") or ""),
        working_dir=working_dir,
        wine_version=wine_section.get("version"),
        env=env,
        gamemode=bool(system_section.get("gamemode")),
        dxvk=bool(wine_section.get("dxvk", True)),
        vkd3d=bool(wine_section.get("vkd3d", False)),
        dxvk_version=wine_section.get("dxvk_version"),
        dll_overrides=str(wine_section.get("dll_overrides", "") or ""),
        disable_runtime=bool(system_section.get("disable_runtime", False)),
        use_umu=use_umu,
    )


def parse_game_config(
    games_config_dir: Path,
    config_dir: Path,
    configpath: str,
    runner: str,
) -> GameConfig:
    """Load and merge game + runner configs into a GameConfig.

    This is the main entry point for config parsing.

    Args:
        games_config_dir: Directory containing game YAML files.
        config_dir: Lutris config directory (for runner configs).
        configpath: The configpath from pga.db.
        runner: The runner name (e.g., "wine").

    Returns:
        Fully resolved GameConfig.
    """
    game_raw = load_game_config(games_config_dir, configpath)
    runner_raw = load_runner_config(config_dir, runner)
    return merge_configs(game_raw, runner_raw)

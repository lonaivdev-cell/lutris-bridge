"""SteamGridDB artwork fetching for non-Steam shortcuts.

Downloads grid, hero, logo, and icon images from SteamGridDB and saves
them to Steam's grid directory with the correct naming convention.
Falls back to Lutris banners/icons if SGDB is unavailable.
"""

import logging
import shutil
import time
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

SGDB_BASE_URL = "https://www.steamgriddb.com/api/v2"

# Artwork types and their filename suffixes
ARTWORK_TYPES = {
    "grid_portrait": {"endpoint": "grids", "params": {"dimensions": "600x900"}, "suffix": "p.png"},
    "grid_landscape": {"endpoint": "grids", "params": {"dimensions": "920x430"}, "suffix": ".png"},
    "hero": {"endpoint": "heroes", "params": {}, "suffix": "_hero.png"},
    "logo": {"endpoint": "logos", "params": {}, "suffix": "_logo.png"},
    "icon": {"endpoint": "icons", "params": {}, "suffix": "_icon.ico"},
}


def _sgdb_request(
    endpoint: str,
    api_key: str,
    params: dict | None = None,
    max_retries: int = 3,
) -> dict | None:
    """Make a SteamGridDB API request with retry logic.

    Returns:
        Parsed JSON response, or None on failure.
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    url = f"{SGDB_BASE_URL}/{endpoint}"

    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=15)

            if resp.status_code == 429:
                wait = min(2 ** (attempt + 1), 30)
                logger.warning("Rate limited by SteamGridDB, waiting %ds", wait)
                time.sleep(wait)
                continue

            if resp.status_code == 404:
                return None

            resp.raise_for_status()
            return resp.json()

        except requests.RequestException:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                logger.warning("SteamGridDB request failed: %s", endpoint, exc_info=True)

    return None


def search_game(game_name: str, api_key: str) -> int | None:
    """Search SteamGridDB for a game by name.

    Args:
        game_name: The game's display name.
        api_key: SteamGridDB API key.

    Returns:
        SteamGridDB game ID, or None if not found.
    """
    data = _sgdb_request(f"search/autocomplete/{game_name}", api_key)
    if not data or not data.get("data"):
        logger.debug("No SteamGridDB results for '%s'", game_name)
        return None

    sgdb_id = data["data"][0]["id"]
    logger.debug("SteamGridDB match for '%s': id=%d", game_name, sgdb_id)
    return sgdb_id


def _download_file(url: str, dest: Path, timeout: int = 30) -> bool:
    """Download a file from URL to dest path.

    Returns:
        True if successful.
    """
    try:
        resp = requests.get(url, timeout=timeout, stream=True)
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except requests.RequestException:
        logger.warning("Failed to download %s", url, exc_info=True)
        return False


def fetch_artwork(
    game_name: str,
    grid_id: int,
    grid_dir: Path,
    api_key: str | None = None,
    lutris_data_dir: Path | None = None,
    slug: str = "",
    force: bool = False,
) -> dict[str, bool]:
    """Fetch artwork for a game from SteamGridDB.

    Downloads all artwork types (grid portrait, grid landscape, hero, logo, icon)
    and saves them to the Steam grid directory.

    Args:
        game_name: The game's display name for searching.
        grid_id: The Steam grid ID for filename generation.
        grid_dir: Steam's grid artwork directory.
        api_key: SteamGridDB API key. If None, skips SGDB and tries Lutris fallback.
        lutris_data_dir: Lutris data directory for fallback artwork.
        slug: Lutris game slug for fallback asset matching.
        force: Re-download even if files exist.

    Returns:
        Dict mapping artwork type to success boolean.
    """
    results = {}
    grid_dir.mkdir(parents=True, exist_ok=True)

    # Check what already exists (skip if cached)
    if not force:
        all_exist = True
        for art_type, info in ARTWORK_TYPES.items():
            dest = grid_dir / f"{grid_id}{info['suffix']}"
            if not dest.exists():
                all_exist = False
                break
        if all_exist:
            logger.debug("All artwork already cached for grid_id=%d", grid_id)
            return {t: True for t in ARTWORK_TYPES}

    # Try SteamGridDB
    if api_key:
        sgdb_id = search_game(game_name, api_key)
        if sgdb_id:
            for art_type, info in ARTWORK_TYPES.items():
                dest = grid_dir / f"{grid_id}{info['suffix']}"
                if dest.exists() and not force:
                    results[art_type] = True
                    continue

                data = _sgdb_request(
                    f"{info['endpoint']}/game/{sgdb_id}",
                    api_key,
                    params=info["params"],
                )
                if data and data.get("data"):
                    image_url = data["data"][0].get("url")
                    if image_url:
                        results[art_type] = _download_file(image_url, dest)
                        continue

                results[art_type] = False
        else:
            results = {t: False for t in ARTWORK_TYPES}
    else:
        logger.debug("No SteamGridDB API key, skipping artwork fetch")
        results = {t: False for t in ARTWORK_TYPES}

    # Fallback: try Lutris banners/icons
    if lutris_data_dir and not all(results.values()):
        _try_lutris_fallback(game_name, grid_id, grid_dir, lutris_data_dir, results, slug=slug)

    fetched = sum(1 for v in results.values() if v)
    total = len(ARTWORK_TYPES)
    if fetched > 0:
        logger.info("Fetched %d/%d artwork for '%s'", fetched, total, game_name)
    else:
        logger.debug("No artwork found for '%s'", game_name)

    return results


def _try_lutris_fallback(
    game_name: str,
    grid_id: int,
    grid_dir: Path,
    lutris_data_dir: Path,
    results: dict[str, bool],
    slug: str = "",
) -> None:
    """Try to use Lutris banners/icons as fallback artwork.

    Lutris stores banners as {slug}.jpg in banners/ and icons as
    {slug}.png in icons/. We try slug-based matching first, then
    fall back to name-based matching.
    """
    banners_dir = lutris_data_dir / "banners"
    icons_dir = lutris_data_dir / "icons"

    if not results.get("grid_landscape", False) and banners_dir.is_dir():
        banner = _find_lutris_asset(banners_dir, slug, game_name, (".jpg", ".png"))
        if banner:
            dest = grid_dir / f"{grid_id}.png"
            if not dest.exists():
                try:
                    shutil.copy2(banner, dest)
                    results["grid_landscape"] = True
                    logger.debug("Used Lutris banner as fallback: %s", banner)
                except OSError:
                    pass

    if not results.get("icon", False) and icons_dir.is_dir():
        icon = _find_lutris_asset(icons_dir, slug, game_name, (".png", ".ico"))
        if icon:
            dest = grid_dir / f"{grid_id}_icon.ico"
            if not dest.exists():
                try:
                    shutil.copy2(icon, dest)
                    results["icon"] = True
                    logger.debug("Used Lutris icon as fallback: %s", icon)
                except OSError:
                    pass


def _find_lutris_asset(
    directory: Path, slug: str, game_name: str, extensions: tuple[str, ...]
) -> Path | None:
    """Find a Lutris asset file by slug or name.

    Tries exact slug match first, then falls back to name-based search.
    """
    # Try exact slug match first (most reliable)
    if slug:
        for ext in extensions:
            candidate = directory / f"{slug}{ext}"
            if candidate.exists():
                return candidate

    # Fall back to name-based search (normalized)
    normalized_name = game_name.lower().replace(" ", "-").replace(":", "")
    for ext in extensions:
        for f in sorted(directory.iterdir()):
            if f.suffix == ext and normalized_name in f.stem.lower():
                return f

    return None

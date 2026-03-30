"""Read Lutris game database (pga.db).

Opens the SQLite database in read-only mode to avoid locking Lutris,
and queries for installed, non-hidden games.
"""

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class LutrisGame:
    """A game entry from the Lutris database."""

    id: int
    slug: str
    name: str
    runner: str
    platform: str | None
    directory: str | None
    configpath: str


def discover_games(db_path: Path) -> list[LutrisGame]:
    """Query Lutris pga.db for installed, non-hidden games.

    Opens the database in read-only mode to avoid interfering with Lutris.

    Args:
        db_path: Path to pga.db.

    Returns:
        List of LutrisGame objects for installed games.

    Raises:
        FileNotFoundError: If db_path doesn't exist.
        sqlite3.Error: On database errors.
    """
    if not db_path.exists():
        raise FileNotFoundError(f"Lutris database not found: {db_path}")

    uri = f"file:{db_path}?mode=ro"
    games = []

    with sqlite3.connect(uri, uri=True) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Check which columns exist (older Lutris versions may differ)
        cursor.execute("PRAGMA table_info(games)")
        columns = {row["name"] for row in cursor.fetchall()}

        has_hidden = "hidden" in columns
        has_platform = "platform" in columns

        query = "SELECT id, slug, name, runner, directory, configpath"
        if has_platform:
            query += ", platform"
        query += " FROM games WHERE installed = 1"
        if has_hidden:
            query += " AND (hidden = 0 OR hidden IS NULL)"

        cursor.execute(query)
        for row in cursor.fetchall():
            # Skip games with missing required fields
            if not row["slug"] or not row["runner"] or not row["configpath"]:
                logger.warning(
                    "Skipping game id=%d: missing slug, runner, or configpath",
                    row["id"],
                )
                continue

            games.append(
                LutrisGame(
                    id=row["id"],
                    slug=row["slug"],
                    name=row["name"] or row["slug"],
                    runner=row["runner"],
                    platform=row["platform"] if has_platform else None,
                    directory=row["directory"],
                    configpath=row["configpath"],
                )
            )

    logger.info("Discovered %d installed Lutris games", len(games))
    return games

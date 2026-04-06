"""Helper script to create a test pga.db fixture."""

import sqlite3
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def create_test_db():
    FIXTURES_DIR.mkdir(exist_ok=True)
    db_path = FIXTURES_DIR / "pga.db"
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE games (
            id INTEGER PRIMARY KEY,
            slug TEXT,
            name TEXT,
            runner TEXT,
            platform TEXT,
            directory TEXT,
            configpath TEXT,
            installed INTEGER DEFAULT 0,
            hidden INTEGER DEFAULT 0
        )
    """)
    games = [
        (1, "valheim", "Valheim", "wine", "Linux", "/games/valheim", "valheim-12345", 1, 0),
        (2, "celeste", "Celeste", "linux", "Linux", "/games/celeste", "celeste-67890", 1, 0),
        (3, "hidden-game", "Hidden Game", "wine", "Linux", "/games/hidden", "hidden-11111", 1, 1),
        (4, "uninstalled", "Uninstalled Game", "wine", "Linux", "/games/uninst", "uninst-22222", 0, 0),
        (5, "dosbox-game", "DOS Game", "dosbox", "DOS", "/games/dos", "dos-33333", 1, 0),
        (6, "no-config", "No Config", "wine", "Linux", "/games/noconfig", None, 1, 0),
    ]
    conn.executemany(
        "INSERT INTO games (id, slug, name, runner, platform, directory, configpath, installed, hidden) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        games,
    )
    conn.commit()
    conn.close()
    print(f"Created test DB at {db_path}")


if __name__ == "__main__":
    create_test_db()

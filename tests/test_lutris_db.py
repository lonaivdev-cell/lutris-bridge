"""Tests for Lutris database reader."""

from pathlib import Path

import pytest

from lutris_bridge.lutris_db import LutrisGame, discover_games

FIXTURES_DIR = Path(__file__).parent / "fixtures"
TEST_DB = FIXTURES_DIR / "pga.db"


def test_discover_games_returns_installed_only():
    """Only installed=1 games should be returned."""
    games = discover_games(TEST_DB)
    slugs = {g.slug for g in games}
    assert "valheim" in slugs
    assert "celeste" in slugs
    assert "uninstalled" not in slugs


def test_discover_games_excludes_hidden():
    """Hidden games should be excluded."""
    games = discover_games(TEST_DB)
    slugs = {g.slug for g in games}
    assert "hidden-game" not in slugs


def test_discover_games_skips_missing_configpath():
    """Games without a configpath should be skipped."""
    games = discover_games(TEST_DB)
    slugs = {g.slug for g in games}
    assert "no-config" not in slugs


def test_discover_games_returns_dataclass():
    """Results should be LutrisGame dataclass instances."""
    games = discover_games(TEST_DB)
    assert len(games) > 0
    game = games[0]
    assert isinstance(game, LutrisGame)
    assert isinstance(game.id, int)
    assert isinstance(game.slug, str)


def test_discover_games_count():
    """Should return exactly 3 games (valheim, celeste, dos-game)."""
    games = discover_games(TEST_DB)
    assert len(games) == 3


def test_discover_games_preserves_runner():
    """Runner field should be preserved correctly."""
    games = discover_games(TEST_DB)
    by_slug = {g.slug: g for g in games}
    assert by_slug["valheim"].runner == "wine"
    assert by_slug["celeste"].runner == "linux"
    assert by_slug["dosbox-game"].runner == "dosbox"


def test_discover_games_nonexistent_db():
    """Should raise FileNotFoundError for missing database."""
    with pytest.raises(FileNotFoundError):
        discover_games(Path("/nonexistent/pga.db"))

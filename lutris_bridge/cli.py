"""Command-line interface for lutris-bridge."""

import argparse
import logging
import sys

from lutris_bridge import __version__


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
    )


def cmd_sync(args: argparse.Namespace) -> int:
    from lutris_bridge.config import build_config
    from lutris_bridge.sync import sync

    config = build_config(
        steam_user=args.steam_user,
        steamgriddb_api_key=args.steamgriddb_key,
    )

    prefix = "[DRY RUN] " if args.dry_run else ""
    logging.info("%sSyncing Lutris games to Steam shortcuts...", prefix)

    counts = sync(config, dry_run=args.dry_run, force=args.force)

    logging.info(
        "%sAdded: %d, Updated: %d, Removed: %d, Total managed: %d",
        prefix,
        counts["added"],
        counts["updated"],
        counts["removed"],
        counts["total"],
    )

    if not args.dry_run and (counts["added"] or counts["removed"] or counts["updated"]):
        logging.info("Restart Steam for changes to take effect.")

    return 0


def cmd_list(args: argparse.Namespace) -> int:
    from lutris_bridge.config import build_config
    from lutris_bridge.lutris_db import discover_games
    from lutris_bridge.state import load_state

    config = build_config(steam_user=args.steam_user)
    games = discover_games(config.lutris.db_path)
    state = load_state()

    if not games:
        print("No installed Lutris games found.")
        return 0

    print(f"{'Name':<40} {'Runner':<10} {'Status':<10}")
    print("-" * 60)

    for game in sorted(games, key=lambda g: g.name.lower()):
        status = "synced" if game.slug in state.managed_games else "not synced"
        print(f"{game.name:<40} {game.runner:<10} {status:<10}")

    print(f"\nTotal: {len(games)} games")
    return 0


def cmd_clean(args: argparse.Namespace) -> int:
    from lutris_bridge.config import build_config
    from lutris_bridge.sync import clean

    config = build_config(steam_user=args.steam_user)
    removed = clean(config)
    logging.info("Cleaned %d managed shortcuts.", removed)

    if removed:
        logging.info("Restart Steam for changes to take effect.")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    from lutris_bridge.config import (
        detect_lutris_install,
        detect_steam_dir,
        find_steam_user_ids,
    )
    from lutris_bridge.state import load_state

    steam_dir = detect_steam_dir()
    lutris = detect_lutris_install()
    state = load_state()

    print("=== lutris-bridge status ===\n")

    if steam_dir:
        user_ids = find_steam_user_ids(steam_dir)
        print(f"Steam directory:  {steam_dir}")
        print(f"Steam users:      {', '.join(user_ids) if user_ids else 'none found'}")
    else:
        print("Steam directory:  NOT FOUND")

    print()
    if lutris:
        print(f"Lutris install:   {lutris.install_type}")
        print(f"Lutris data:      {lutris.data_dir}")
        print(f"Lutris config:    {lutris.config_dir}")
        print(f"Lutris DB:        {lutris.db_path}")
    else:
        print("Lutris install:   NOT FOUND")

    print()
    print(f"Managed games:    {len(state.managed_games)}")
    if state.managed_games:
        for slug, game in sorted(state.managed_games.items()):
            print(f"  - {game.name} ({game.runner}) [appid={game.appid}]")

    return 0


def cmd_generate_script(args: argparse.Namespace) -> int:
    from lutris_bridge.config import build_config
    from lutris_bridge.lutris_config import parse_game_config
    from lutris_bridge.lutris_db import discover_games
    from lutris_bridge.script_gen import generate_launch_script

    config = build_config(steam_user=args.steam_user)
    games = discover_games(config.lutris.db_path)

    game = next((g for g in games if g.slug == args.slug), None)
    if not game:
        logging.error("Game with slug '%s' not found.", args.slug)
        available = [g.slug for g in games]
        if available:
            logging.info("Available slugs: %s", ", ".join(sorted(available)))
        return 1

    game_config = parse_game_config(
        config.lutris.games_config_dir,
        config.lutris.config_dir,
        game.configpath,
        game.runner,
    )

    script_path = generate_launch_script(
        game, game_config, config.bridge_scripts_dir, config.lutris.runners_dir
    )

    logging.info("Generated script: %s", script_path)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lutris-bridge",
        description="Sync Lutris games to Steam as non-Steam shortcuts for Gaming Mode.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
    )
    parser.add_argument(
        "--steam-user", help="Steam user ID to target (default: most recent)"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # sync
    sync_parser = subparsers.add_parser("sync", help="Sync Lutris games to Steam shortcuts")
    sync_parser.add_argument("--dry-run", action="store_true", help="Show what would be done without writing")
    sync_parser.add_argument("--force", action="store_true", help="Force regenerate all scripts and shortcuts")
    sync_parser.add_argument("--steamgriddb-key", help="SteamGridDB API key for artwork")

    # list
    subparsers.add_parser("list", help="Show discovered Lutris games and sync status")

    # clean
    subparsers.add_parser("clean", help="Remove all lutris-bridge managed shortcuts and scripts")

    # status
    subparsers.add_parser("status", help="Show current state and detected paths")

    # generate-script
    gen_parser = subparsers.add_parser("generate-script", help="Generate launch script for a single game")
    gen_parser.add_argument("slug", help="Lutris game slug")

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    if not args.command:
        parser.print_help()
        return 1

    commands = {
        "sync": cmd_sync,
        "list": cmd_list,
        "clean": cmd_clean,
        "status": cmd_status,
        "generate-script": cmd_generate_script,
    }

    try:
        return commands[args.command](args)
    except RuntimeError as e:
        logging.error("%s", e)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())

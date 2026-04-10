"""Logging configuration for lutris-bridge.

Sets up dual-output logging:
- Console: clean, user-friendly (INFO+ by default, DEBUG with --verbose)
- File: detailed with timestamps, module, function, line (always DEBUG)

Log files are stored at ~/.local/share/lutris-bridge/logs/
with rotation to prevent disk fill.
"""

import logging
import platform
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from lutris_bridge import __version__

LOG_DIR = Path.home() / ".local/share/lutris-bridge" / "logs"
LOG_FILE = LOG_DIR / "lutris-bridge.log"

# File format: pipe-delimited columns for easy parsing.
# module:function:line maps directly to source code locations.
FILE_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s"
)
FILE_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Console format: clean for human eyes with short timestamps.
CONSOLE_FORMAT = "%(asctime)s %(levelname)s: %(message)s"
CONSOLE_DATE_FORMAT = "%H:%M:%S"

# Rotation: 2 MB per file, 3 backups = 8 MB total max.
MAX_BYTES = 2 * 1024 * 1024
BACKUP_COUNT = 3


def setup_logging(verbose: bool = False) -> Path:
    """Configure program-wide logging with console + file handlers.

    Args:
        verbose: If True, console shows DEBUG. File always logs DEBUG.

    Returns:
        Path to the active log file.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()

    # File handler: always DEBUG, full detail
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(FILE_FORMAT, datefmt=FILE_DATE_FORMAT))
    root.addHandler(file_handler)

    # Console handler: INFO (or DEBUG with --verbose)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    console_handler.setFormatter(
        logging.Formatter(CONSOLE_FORMAT, datefmt=CONSOLE_DATE_FORMAT)
    )
    root.addHandler(console_handler)

    return LOG_FILE


def log_session_header(argv: list[str] | None = None) -> None:
    """Write a session header block to the log file.

    Captures system context essential for troubleshooting:
    version, Python version, OS, command-line args, and working directory.
    """
    logger = logging.getLogger(__name__)
    logger.debug(
        "=== lutris-bridge session start ===\n"
        "  version:    %s\n"
        "  python:     %s\n"
        "  platform:   %s\n"
        "  argv:       %s\n"
        "  cwd:        %s\n"
        "  log_file:   %s\n"
        "===================================",
        __version__,
        sys.version.replace("\n", " "),
        platform.platform(),
        " ".join(argv) if argv else "(none)",
        Path.cwd(),
        LOG_FILE,
    )


def install_unhandled_exception_hook() -> None:
    """Replace sys.excepthook to capture unhandled exceptions in the log.

    Ensures unexpected crashes produce a full traceback in the log file.
    """
    logger = logging.getLogger("lutris_bridge")

    def _hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logger.critical(
            "Unhandled exception", exc_info=(exc_type, exc_value, exc_tb)
        )

    sys.excepthook = _hook

"""Windows 98 InstallShield-style sync wizard for lutris-bridge."""

import logging
import queue
import sys
import threading
import tkinter as tk
import tkinter.font
import tkinter.messagebox
import tkinter.scrolledtext
from pathlib import Path

from lutris_bridge import __version__

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Win98 Style Constants & Widget Factories
# ---------------------------------------------------------------------------

class Win98Style:
    """Windows 98 color palette, fonts, and widget factory methods."""

    # Main backgrounds
    BG = "#c0c0c0"
    BG_WHITE = "#ffffff"
    BG_DARK = "#808080"
    BG_LIGHT = "#dfdfdf"

    # Sidebar gradient endpoints
    SIDEBAR_TOP = "#0000aa"
    SIDEBAR_BOT = "#000044"

    # Buttons
    BTN_FACE = "#c0c0c0"

    # Progress bar
    PROGRESS_FILL = "#000080"

    # Highlight / selection
    SELECT_BG = "#000080"
    SELECT_FG = "#ffffff"

    # Status
    COLOR_OK = "#008000"
    COLOR_WARN = "#808000"
    COLOR_ERR = "#cc0000"
    COLOR_NEW = "#0000aa"

    # Fonts — resolved at runtime by _resolve_fonts()
    FONT_MAIN: tuple = ("Helvetica", 9)
    FONT_BOLD: tuple = ("Helvetica", 9, "bold")
    FONT_TITLE: tuple = ("Helvetica", 13, "bold")
    FONT_SIDEBAR: tuple = ("Helvetica", 16, "bold")
    FONT_SIDEBAR_SUB: tuple = ("Helvetica", 9)
    FONT_SMALL: tuple = ("Helvetica", 8)
    FONT_MONO: tuple = ("Courier", 9)

    _fonts_resolved = False

    @classmethod
    def resolve_fonts(cls) -> None:
        """Pick the best available font family for the Win98 look."""
        if cls._fonts_resolved:
            return
        families = set(tkinter.font.families())
        # Preference order: Tahoma is the authentic Win98 font,
        # Liberation Sans is its open clone, then DejaVu Sans.
        for candidate in ("Tahoma", "Liberation Sans", "DejaVu Sans", "Helvetica"):
            if candidate in families:
                base = candidate
                break
        else:
            base = "Helvetica"

        for mono_candidate in ("Consolas", "Liberation Mono", "DejaVu Sans Mono", "Courier"):
            if mono_candidate in families:
                mono = mono_candidate
                break
        else:
            mono = "Courier"

        cls.FONT_MAIN = (base, 9)
        cls.FONT_BOLD = (base, 9, "bold")
        cls.FONT_TITLE = (base, 13, "bold")
        cls.FONT_SIDEBAR = (base, 16, "bold")
        cls.FONT_SIDEBAR_SUB = (base, 9)
        cls.FONT_SMALL = (base, 8)
        cls.FONT_MONO = (mono, 9)
        cls._fonts_resolved = True

    @staticmethod
    def etched_line(parent: tk.Widget) -> tk.Frame:
        """Create a Win98-style etched horizontal separator."""
        frame = tk.Frame(parent, bg=Win98Style.BG)
        tk.Frame(frame, height=1, bg=Win98Style.BG_DARK).pack(fill="x")
        tk.Frame(frame, height=1, bg=Win98Style.BG_LIGHT).pack(fill="x")
        return frame

    @staticmethod
    def sunken_frame(parent: tk.Widget, **kw) -> tk.Frame:
        """Create a Win98-style sunken content frame."""
        return tk.Frame(parent, relief="sunken", bd=2, bg=Win98Style.BG_WHITE, **kw)

    @staticmethod
    def button(parent: tk.Widget, text: str, command=None, width: int = 10) -> tk.Button:
        """Create a Win98-style raised button."""
        return tk.Button(
            parent,
            text=text,
            command=command,
            font=Win98Style.FONT_MAIN,
            bg=Win98Style.BTN_FACE,
            activebackground=Win98Style.BG_LIGHT,
            relief="raised",
            bd=2,
            width=width,
            cursor="arrow",
        )

    @staticmethod
    def label(parent: tk.Widget, text: str = "", **kw) -> tk.Label:
        """Create a label with Win98 background and font."""
        defaults = dict(bg=Win98Style.BG, font=Win98Style.FONT_MAIN, anchor="w")
        defaults.update(kw)
        return tk.Label(parent, text=text, **defaults)

    @staticmethod
    def bold_label(parent: tk.Widget, text: str = "", **kw) -> tk.Label:
        """Create a bold label."""
        defaults = dict(bg=Win98Style.BG, font=Win98Style.FONT_BOLD, anchor="w")
        defaults.update(kw)
        return tk.Label(parent, text=text, **defaults)


# ---------------------------------------------------------------------------
# Queue-based Log Handler
# ---------------------------------------------------------------------------

class QueueLogHandler(logging.Handler):
    """Logging handler that pushes formatted records to a queue."""

    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.log_queue.put(("log", record.levelno, msg))
        except Exception:
            self.handleError(record)


# ---------------------------------------------------------------------------
# Chunked Progress Bar (Win98 InstallShield style)
# ---------------------------------------------------------------------------

class ChunkedProgressBar(tk.Canvas):
    """Segmented progress bar matching the classic InstallShield look."""

    def __init__(self, parent: tk.Widget, width: int = 400, height: int = 22,
                 num_chunks: int = 25):
        super().__init__(
            parent, width=width, height=height,
            bg=Win98Style.BG_WHITE, relief="sunken", bd=2,
            highlightthickness=0,
        )
        self.num_chunks = num_chunks
        self._fraction = 0.0
        self.bind("<Configure>", lambda _e: self._draw())

    def set_progress(self, fraction: float) -> None:
        self._fraction = max(0.0, min(1.0, fraction))
        self._draw()

    def _draw(self) -> None:
        self.delete("chunks")
        w = self.winfo_width() - 4
        h = self.winfo_height() - 4
        if w <= 0 or h <= 0:
            return
        filled = int(self._fraction * self.num_chunks)
        chunk_w = w / self.num_chunks
        gap = 2
        for i in range(filled):
            x0 = 2 + i * chunk_w + gap / 2
            x1 = 2 + (i + 1) * chunk_w - gap / 2
            self.create_rectangle(
                x0, 2, x1, h + 2,
                fill=Win98Style.PROGRESS_FILL, outline="", tags="chunks",
            )


# ---------------------------------------------------------------------------
# Wizard Page Base
# ---------------------------------------------------------------------------

class WizardPage(tk.Frame):
    """Base class for wizard pages."""

    next_page: str = ""

    def __init__(self, wizard: "SyncWizard"):
        super().__init__(wizard.content_frame, bg=Win98Style.BG)
        self.wizard = wizard

    def on_show(self) -> None:
        """Called when the page becomes visible."""

    def validate(self) -> bool:
        """Return False to block navigation away from this page."""
        return True

    def get_next_page(self) -> str:
        return self.next_page


# ---------------------------------------------------------------------------
# Page 1: Welcome
# ---------------------------------------------------------------------------

class WelcomePage(WizardPage):
    next_page = "detection"

    def __init__(self, wizard: "SyncWizard"):
        super().__init__(wizard)

        Win98Style.label(
            self, text="Welcome to the lutris-bridge\nSync Wizard",
            font=Win98Style.FONT_TITLE, justify="left",
        ).pack(anchor="nw", padx=20, pady=(24, 8))

        Win98Style.etched_line(self).pack(fill="x", padx=20, pady=(0, 12))

        body = (
            "This wizard will sync your Lutris-installed games into "
            "Steam as non-Steam shortcuts for Gaming Mode.\n\n"
            "The wizard will:\n\n"
            "    \u2022  Detect your Steam and Lutris installations\n"
            "    \u2022  Show you which games are available\n"
            "    \u2022  Let you choose which games to sync\n"
            "    \u2022  Generate launch scripts and Steam shortcuts\n"
            "    \u2022  Fetch artwork from SteamGridDB (optional)\n\n"
            "Click Next to continue, or Cancel to exit."
        )
        Win98Style.label(
            self, text=body, justify="left", wraplength=400,
        ).pack(anchor="nw", padx=20, pady=(0, 12))

        # Version at bottom
        Win98Style.label(
            self,
            text=f"lutris-bridge v{__version__}",
            font=Win98Style.FONT_SMALL,
            fg="#808080",
        ).pack(side="bottom", anchor="sw", padx=20, pady=(0, 8))

    def on_show(self) -> None:
        self.wizard.update_buttons(back=False, next=True, cancel=True, next_text="Next >")


# ---------------------------------------------------------------------------
# Page 2: System Detection
# ---------------------------------------------------------------------------

class DetectionPage(WizardPage):
    next_page = "gamelist"

    def __init__(self, wizard: "SyncWizard"):
        super().__init__(wizard)

        Win98Style.label(
            self, text="System Detection", font=Win98Style.FONT_TITLE,
        ).pack(anchor="nw", padx=20, pady=(24, 8))

        Win98Style.etched_line(self).pack(fill="x", padx=20, pady=(0, 12))

        Win98Style.label(
            self, text="Detecting Steam and Lutris installations...",
        ).pack(anchor="nw", padx=20, pady=(0, 12))

        # Detection results grid
        self.results_frame = Win98Style.sunken_frame(self)
        self.results_frame.pack(fill="both", padx=20, pady=(0, 8), expand=True)

        self.status_label = Win98Style.label(self, text="", fg="#808080")
        self.status_label.pack(anchor="nw", padx=20, pady=(4, 8))

        self._result_rows: list[tuple[tk.Label, tk.Label]] = []
        self._can_proceed = False

    def on_show(self) -> None:
        self.wizard.update_buttons(back=True, next=False, cancel=True)
        self.after(150, self._run_detection)

    def _add_row(self, key: str, value: str, ok: bool) -> None:
        row = len(self._result_rows)
        k_label = tk.Label(
            self.results_frame, text=key, font=Win98Style.FONT_BOLD,
            bg=Win98Style.BG_WHITE, anchor="w",
        )
        v_label = tk.Label(
            self.results_frame, text=value,
            font=Win98Style.FONT_MAIN, bg=Win98Style.BG_WHITE, anchor="w",
            fg=Win98Style.COLOR_OK if ok else Win98Style.COLOR_ERR,
        )
        k_label.grid(row=row, column=0, sticky="w", padx=(12, 8), pady=4)
        v_label.grid(row=row, column=1, sticky="w", padx=(0, 12), pady=4)
        self._result_rows.append((k_label, v_label))

    def _run_detection(self) -> None:
        from lutris_bridge.config import (
            detect_lutris_install,
            detect_steam_dir,
            find_steam_user_ids,
            get_most_recent_user,
        )
        from lutris_bridge.state import load_state

        # Clear previous results
        for k, v in self._result_rows:
            k.destroy()
            v.destroy()
        self._result_rows.clear()

        steam_dir = detect_steam_dir()
        lutris = detect_lutris_install()
        user_ids = find_steam_user_ids(steam_dir) if steam_dir else []
        state = load_state()

        # Store on wizard for later pages
        self.wizard.detected_steam_dir = steam_dir
        self.wizard.detected_lutris = lutris
        self.wizard.detected_user_ids = user_ids
        self.wizard.detected_state = state

        self._add_row("Steam directory:", str(steam_dir) if steam_dir else "NOT FOUND", bool(steam_dir))
        self._add_row(
            "Steam users:",
            ", ".join(user_ids) if user_ids else "none found",
            bool(user_ids),
        )
        self._add_row(
            "Lutris install:",
            lutris.install_type if lutris else "NOT FOUND",
            bool(lutris),
        )
        if lutris:
            self._add_row("Lutris database:", str(lutris.db_path), lutris.db_path.exists())

        # Discover games
        games = []
        if lutris:
            try:
                from lutris_bridge.lutris_db import discover_games
                games = discover_games(lutris.db_path)
            except Exception as exc:
                logger.error("Failed to read Lutris DB: %s", exc, exc_info=True)

        self.wizard.games = games
        self._add_row("Games found:", str(len(games)), len(games) > 0)
        self._add_row("Currently managed:", str(len(state.managed_games)), True)

        self.results_frame.columnconfigure(1, weight=1)

        self._can_proceed = bool(steam_dir and lutris and user_ids and games)
        if self._can_proceed:
            self.status_label.config(text="All systems detected. Click Next to continue.", fg=Win98Style.COLOR_OK)
            # Pre-select most recent user
            self.wizard.selected_user_id = get_most_recent_user(steam_dir, user_ids) or user_ids[0]
        elif not games and lutris:
            self.status_label.config(text="No installed Lutris games found.", fg=Win98Style.COLOR_WARN)
        else:
            self.status_label.config(text="Required components missing. Cannot continue.", fg=Win98Style.COLOR_ERR)

        self.wizard.update_buttons(back=True, next=self._can_proceed, cancel=True)

    def validate(self) -> bool:
        return self._can_proceed


# ---------------------------------------------------------------------------
# Page 3: Game List
# ---------------------------------------------------------------------------

class GameListPage(WizardPage):
    next_page = "options"

    def __init__(self, wizard: "SyncWizard"):
        super().__init__(wizard)
        self._built = False
        self.game_vars: dict[str, tk.BooleanVar] = {}

        Win98Style.label(
            self, text="Select Games to Sync", font=Win98Style.FONT_TITLE,
        ).pack(anchor="nw", padx=20, pady=(24, 8))

        Win98Style.etched_line(self).pack(fill="x", padx=20, pady=(0, 6))

        # Select All / Deselect All buttons
        btn_row = tk.Frame(self, bg=Win98Style.BG)
        btn_row.pack(fill="x", padx=20, pady=(0, 6))
        Win98Style.label(btn_row, text="Choose which games to sync to Steam:").pack(side="left")
        Win98Style.button(btn_row, "Deselect All", self._deselect_all, width=9).pack(side="right", padx=(4, 0))
        Win98Style.button(btn_row, "Select All", self._select_all, width=8).pack(side="right")

        # Scrollable game list container
        list_border = tk.Frame(self, relief="sunken", bd=2, bg=Win98Style.BG_WHITE)
        list_border.pack(fill="both", expand=True, padx=20, pady=(0, 8))

        self.canvas = tk.Canvas(list_border, bg=Win98Style.BG_WHITE, highlightthickness=0)
        self.scrollbar = tk.Scrollbar(list_border, orient="vertical", command=self.canvas.yview)
        self.inner_frame = tk.Frame(self.canvas, bg=Win98Style.BG_WHITE)

        self.inner_frame.bind("<Configure>", lambda _: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.inner_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        # Mousewheel scrolling (Linux uses Button-4/5)
        self.canvas.bind("<Button-4>", lambda _: self.canvas.yview_scroll(-3, "units"))
        self.canvas.bind("<Button-5>", lambda _: self.canvas.yview_scroll(3, "units"))

        self.count_label = Win98Style.label(self, text="", fg="#808080")
        self.count_label.pack(anchor="sw", padx=20, pady=(0, 8))

    def on_show(self) -> None:
        self.wizard.update_buttons(back=True, next=True, cancel=True, next_text="Next >")
        if not self._built:
            self._build_list()
            self._built = True
        self._update_count()

    def _build_list(self) -> None:
        managed = self.wizard.detected_state.managed_games
        stripe = False
        for game in sorted(self.wizard.games, key=lambda g: g.name.lower()):
            var = tk.BooleanVar(value=True)
            self.game_vars[game.slug] = var

            bg = "#f0f0f0" if stripe else Win98Style.BG_WHITE
            row = tk.Frame(self.inner_frame, bg=bg)
            row.pack(fill="x", padx=0, pady=0)

            cb = tk.Checkbutton(
                row, variable=var, bg=bg, activebackground=bg,
                selectcolor=Win98Style.BG_WHITE, command=self._update_count,
            )
            cb.pack(side="left", padx=(6, 0))

            tk.Label(
                row, text=game.name, font=Win98Style.FONT_MAIN,
                bg=bg, anchor="w",
            ).pack(side="left", padx=(2, 8), fill="x", expand=True)

            tk.Label(
                row, text=game.runner, font=Win98Style.FONT_SMALL,
                bg=bg, fg="#808080", anchor="w", width=8,
            ).pack(side="left", padx=4)

            is_synced = game.slug in managed
            status_text = "synced" if is_synced else "new"
            status_fg = Win98Style.COLOR_OK if is_synced else Win98Style.COLOR_NEW
            tk.Label(
                row, text=status_text, font=Win98Style.FONT_SMALL,
                bg=bg, fg=status_fg, anchor="e", width=6,
            ).pack(side="right", padx=(4, 10))

            stripe = not stripe

    def _update_count(self) -> None:
        selected = sum(1 for v in self.game_vars.values() if v.get())
        total = len(self.game_vars)
        self.count_label.config(text=f"{selected} of {total} games selected")

    def _select_all(self) -> None:
        for v in self.game_vars.values():
            v.set(True)
        self._update_count()

    def _deselect_all(self) -> None:
        for v in self.game_vars.values():
            v.set(False)
        self._update_count()

    def validate(self) -> bool:
        selected = {slug for slug, v in self.game_vars.items() if v.get()}
        if not selected:
            tk.messagebox.showwarning(
                "No Games Selected",
                "Please select at least one game to sync.",
                parent=self.wizard,
            )
            return False
        self.wizard.selected_slugs = selected
        return True


# ---------------------------------------------------------------------------
# Page 4: Options
# ---------------------------------------------------------------------------

class OptionsPage(WizardPage):
    next_page = "progress"

    def __init__(self, wizard: "SyncWizard"):
        super().__init__(wizard)

        Win98Style.label(
            self, text="Sync Options", font=Win98Style.FONT_TITLE,
        ).pack(anchor="nw", padx=20, pady=(24, 8))

        Win98Style.etched_line(self).pack(fill="x", padx=20, pady=(0, 12))

        # --- Steam User group ---
        group1 = tk.LabelFrame(
            self, text=" Steam User ", font=Win98Style.FONT_BOLD,
            bg=Win98Style.BG, relief="groove", bd=2,
        )
        group1.pack(fill="x", padx=20, pady=(0, 10))

        row1 = tk.Frame(group1, bg=Win98Style.BG)
        row1.pack(fill="x", padx=12, pady=8)
        Win98Style.label(row1, text="Target user:").pack(side="left")
        self.user_var = tk.StringVar()
        self.user_menu = tk.OptionMenu(row1, self.user_var, "")
        self.user_menu.config(
            font=Win98Style.FONT_MAIN, bg=Win98Style.BTN_FACE,
            relief="raised", bd=2, width=14,
        )
        self.user_menu.pack(side="left", padx=(8, 0))

        # --- SteamGridDB group ---
        group2 = tk.LabelFrame(
            self, text=" SteamGridDB Artwork ", font=Win98Style.FONT_BOLD,
            bg=Win98Style.BG, relief="groove", bd=2,
        )
        group2.pack(fill="x", padx=20, pady=(0, 10))

        row2 = tk.Frame(group2, bg=Win98Style.BG)
        row2.pack(fill="x", padx=12, pady=(8, 2))
        Win98Style.label(row2, text="API Key (optional):").pack(side="left")
        self.api_key_var = tk.StringVar()
        entry = tk.Entry(
            row2, textvariable=self.api_key_var, font=Win98Style.FONT_MAIN,
            relief="sunken", bd=2, width=36,
        )
        entry.pack(side="left", padx=(8, 0))

        Win98Style.label(
            group2, text="Get a free key at steamgriddb.com/profile/preferences/api",
            font=Win98Style.FONT_SMALL, fg="#808080",
        ).pack(anchor="w", padx=12, pady=(0, 8))

        # --- Sync Behavior group ---
        group3 = tk.LabelFrame(
            self, text=" Sync Behavior ", font=Win98Style.FONT_BOLD,
            bg=Win98Style.BG, relief="groove", bd=2,
        )
        group3.pack(fill="x", padx=20, pady=(0, 10))

        self.force_var = tk.BooleanVar(value=False)
        self.dryrun_var = tk.BooleanVar(value=False)

        tk.Checkbutton(
            group3, text="Force re-sync all games (regenerate scripts and shortcuts)",
            variable=self.force_var, bg=Win98Style.BG,
            selectcolor=Win98Style.BG_WHITE, font=Win98Style.FONT_MAIN,
            activebackground=Win98Style.BG, anchor="w",
        ).pack(anchor="w", padx=12, pady=(8, 2))

        tk.Checkbutton(
            group3, text="Dry run (preview only \u2014 no changes written to disk)",
            variable=self.dryrun_var, bg=Win98Style.BG,
            selectcolor=Win98Style.BG_WHITE, font=Win98Style.FONT_MAIN,
            activebackground=Win98Style.BG, anchor="w",
        ).pack(anchor="w", padx=12, pady=(2, 8))

    def on_show(self) -> None:
        self.wizard.update_buttons(back=True, next=True, cancel=True, next_text="Sync!")

        # Populate user dropdown
        menu = self.user_menu["menu"]
        menu.delete(0, "end")
        for uid in self.wizard.detected_user_ids:
            menu.add_command(label=uid, command=lambda u=uid: self.user_var.set(u))
        if self.wizard.selected_user_id:
            self.user_var.set(self.wizard.selected_user_id)
        elif self.wizard.detected_user_ids:
            self.user_var.set(self.wizard.detected_user_ids[0])

        # Load existing API key from config if present
        if not self.api_key_var.get():
            from lutris_bridge.config import _load_api_key_from_config
            existing_key = _load_api_key_from_config()
            if existing_key:
                self.api_key_var.set(existing_key)

    def validate(self) -> bool:
        self.wizard.selected_user_id = self.user_var.get()
        self.wizard.api_key = self.api_key_var.get().strip()
        self.wizard.force_sync = self.force_var.get()
        self.wizard.dry_run = self.dryrun_var.get()
        return True


# ---------------------------------------------------------------------------
# Page 5: Sync Progress
# ---------------------------------------------------------------------------

class SyncProgressPage(WizardPage):
    next_page = "complete"

    def __init__(self, wizard: "SyncWizard"):
        super().__init__(wizard)
        self._started = False

        self.title_label = Win98Style.label(
            self, text="Syncing Games...", font=Win98Style.FONT_TITLE,
        )
        self.title_label.pack(anchor="nw", padx=20, pady=(24, 8))

        Win98Style.etched_line(self).pack(fill="x", padx=20, pady=(0, 12))

        self.current_label = Win98Style.label(self, text="Preparing...", fg="#404040")
        self.current_label.pack(anchor="nw", padx=20, pady=(0, 6))

        self.progress = ChunkedProgressBar(self, width=420, height=22)
        self.progress.pack(padx=20, pady=(0, 12), fill="x")

        # Log output
        Win98Style.bold_label(self, text="Log Output:").pack(anchor="nw", padx=20, pady=(0, 2))
        self.log_text = tkinter.scrolledtext.ScrolledText(
            self, font=Win98Style.FONT_MONO, height=10, width=55,
            bg=Win98Style.BG_WHITE, relief="sunken", bd=2,
            state="disabled", wrap="word",
        )
        self.log_text.pack(fill="both", expand=True, padx=20, pady=(0, 8))

        # Configure log text tag colors
        self.log_text.tag_configure("ERROR", foreground=Win98Style.COLOR_ERR)
        self.log_text.tag_configure("WARNING", foreground=Win98Style.COLOR_WARN)
        self.log_text.tag_configure("INFO", foreground="#000000")
        self.log_text.tag_configure("DEBUG", foreground="#808080")

    def on_show(self) -> None:
        self.wizard.update_buttons(back=False, next=False, cancel=True)
        if not self._started:
            self._started = True
            self.after(200, self._start_sync)

    def _start_sync(self) -> None:
        self.log_queue: queue.Queue = queue.Queue()
        self.processed_count = 0
        self.total_games = len(self.wizard.selected_slugs)

        # Install queue handler on root logger
        self.queue_handler = QueueLogHandler(self.log_queue)
        self.queue_handler.setLevel(logging.DEBUG)
        self.queue_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logging.getLogger().addHandler(self.queue_handler)

        # Start worker thread
        self.sync_thread = threading.Thread(target=self._sync_worker, daemon=True)
        self.sync_thread.start()

        # Start polling
        self._poll_queue()

    def _sync_worker(self) -> None:
        try:
            from lutris_bridge.config import build_config
            from lutris_bridge.sync import sync

            config = build_config(
                steam_user=self.wizard.selected_user_id,
                steamgriddb_api_key=self.wizard.api_key or None,
            )
            counts = sync(
                config,
                dry_run=self.wizard.dry_run,
                force=self.wizard.force_sync,
                selected_slugs=self.wizard.selected_slugs,
            )
            self.log_queue.put(("done", counts))
        except Exception as exc:
            logger.error("Sync failed: %s", exc, exc_info=True)
            self.log_queue.put(("error", str(exc)))
        finally:
            logging.getLogger().removeHandler(self.queue_handler)

    def _poll_queue(self) -> None:
        try:
            while True:
                item = self.log_queue.get_nowait()
                kind = item[0]
                if kind == "log":
                    _, level, msg = item
                    self._append_log(msg, level)
                    self._update_progress(msg)
                elif kind == "done":
                    self.wizard.sync_counts = item[1]
                    self.wizard.sync_error = None
                    self._on_complete()
                    return
                elif kind == "error":
                    self.wizard.sync_counts = {"added": 0, "removed": 0, "updated": 0, "total": 0}
                    self.wizard.sync_error = item[1]
                    self._on_error(item[1])
                    return
        except queue.Empty:
            pass

        self._poll_id = self.after(100, self._poll_queue)

    def _append_log(self, msg: str, level: int) -> None:
        if level >= logging.ERROR:
            tag = "ERROR"
        elif level >= logging.WARNING:
            tag = "WARNING"
        elif level >= logging.DEBUG + 1:
            tag = "INFO"
        else:
            tag = "DEBUG"

        self.log_text.config(state="normal")
        self.log_text.insert("end", msg + "\n", tag)
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _update_progress(self, msg: str) -> None:
        for prefix in ("Added:", "Updated:", "Removed:", "Would add:", "Would update:", "Would remove:"):
            if prefix in msg:
                self.processed_count += 1
                # Extract game name for display
                parts = msg.split(prefix, 1)
                if len(parts) > 1:
                    game_name = parts[1].strip().split("(")[0].strip()
                    self.current_label.config(text=f"Processing: {game_name}")
                break

        fraction = self.processed_count / max(self.total_games, 1)
        self.progress.set_progress(min(fraction, 1.0))

    def _on_complete(self) -> None:
        self.progress.set_progress(1.0)
        prefix = "[DRY RUN] " if self.wizard.dry_run else ""
        self.title_label.config(text=f"{prefix}Sync Complete")
        self.current_label.config(text="Done.", fg=Win98Style.COLOR_OK)
        self.wizard.update_buttons(back=False, next=True, cancel=False, next_text="Next >")

    def _on_error(self, msg: str) -> None:
        self.title_label.config(text="Sync Failed")
        self.current_label.config(text=f"Error: {msg}", fg=Win98Style.COLOR_ERR)
        self.wizard.update_buttons(back=False, next=True, cancel=False, next_text="Next >")
        tk.messagebox.showerror("Sync Error", f"The sync operation failed:\n\n{msg}", parent=self.wizard)


# ---------------------------------------------------------------------------
# Page 6: Complete
# ---------------------------------------------------------------------------

class CompletePage(WizardPage):

    def __init__(self, wizard: "SyncWizard"):
        super().__init__(wizard)

        self.title_label = Win98Style.label(
            self, text="Sync Complete", font=Win98Style.FONT_TITLE,
        )
        self.title_label.pack(anchor="nw", padx=20, pady=(24, 8))

        Win98Style.etched_line(self).pack(fill="x", padx=20, pady=(0, 12))

        self.body_label = Win98Style.label(
            self, text="", justify="left", wraplength=400,
        )
        self.body_label.pack(anchor="nw", padx=20, pady=(0, 8))

        # Summary frame
        self.summary_frame = Win98Style.sunken_frame(self)
        self.summary_frame.pack(fill="x", padx=20, pady=(0, 12))

        self.summary_labels: list[tuple[tk.Label, tk.Label]] = []

        # Warning banner (hidden until shown)
        self.warning_frame = tk.Frame(self, bg="#ffffcc", relief="groove", bd=2)
        self.warning_label = tk.Label(
            self.warning_frame,
            text="\u26a0  Please restart Steam for changes to take effect.",
            font=Win98Style.FONT_BOLD, bg="#ffffcc", fg="#666600",
        )
        self.warning_label.pack(padx=12, pady=8)

        # Bottom buttons
        btn_frame = tk.Frame(self, bg=Win98Style.BG)
        btn_frame.pack(side="bottom", fill="x", padx=20, pady=(0, 8))
        Win98Style.button(btn_frame, "Clean All", self._on_clean, width=12).pack(side="left")

    def on_show(self) -> None:
        self.wizard.update_buttons(back=False, next=True, cancel=False, next_text="Finish")

        counts = self.wizard.sync_counts
        error = self.wizard.sync_error

        # Clear old summary rows
        for k, v in self.summary_labels:
            k.destroy()
            v.destroy()
        self.summary_labels.clear()

        if error:
            prefix = "Sync Failed"
            self.title_label.config(text=prefix)
            self.body_label.config(
                text=f"The sync operation encountered an error:\n\n{error}",
                fg=Win98Style.COLOR_ERR,
            )
            self.warning_frame.pack_forget()
            return

        dry = self.wizard.dry_run
        prefix = "Dry Run Complete" if dry else "Sync Complete"
        self.title_label.config(text=prefix)

        self.body_label.config(
            text="The wizard has finished processing your games." if not dry
            else "This was a dry run \u2014 no changes were written to disk.",
            fg="#000000",
        )

        rows = [
            ("Games added:", str(counts.get("added", 0))),
            ("Games updated:", str(counts.get("updated", 0))),
            ("Games removed:", str(counts.get("removed", 0))),
            ("Total managed:", str(counts.get("total", 0))),
        ]
        for i, (key, val) in enumerate(rows):
            kl = tk.Label(
                self.summary_frame, text=key, font=Win98Style.FONT_BOLD,
                bg=Win98Style.BG_WHITE, anchor="w",
            )
            vl = tk.Label(
                self.summary_frame, text=val, font=Win98Style.FONT_MAIN,
                bg=Win98Style.BG_WHITE, anchor="w",
            )
            kl.grid(row=i, column=0, sticky="w", padx=(16, 8), pady=4)
            vl.grid(row=i, column=1, sticky="w", padx=(0, 16), pady=4)
            self.summary_labels.append((kl, vl))

        self.summary_frame.columnconfigure(1, weight=1)

        # Show restart warning if real changes were made
        has_changes = not dry and (counts.get("added", 0) or counts.get("updated", 0) or counts.get("removed", 0))
        if has_changes:
            self.warning_frame.pack(fill="x", padx=20, pady=(0, 12))
        else:
            self.warning_frame.pack_forget()

    def _on_clean(self) -> None:
        if not tk.messagebox.askyesno(
            "Clean All Shortcuts",
            "This will remove ALL lutris-bridge managed shortcuts and scripts from Steam.\n\n"
            "Are you sure?",
            parent=self.wizard,
        ):
            return

        try:
            from lutris_bridge.config import build_config
            from lutris_bridge.sync import clean

            config = build_config(steam_user=self.wizard.selected_user_id)
            removed = clean(config)
            tk.messagebox.showinfo(
                "Clean Complete",
                f"Removed {removed} managed shortcuts.\n\n"
                "Restart Steam for changes to take effect.",
                parent=self.wizard,
            )
        except Exception as exc:
            tk.messagebox.showerror(
                "Clean Failed", f"An error occurred:\n\n{exc}", parent=self.wizard,
            )

    def get_next_page(self) -> str:
        return ""  # Finish — exits the wizard


# ---------------------------------------------------------------------------
# Main Wizard Window
# ---------------------------------------------------------------------------

class SyncWizard(tk.Tk):
    """Windows 98 InstallShield-style wizard for lutris-bridge."""

    def __init__(self) -> None:
        super().__init__()
        Win98Style.resolve_fonts()

        self.title("lutris-bridge Sync Wizard")
        self.geometry("660x500")
        self.resizable(False, False)
        self.configure(bg=Win98Style.BG)

        # Shared state populated by pages
        self.detected_steam_dir: Path | None = None
        self.detected_lutris = None
        self.detected_user_ids: list[str] = []
        self.detected_state = None
        self.games: list = []
        self.selected_slugs: set[str] = set()
        self.selected_user_id: str = ""
        self.api_key: str = ""
        self.force_sync: bool = False
        self.dry_run: bool = False
        self.sync_counts: dict[str, int] = {}
        self.sync_error: str | None = None

        # --- Layout ---
        # Top area: sidebar + content
        self.top_frame = tk.Frame(self, bg=Win98Style.BG)
        self.top_frame.pack(fill="both", expand=True)

        # Sidebar
        self.sidebar = tk.Canvas(
            self.top_frame, width=170, bg=Win98Style.SIDEBAR_TOP,
            highlightthickness=0,
        )
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.bind("<Configure>", lambda _: self._draw_sidebar())

        # Content area
        self.content_frame = tk.Frame(self.top_frame, bg=Win98Style.BG)
        self.content_frame.pack(side="left", fill="both", expand=True)

        # Bottom area: etched line + buttons
        bottom = tk.Frame(self, bg=Win98Style.BG)
        bottom.pack(side="bottom", fill="x")

        Win98Style.etched_line(bottom).pack(fill="x", padx=8, pady=(4, 0))

        btn_frame = tk.Frame(bottom, bg=Win98Style.BG)
        btn_frame.pack(fill="x", padx=12, pady=8)

        self.btn_cancel = Win98Style.button(btn_frame, "Cancel", self._on_cancel)
        self.btn_cancel.pack(side="right")

        self.btn_next = Win98Style.button(btn_frame, "Next >", self._on_next)
        self.btn_next.pack(side="right", padx=(0, 6))

        self.btn_back = Win98Style.button(btn_frame, "< Back", self._on_back)
        self.btn_back.pack(side="right", padx=(0, 6))

        # --- Pages ---
        self.pages: dict[str, WizardPage] = {}
        self.current_page_name: str = ""
        self.page_history: list[str] = []

        self._register_page("welcome", WelcomePage(self))
        self._register_page("detection", DetectionPage(self))
        self._register_page("gamelist", GameListPage(self))
        self._register_page("options", OptionsPage(self))
        self._register_page("progress", SyncProgressPage(self))
        self._register_page("complete", CompletePage(self))

        self.show_page("welcome")

        # Handle window close
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _register_page(self, name: str, page: WizardPage) -> None:
        self.pages[name] = page

    def _draw_sidebar(self) -> None:
        """Draw the blue-to-navy gradient and title text on the sidebar."""
        self.sidebar.delete("all")
        w = self.sidebar.winfo_width()
        h = self.sidebar.winfo_height()
        if h <= 0:
            return

        # Vertical gradient: deep blue -> darker navy
        r1, g1, b1 = 0x00, 0x00, 0xAA
        r2, g2, b2 = 0x00, 0x00, 0x44
        for y in range(h):
            ratio = y / max(h - 1, 1)
            r = int(r1 + (r2 - r1) * ratio)
            g = int(g1 + (g2 - g1) * ratio)
            b = int(b1 + (b2 - b1) * ratio)
            self.sidebar.create_line(0, y, w, y, fill=f"#{r:02x}{g:02x}{b:02x}")

        # Title text
        cx = w // 2
        self.sidebar.create_text(
            cx, 36, text="lutris-bridge", fill="white",
            font=Win98Style.FONT_SIDEBAR, anchor="n",
        )
        self.sidebar.create_text(
            cx, 62, text="Sync Wizard", fill="#aaaaff",
            font=Win98Style.FONT_SIDEBAR_SUB, anchor="n",
        )

        # Decorative line under title
        self.sidebar.create_line(20, 84, w - 20, 84, fill="#4444cc", width=1)

        # Step indicators
        steps = ["Welcome", "Detection", "Games", "Options", "Sync", "Complete"]
        page_names = ["welcome", "detection", "gamelist", "options", "progress", "complete"]
        for i, (step_label, page_name) in enumerate(zip(steps, page_names)):
            y_pos = 104 + i * 24
            is_current = page_name == self.current_page_name
            is_visited = page_name in [self.current_page_name] + self.page_history
            if is_current:
                fill = "#ffffff"
                font = Win98Style.FONT_BOLD
            elif is_visited:
                fill = "#8888cc"
                font = Win98Style.FONT_MAIN
            else:
                fill = "#6666aa"
                font = Win98Style.FONT_MAIN
            marker = "\u25b6" if is_current else "  "
            self.sidebar.create_text(
                16, y_pos, text=marker, fill=fill, font=font, anchor="w",
            )
            self.sidebar.create_text(
                30, y_pos, text=step_label, fill=fill, font=font, anchor="w",
            )

    def show_page(self, name: str) -> None:
        """Switch to the named page."""
        if self.current_page_name and self.current_page_name in self.pages:
            self.pages[self.current_page_name].pack_forget()

        self.current_page_name = name
        page = self.pages[name]
        page.pack(fill="both", expand=True)
        page.on_show()
        self._draw_sidebar()

    def update_buttons(
        self,
        back: bool = True,
        next: bool = True,
        cancel: bool = True,
        next_text: str = "Next >",
    ) -> None:
        self.btn_back.config(state="normal" if back else "disabled")
        self.btn_next.config(state="normal" if next else "disabled", text=next_text)
        self.btn_cancel.config(state="normal" if cancel else "disabled")

    def _on_next(self) -> None:
        page = self.pages[self.current_page_name]
        if not page.validate():
            return

        next_name = page.get_next_page()
        if not next_name:
            # Finish
            self.destroy()
            return

        self.page_history.append(self.current_page_name)
        self.show_page(next_name)

    def _on_back(self) -> None:
        if self.page_history:
            prev = self.page_history.pop()
            self.show_page(prev)

    def _on_cancel(self) -> None:
        if tk.messagebox.askyesno(
            "Cancel",
            "Are you sure you want to exit the wizard?",
            parent=self,
        ):
            self.destroy()


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def main() -> int:
    """Entry point for lutris-bridge-gui."""
    try:
        from lutris_bridge.log import (
            install_unhandled_exception_hook,
            log_session_header,
            setup_logging,
        )

        setup_logging(verbose=False)
        install_unhandled_exception_hook()
        log_session_header(argv=["gui"])

        app = SyncWizard()
        app.mainloop()
        return 0

    except tk.TclError as exc:
        print(f"GUI error: {exc}", file=sys.stderr)
        print("Cannot start GUI. Is a graphical session running?", file=sys.stderr)
        return 1
    except Exception:
        logging.critical("Unexpected error in GUI", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

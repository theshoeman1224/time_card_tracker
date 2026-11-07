from __future__ import annotations

import logging
import tkinter as tk
from tkinter import messagebox

from time_tracker import db
from time_tracker.paths import log_path
from time_tracker.services import repository
from time_tracker.ui import theme
from time_tracker.ui.main_window import MainWindow
from time_tracker.util.logging_config import configure_logging


def report_callback_error(exc_type, exc, tb, show_error=messagebox.showerror) -> None:
    """Log an error that escaped a Tk callback and tell the user.

    Installed as root.report_callback_exception. Tk's default prints to stderr,
    which the windowed build doesn't have, so errors would otherwise vanish.
    """
    logging.error("Unhandled error in a UI callback", exc_info=(exc_type, exc, tb))
    show_error(
        "Time Card Tracker",
        f"Something went wrong: {exc}\n\nDetails were written to the log:\n{log_path()}",
    )


def main() -> None:
    """Configure logging, open the database, and start the main window."""
    configure_logging()
    try:
        conn = db.connect()
    except Exception as exc:
        logging.exception("Failed to open database")
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Time Card Tracker", f"Could not open the local database:\n{exc}")
        return

    root = tk.Tk()
    root.report_callback_exception = report_callback_error
    root.title("Time Card Tracker")
    root.geometry("1100x720")
    root.minsize(900, 600)
    theme.apply_theme(root, repository.get_setting(conn, theme.THEME_SETTING, theme.LIGHT))
    MainWindow(root, conn).pack(fill="both", expand=True)
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()

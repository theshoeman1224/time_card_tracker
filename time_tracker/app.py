from __future__ import annotations

import logging
import tkinter as tk
from tkinter import messagebox, ttk

from time_tracker import db
from time_tracker.ui.main_window import MainWindow
from time_tracker.util.logging_config import configure_logging


def main() -> None:
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
    root.title("Time Card Tracker")
    root.geometry("1100x720")
    root.minsize(900, 600)
    try:
        ttk.Style().theme_use("clam")
    except tk.TclError:
        pass
    MainWindow(root, conn).pack(fill="both", expand=True)
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()

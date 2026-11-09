from __future__ import annotations

import logging
import sqlite3
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from time_tracker import constants
from time_tracker.paths import database_path, log_path
from time_tracker.services import public_list, repository, tracking
from time_tracker.ui import theme
from time_tracker.ui.dialogs import ask_save_path, show_save_error
from time_tracker.util import desktop

# Frame label and dialog title for the public list controls.
PUBLIC_LIST_TITLE = "Public List"


class SettingsTab(ttk.Frame):
    """Rounding/reset settings and public list import/export."""

    def __init__(
        self,
        parent: tk.Widget,
        conn: sqlite3.Connection,
        on_change,
        on_public_import=None,
    ):
        super().__init__(parent, padding=10)
        self.conn = conn
        self.on_change = on_change
        self.on_public_import = on_public_import

        settings = ttk.LabelFrame(self, text="Settings")
        settings.pack(fill="x", pady=(0, 10))
        ttk.Label(settings, text="Rounding increment").grid(row=0, column=0, sticky="w", padx=10, pady=8)
        self.rounding = ttk.Combobox(settings, values=["1", "5", "6", "10", "15", "30"], width=8, state="readonly")
        self.rounding.grid(row=0, column=1, sticky="w", padx=8, pady=8)
        ttk.Button(settings, text="Save Settings", command=self.save_settings).grid(row=0, column=2, padx=8, pady=8)
        ttk.Button(settings, text="Reset Day", command=self.reset_day).grid(row=0, column=3, padx=8, pady=8)
        self.dark_mode = tk.BooleanVar(
            value=repository.get_setting(self.conn, theme.THEME_SETTING, theme.LIGHT) == theme.DARK
        )
        ttk.Checkbutton(settings, text="Dark mode", variable=self.dark_mode, command=self.save_theme).grid(
            row=0, column=4, padx=8, pady=8
        )
        self.hide_scope = tk.BooleanVar(value=repository.scope_column_hidden(self.conn))
        ttk.Checkbutton(
            settings, text=f"Hide {constants.SCOPE} column", variable=self.hide_scope, command=self.save_hide_scope
        ).grid(row=0, column=5, padx=8, pady=8)

        # Read-only entries so the paths can be selected and copied.
        files = ttk.Frame(settings)
        files.grid(row=1, column=0, columnspan=6, sticky="ew", padx=10, pady=(0, 8))
        settings.columnconfigure(5, weight=1)
        files.columnconfigure(1, weight=1)
        self.path_entries: dict[str, ttk.Entry] = {}
        for row, (label, path) in enumerate([("Database", database_path()), ("Log", log_path())]):
            ttk.Label(files, text=label).grid(row=row, column=0, sticky="w", pady=2)
            entry = ttk.Entry(files)
            entry.insert(0, str(path))
            entry.configure(state="readonly")
            entry.grid(row=row, column=1, sticky="ew", padx=8, pady=2)
            ttk.Button(files, text="Open folder", command=lambda p=path: self.open_folder(p.parent)).grid(
                row=row, column=2, pady=2
            )
            self.path_entries[label] = entry

        public = ttk.LabelFrame(self, text=PUBLIC_LIST_TITLE)
        public.pack(fill="x", pady=(0, 10))
        ttk.Label(public, text="One shared team list at a time; importing a new one replaces it.").pack(
            side="left", padx=(10, 4), pady=8
        )
        self.public_edits = tk.BooleanVar(
            value=repository.get_setting(self.conn, "allow_public_edits", "0") == "1"
        )
        ttk.Checkbutton(public, text="Allow editing public items", variable=self.public_edits, command=self.save_public_edits).pack(
            side="right", padx=10, pady=8
        )
        ttk.Button(public, text="Import…", command=self.import_public_list).pack(side="right", padx=(6, 10), pady=8)
        ttk.Button(public, text="Export…", command=self.export_public_list).pack(side="right", padx=(6, 4), pady=8)
        self.refresh()

    def refresh(self) -> None:
        self.rounding.set(repository.get_setting(self.conn, "rounding_increment_minutes", "15"))

    def save_settings(self) -> None:
        repository.set_setting(self.conn, "rounding_increment_minutes", self.rounding.get() or "15")
        # Lets the Reports tab regenerate with the new rounding.
        self.on_change()

    def save_public_edits(self) -> None:
        repository.set_setting(self.conn, "allow_public_edits", "1" if self.public_edits.get() else "0")
        self.on_change()

    def save_theme(self) -> None:
        name = theme.DARK if self.dark_mode.get() else theme.LIGHT
        repository.set_setting(self.conn, theme.THEME_SETTING, name)
        theme.apply_theme(self.winfo_toplevel(), name)

    def save_hide_scope(self) -> None:
        repository.set_setting(self.conn, constants.HIDE_SCOPE_SETTING, "1" if self.hide_scope.get() else "0")
        self.on_change()

    def open_folder(self, folder: Path) -> None:
        try:
            desktop.open_folder(folder)
        except OSError as exc:
            logging.warning("Could not open folder %s: %s", folder, exc)
            messagebox.showerror("Open Folder", f"Couldn't open the folder:\n{folder}\n\n{exc}", parent=self)

    def import_public_list(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            defaultextension=".json",
            filetypes=[("Public list", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            report = public_list.import_public_list(self.conn, Path(path))
        except ValueError as exc:
            messagebox.showerror(PUBLIC_LIST_TITLE, str(exc), parent=self)
            return
        except sqlite3.Error as exc:
            logging.exception("Public list import failed")
            messagebox.showerror(
                PUBLIC_LIST_TITLE,
                f"The public list couldn't be saved, so nothing was changed:\n{exc}",
                parent=self,
            )
            return
        if self.on_public_import:
            self.on_public_import(report)
        self.on_change()
        lines = [
            f"Public list imported from {Path(path).name}.",
            f"{constants.NWA}s: {report['nwas_added']} added, {report['nwas_updated']} updated, "
            f"{report['nwas_obsoleted']} obsoleted.",
            f"{constants.WORK_ITEM}s: {report['work_items_added']} added, {report['work_items_updated']} updated, "
            f"{report['work_items_obsoleted']} obsoleted.",
        ]
        stale = report["stale"]
        if stale:
            lines.append("")
            lines.append(
                f"{len(stale)} task split(s) reference charge codes dropped from the public list "
                "and must be relinked:"
            )
            lines.extend(f"  - {row['work_item_name']} ({row['nwa_code']})" for row in stale)
            messagebox.showwarning(PUBLIC_LIST_TITLE, "\n".join(lines), parent=self)
        else:
            messagebox.showinfo(PUBLIC_LIST_TITLE, "\n".join(lines), parent=self)

    def export_public_list(self) -> None:
        path = ask_save_path(self, ".json")
        if not path:
            return
        try:
            summary = public_list.export_public_list(self.conn, path)
        except ValueError as exc:
            messagebox.showerror(PUBLIC_LIST_TITLE, str(exc), parent=self)
            return
        except OSError as exc:
            show_save_error(self, PUBLIC_LIST_TITLE, path, exc)
            return
        messagebox.showinfo(
            PUBLIC_LIST_TITLE,
            f"Exported {summary['nwa_count']} NWA(s) and {summary['work_item_count']} work item(s) to {path}",
            parent=self,
        )

    def reset_day(self) -> None:
        if not messagebox.askyesno("Reset Day", "Stop current tracking and reset the current day?", parent=self):
            return
        tracking.reset_day(self.conn)
        self.on_change()

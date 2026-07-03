from __future__ import annotations

import sqlite3
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from time_tracker.paths import database_path, log_path
from time_tracker.services import exports, reports, repository, tracking
from time_tracker.util.time_utils import now_local


class SettingsReportsTab(ttk.Frame):
    def __init__(self, parent: tk.Widget, conn: sqlite3.Connection, on_change):
        super().__init__(parent, padding=10)
        self.conn = conn
        self.on_change = on_change
        self.current_report: dict[str, object] | None = None

        settings = ttk.LabelFrame(self, text="Settings")
        settings.pack(fill="x", pady=(0, 10))
        ttk.Label(settings, text="Rounding increment").grid(row=0, column=0, sticky="w", padx=10, pady=8)
        self.rounding = ttk.Combobox(settings, values=["1", "5", "6", "10", "15", "30"], width=8, state="readonly")
        self.rounding.grid(row=0, column=1, sticky="w", padx=8, pady=8)
        ttk.Button(settings, text="Save Settings", command=self.save_settings).grid(row=0, column=2, padx=8, pady=8)
        ttk.Button(settings, text="Reset Day", command=self.reset_day).grid(row=0, column=3, padx=8, pady=8)
        ttk.Label(settings, text=f"Database: {database_path()}").grid(row=1, column=0, columnspan=4, sticky="w", padx=10)
        ttk.Label(settings, text=f"Log: {log_path()}").grid(row=2, column=0, columnspan=4, sticky="w", padx=10, pady=(0, 8))

        controls = ttk.LabelFrame(self, text="Reports")
        controls.pack(fill="x", pady=(0, 10))
        ttk.Label(controls, text="Period").pack(side="left", padx=(10, 4), pady=8)
        self.period = ttk.Combobox(controls, values=["daily", "weekly", "monthly"], state="readonly", width=10)
        self.period.pack(side="left", padx=4)
        self.period.set("daily")
        ttk.Label(controls, text="Anchor Date").pack(side="left", padx=(14, 4))
        self.anchor = ttk.Entry(controls, width=14)
        self.anchor.pack(side="left", padx=4)
        self.anchor.insert(0, now_local().date().isoformat())
        ttk.Button(controls, text="Generate", command=self.generate).pack(side="left", padx=8)
        ttk.Button(controls, text="Export CSV", command=self.export_csv).pack(side="right", padx=(6, 10))
        ttk.Button(controls, text="Export Markdown", command=self.export_markdown).pack(side="right")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)
        self.work_items = ttk.Treeview(self.notebook, columns=("name", "raw", "rounded"), show="headings")
        self.nwas = ttk.Treeview(self.notebook, columns=("code", "raw", "rounded"), show="headings")
        for tree, first, label in [(self.work_items, "name", "Work Item"), (self.nwas, "code", "NWA")]:
            tree.heading(first, text=label)
            tree.heading("raw", text="Raw")
            tree.heading("rounded", text="Rounded")
            tree.column(first, width=360)
            tree.column("raw", width=120, anchor="e")
            tree.column("rounded", width=120, anchor="e")
        self.notebook.add(self.work_items, text="Raw Time Per Work Item")
        self.notebook.add(self.nwas, text="Charge Time Per NWA")
        self.refresh()
        self.generate()

    def refresh(self) -> None:
        self.rounding.set(repository.get_setting(self.conn, "rounding_increment_minutes", "15"))

    def save_settings(self) -> None:
        repository.set_setting(self.conn, "rounding_increment_minutes", self.rounding.get() or "15")
        self.conn.commit()
        self.generate()

    def reset_day(self) -> None:
        if not messagebox.askyesno("Reset Day", "Stop current tracking and reset the current day?", parent=self):
            return
        tracking.reset_day(self.conn)
        self.conn.commit()
        self.on_change()

    def generate(self) -> None:
        try:
            datetime.strptime(self.anchor.get().strip(), "%Y-%m-%d")
            self.current_report = reports.generate_report(self.conn, self.period.get(), self.anchor.get().strip())
        except ValueError as exc:
            messagebox.showerror("Report", str(exc), parent=self)
            return
        self.work_items.delete(*self.work_items.get_children())
        self.nwas.delete(*self.nwas.get_children())
        for row in self.current_report["work_items"]:
            self.work_items.insert("", "end", values=(row["name"], row["raw"], row["rounded"]))
        for row in self.current_report["nwas"]:
            self.nwas.insert("", "end", values=(row["code"], row["raw"], row["rounded"]))

    def _export_path(self, suffix: str) -> Path | None:
        path = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=suffix,
            filetypes=[(suffix.upper().strip("."), f"*{suffix}"), ("All files", "*.*")],
        )
        return Path(path) if path else None

    def export_csv(self) -> None:
        if not self.current_report:
            self.generate()
        if not self.current_report:
            return
        path = self._export_path(".csv")
        if not path:
            return
        exports.export_csv(self.current_report, path)
        messagebox.showinfo("Export", f"Exported {path}", parent=self)

    def export_markdown(self) -> None:
        if not self.current_report:
            self.generate()
        if not self.current_report:
            return
        path = self._export_path(".md")
        if not path:
            return
        exports.export_markdown(self.current_report, path)
        messagebox.showinfo("Export", f"Exported {path}", parent=self)

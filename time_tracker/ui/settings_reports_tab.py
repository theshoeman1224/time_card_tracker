from __future__ import annotations

import sqlite3
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from time_tracker import constants
from time_tracker.paths import database_path, log_path
from time_tracker.services import exports, public_list, reports, repository, tracking
from time_tracker.util.time_utils import now_local


class SettingsReportsTab(ttk.Frame):
    """Rounding/reset settings, public list import/export, reports, and exports."""

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

        public = ttk.LabelFrame(self, text="Public List")
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
        ttk.Button(controls, text="Copy NWA Values", command=self.copy_nwa_values).pack(side="right", padx=(6, 10))
        ttk.Button(controls, text="Export CSV", command=self.export_csv).pack(side="right", padx=(6, 10))
        ttk.Button(controls, text="Export Markdown", command=self.export_markdown).pack(side="right")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)
        self.work_items = ttk.Treeview(self.notebook, columns=("name", "raw", "rounded"), show="headings")
        self.nwas = ttk.Treeview(self.notebook, columns=("code", "raw", "rounded"), show="headings")
        for tree, first, label in [(self.work_items, "name", constants.WORK_ITEM), (self.nwas, "code", constants.NWA)]:
            tree.heading(first, text=label)
            tree.heading("raw", text=constants.RAW)
            tree.heading("rounded", text=constants.ROUNDED)
            tree.column(first, width=360)
            tree.column("raw", width=120, anchor="e")
            tree.column("rounded", width=120, anchor="e")
        self.notebook.add(self.work_items, text=f"{constants.RAW} Time Per {constants.WORK_ITEM}")
        self.notebook.add(self.nwas, text=f"Charge Time Per {constants.NWA}")
        self.nwas.bind("<Control-c>", self.copy_nwa_values)
        self.nwas.bind("<Command-c>", self.copy_nwa_values)
        self.refresh()
        self.generate()

    def refresh(self) -> None:
        self.rounding.set(repository.get_setting(self.conn, "rounding_increment_minutes", "15"))

    def save_settings(self) -> None:
        repository.set_setting(self.conn, "rounding_increment_minutes", self.rounding.get() or "15")
        self.generate()

    def save_public_edits(self) -> None:
        repository.set_setting(self.conn, "allow_public_edits", "1" if self.public_edits.get() else "0")
        self.on_change()

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
            messagebox.showerror("Public List", str(exc), parent=self)
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
            messagebox.showwarning("Public List", "\n".join(lines), parent=self)
        else:
            messagebox.showinfo("Public List", "\n".join(lines), parent=self)

    def export_public_list(self) -> None:
        path = self._export_path(".json")
        if not path:
            return
        try:
            summary = public_list.export_public_list(self.conn, path)
        except ValueError as exc:
            messagebox.showerror("Public List", str(exc), parent=self)
            return
        messagebox.showinfo(
            "Public List",
            f"Exported {summary['nwa_count']} NWA(s) and {summary['work_item_count']} work item(s) to {path}",
            parent=self,
        )

    def reset_day(self) -> None:
        if not messagebox.askyesno("Reset Day", "Stop current tracking and reset the current day?", parent=self):
            return
        tracking.reset_day(self.conn)
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

    def copy_nwa_values(self, _event=None):
        """Copy NWA codes to the clipboard: selected rows, or all rows if none selected.

        Returns 'break' so Tk's default Ctrl-C binding doesn't also run.
        """
        selected = self.nwas.selection() or self.nwas.get_children()
        values = [str(self.nwas.item(item, "values")[0]) for item in selected]
        self.clipboard_clear()
        self.clipboard_append("\n".join(values))
        self.update()
        return "break"

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

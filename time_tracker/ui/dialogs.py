from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import messagebox, ttk

from time_tracker.services import repository
from time_tracker.services.validation import basis_points_to_percent, parse_percent_to_basis_points
from time_tracker.util.time_utils import format_datetime, iso, parse_local_datetime


class NwaDialog(tk.Toplevel):
    def __init__(self, parent: tk.Widget, title: str, initial: sqlite3.Row | None = None):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.result: dict[str, str] | None = None
        self.transient(parent)
        self.grab_set()

        ttk.Label(self, text="Code").grid(row=0, column=0, sticky="w", padx=12, pady=(12, 4))
        self.code = ttk.Entry(self, width=40)
        self.code.grid(row=0, column=1, padx=12, pady=(12, 4))

        ttk.Label(self, text="Name").grid(row=1, column=0, sticky="w", padx=12, pady=4)
        self.name = ttk.Entry(self, width=40)
        self.name.grid(row=1, column=1, padx=12, pady=4)

        ttk.Label(self, text="Notes").grid(row=2, column=0, sticky="nw", padx=12, pady=4)
        self.notes = tk.Text(self, width=40, height=5)
        self.notes.grid(row=2, column=1, padx=12, pady=4)

        ttk.Label(self, text="Tags").grid(row=3, column=0, sticky="w", padx=12, pady=4)
        self.tags = ttk.Entry(self, width=40)
        self.tags.grid(row=3, column=1, padx=12, pady=4)

        buttons = ttk.Frame(self)
        buttons.grid(row=4, column=0, columnspan=2, sticky="e", padx=12, pady=12)
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(buttons, text="Save", command=self._save).pack(side="right")

        if initial:
            self.code.insert(0, initial["code"])
            self.name.insert(0, initial["name"] or "")
            self.notes.insert("1.0", initial["notes"] or "")
            self.tags.insert(0, initial["tags"] or "")
        self.code.focus_set()
        self.wait_window()

    def _save(self) -> None:
        code = self.code.get().strip()
        if not code:
            messagebox.showerror("NWA", "NWA code is required.", parent=self)
            return
        self.result = {
            "code": code,
            "name": self.name.get().strip(),
            "notes": self.notes.get("1.0", "end").strip(),
            "tags": self.tags.get().strip(),
        }
        self.destroy()


class WorkItemDialog(tk.Toplevel):
    def __init__(self, parent: tk.Widget, conn: sqlite3.Connection, title: str, initial: sqlite3.Row | None = None):
        super().__init__(parent)
        self.conn = conn
        self.title(title)
        self.result: dict[str, object] | None = None
        self.transient(parent)
        self.grab_set()
        self.geometry("680x520")

        ttk.Label(self, text="Name").grid(row=0, column=0, sticky="w", padx=12, pady=(12, 4))
        self.name = ttk.Entry(self, width=54)
        self.name.grid(row=0, column=1, sticky="ew", padx=12, pady=(12, 4))

        ttk.Label(self, text="Description").grid(row=1, column=0, sticky="nw", padx=12, pady=4)
        self.description = tk.Text(self, width=54, height=4)
        self.description.grid(row=1, column=1, sticky="ew", padx=12, pady=4)

        split_frame = ttk.LabelFrame(self, text="NWA Splits")
        split_frame.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=12, pady=8)
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(1, weight=1)
        split_frame.grid_columnconfigure(0, weight=1)
        split_frame.grid_rowconfigure(0, weight=1)

        self.splits = ttk.Treeview(split_frame, columns=("nwa", "percent"), show="headings", height=8)
        self.splits.heading("nwa", text="NWA")
        self.splits.heading("percent", text="Percent")
        self.splits.column("nwa", width=420)
        self.splits.column("percent", width=100, anchor="e")
        self.splits.grid(row=0, column=0, columnspan=4, sticky="nsew", padx=8, pady=8)

        self.nwa_values = []
        for row in repository.list_nwas(conn):
            label = f"{row['code']} - {row['name'] or ''}".strip()
            self.nwa_values.append((label, row["id"]))
        self.nwa_combo = ttk.Combobox(split_frame, values=[label for label, _ in self.nwa_values], state="readonly")
        self.nwa_combo.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        self.percent = ttk.Entry(split_frame, width=10)
        self.percent.grid(row=1, column=1, padx=4, pady=(0, 8))
        ttk.Button(split_frame, text="Add Split", command=self._add_split).grid(row=1, column=2, padx=4, pady=(0, 8))
        ttk.Button(split_frame, text="Remove", command=self._remove_split).grid(row=1, column=3, padx=8, pady=(0, 8))

        buttons = ttk.Frame(self)
        buttons.grid(row=3, column=0, columnspan=2, sticky="e", padx=12, pady=12)
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(buttons, text="Save", command=self._save).pack(side="right")

        self._split_ids: dict[str, str] = {}
        if initial:
            self.name.insert(0, initial["name"])
            self.description.insert("1.0", initial["description"] or "")
            for split in repository.get_work_item_splits(conn, initial["id"]):
                item = self.splits.insert("", "end", values=(split["code"], basis_points_to_percent(split["percent_basis_points"])))
                self._split_ids[item] = split["nwa_id"]
        self.wait_window()

    def _add_split(self) -> None:
        if not self.nwa_combo.get():
            messagebox.showerror("Work Item", "Choose an NWA.", parent=self)
            return
        try:
            basis_points = parse_percent_to_basis_points(self.percent.get())
        except ValueError as exc:
            messagebox.showerror("Work Item", str(exc), parent=self)
            return
        nwa_id = dict(self.nwa_values)[self.nwa_combo.get()]
        for item, existing_id in self._split_ids.items():
            if existing_id == nwa_id:
                self.splits.item(item, values=(self.nwa_combo.get().split(" - ")[0], basis_points_to_percent(basis_points)))
                return
        item = self.splits.insert("", "end", values=(self.nwa_combo.get().split(" - ")[0], basis_points_to_percent(basis_points)))
        self._split_ids[item] = nwa_id

    def _remove_split(self) -> None:
        for item in self.splits.selection():
            self._split_ids.pop(item, None)
            self.splits.delete(item)

    def _save(self) -> None:
        splits = []
        try:
            for item in self.splits.get_children():
                percent = parse_percent_to_basis_points(self.splits.item(item, "values")[1])
                splits.append((self._split_ids[item], percent))
            self.result = {
                "name": self.name.get().strip(),
                "description": self.description.get("1.0", "end").strip(),
                "splits": splits,
            }
        except ValueError as exc:
            messagebox.showerror("Work Item", str(exc), parent=self)
            return
        self.destroy()


class SessionDialog(tk.Toplevel):
    def __init__(self, parent: tk.Widget, conn: sqlite3.Connection, session: sqlite3.Row):
        super().__init__(parent)
        self.conn = conn
        self.session = session
        self.result: dict[str, str] | None = None
        self.title("Edit Session")
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)

        ttk.Label(self, text="Start").grid(row=0, column=0, sticky="w", padx=12, pady=(12, 4))
        self.start = ttk.Entry(self, width=28)
        self.start.grid(row=0, column=1, padx=12, pady=(12, 4))
        ttk.Label(self, text="End").grid(row=1, column=0, sticky="w", padx=12, pady=4)
        self.end = ttk.Entry(self, width=28)
        self.end.grid(row=1, column=1, padx=12, pady=4)

        ttk.Label(self, text="Work Item").grid(row=2, column=0, sticky="w", padx=12, pady=4)
        self.work_items = [(row["name"], row["id"]) for row in repository.list_work_items(conn)]
        self.work_item = ttk.Combobox(self, values=[name for name, _ in self.work_items], state="readonly", width=26)
        self.work_item.grid(row=2, column=1, padx=12, pady=4)

        ttk.Label(self, text="Note").grid(row=3, column=0, sticky="w", padx=12, pady=4)
        self.note = ttk.Entry(self, width=28)
        self.note.grid(row=3, column=1, padx=12, pady=4)

        buttons = ttk.Frame(self)
        buttons.grid(row=4, column=0, columnspan=2, sticky="e", padx=12, pady=12)
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(buttons, text="Save", command=self._save).pack(side="right")

        self.start.insert(0, format_datetime(session["start_at"]))
        self.end.insert(0, format_datetime(session["end_at"]))
        current_name = session["work_item_name"]
        if current_name in [name for name, _ in self.work_items]:
            self.work_item.set(current_name)
        self.note.insert(0, session["note"] or "")
        self.wait_window()

    def _save(self) -> None:
        try:
            start_at = iso(parse_local_datetime(self.start.get()))
            end_at = iso(parse_local_datetime(self.end.get()))
        except ValueError:
            messagebox.showerror("Session", "Use date/time format YYYY-MM-DD HH:MM.", parent=self)
            return
        if not self.work_item.get():
            messagebox.showerror("Session", "Choose a work item.", parent=self)
            return
        work_item_id = dict(self.work_items)[self.work_item.get()]
        self.result = {
            "start_at": start_at,
            "end_at": end_at,
            "work_item_id": work_item_id,
            "note": self.note.get().strip(),
        }
        self.destroy()

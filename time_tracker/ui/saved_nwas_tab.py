from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import messagebox, ttk

from time_tracker.services import repository
from time_tracker.ui.dialogs import NwaDialog


class SavedNwasTab(ttk.Frame):
    def __init__(self, parent: tk.Widget, conn: sqlite3.Connection, on_change):
        super().__init__(parent, padding=10)
        self.conn = conn
        self.on_change = on_change

        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 8))
        ttk.Label(toolbar, text="Search").pack(side="left")
        self.search = ttk.Entry(toolbar, width=32)
        self.search.pack(side="left", padx=6)
        self.search.bind("<KeyRelease>", lambda _event: self.refresh())
        ttk.Button(toolbar, text="Add", command=self.add_nwa).pack(side="right", padx=(6, 0))
        ttk.Button(toolbar, text="Edit", command=self.edit_nwa).pack(side="right", padx=(6, 0))
        ttk.Button(toolbar, text="Remove", command=self.remove_nwa).pack(side="right")

        self.tree = ttk.Treeview(self, columns=("code", "name", "tags", "notes"), show="headings", selectmode="browse")
        self.tree.heading("code", text="NWA")
        self.tree.heading("name", text="Name")
        self.tree.heading("tags", text="Tags")
        self.tree.heading("notes", text="Notes")
        self.tree.column("code", width=160)
        self.tree.column("name", width=240)
        self.tree.column("tags", width=180)
        self.tree.column("notes", width=360)
        self.tree.pack(fill="both", expand=True)

        self._rows: dict[str, sqlite3.Row] = {}
        self.refresh()

    def refresh(self) -> None:
        selected = self.selected_id()
        self.tree.delete(*self.tree.get_children())
        self._rows.clear()
        for row in repository.list_nwas(self.conn, query=self.search.get()):
            item = self.tree.insert(
                "",
                "end",
                iid=row["id"],
                values=(row["code"], row["name"] or "", row["tags"] or "", row["notes"] or ""),
            )
            self._rows[item] = row
        if selected and selected in self._rows:
            self.tree.selection_set(selected)

    def selected_id(self) -> str | None:
        selection = self.tree.selection()
        return selection[0] if selection else None

    def add_nwa(self) -> None:
        dialog = NwaDialog(self, "Add NWA")
        if not dialog.result:
            return
        try:
            repository.save_nwa(self.conn, **dialog.result)
            self.conn.commit()
            self.on_change()
        except sqlite3.IntegrityError:
            messagebox.showerror("NWA", "That NWA code already exists.", parent=self)
        except ValueError as exc:
            messagebox.showerror("NWA", str(exc), parent=self)

    def edit_nwa(self) -> None:
        row_id = self.selected_id()
        if not row_id:
            return
        dialog = NwaDialog(self, "Edit NWA", self._rows[row_id])
        if not dialog.result:
            return
        try:
            repository.save_nwa(self.conn, nwa_id=row_id, **dialog.result)
            self.conn.commit()
            self.on_change()
        except sqlite3.IntegrityError:
            messagebox.showerror("NWA", "That NWA code already exists.", parent=self)
        except ValueError as exc:
            messagebox.showerror("NWA", str(exc), parent=self)

    def remove_nwa(self) -> None:
        row_id = self.selected_id()
        if not row_id:
            return
        if not messagebox.askyesno("Remove NWA", "Remove this NWA from active lists?", parent=self):
            return
        repository.remove_nwa(self.conn, row_id)
        self.conn.commit()
        self.on_change()

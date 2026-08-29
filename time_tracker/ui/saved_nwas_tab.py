from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import messagebox, ttk

from time_tracker import constants
from time_tracker.services import repository
from time_tracker.ui.dialogs import NwaDialog


class SavedNwasTab(ttk.Frame):
    """Searchable list of NWAs with add/edit/remove."""

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
        self.show_obsolete = tk.BooleanVar(value=False)
        ttk.Checkbutton(toolbar, text="Show obsolete", variable=self.show_obsolete, command=self.refresh).pack(
            side="left", padx=(12, 0)
        )
        ttk.Button(toolbar, text="Add", command=self.add_nwa).pack(side="right", padx=(6, 0))
        ttk.Button(toolbar, text="Edit", command=self.edit_nwa).pack(side="right", padx=(6, 0))
        ttk.Button(toolbar, text="Remove", command=self.remove_nwa).pack(side="right")

        self.tree = ttk.Treeview(
            self, columns=("code", "name", "tags", "notes", "scope"), show="headings", selectmode="browse"
        )
        self.tree.heading("code", text=constants.NWA)
        self.tree.heading("name", text=constants.NAME)
        self.tree.heading("tags", text=constants.TAGS)
        self.tree.heading("notes", text=constants.NOTES)
        self.tree.heading("scope", text=constants.SCOPE)
        self.tree.column("code", width=160)
        self.tree.column("name", width=220)
        self.tree.column("tags", width=160)
        self.tree.column("notes", width=300)
        self.tree.column("scope", width=80, anchor="center")
        self.tree.tag_configure("obsolete", foreground="red")
        self.tree.pack(fill="both", expand=True)

        self._rows: dict[str, sqlite3.Row] = {}
        self.refresh()

    def refresh(self) -> None:
        selected = self.selected_id()
        self.tree.delete(*self.tree.get_children())
        self._rows.clear()
        for row in repository.list_nwas(
            self.conn, query=self.search.get(), include_obsolete=self.show_obsolete.get()
        ):
            scope = constants.PUBLIC if row["scope"] == "public" else constants.PERSONAL
            tags = ("obsolete",) if row["is_obsolete"] else ()
            item = self.tree.insert(
                "",
                "end",
                iid=row["id"],
                values=(row["code"], row["name"] or "", row["tags"] or "", row["notes"] or "", scope),
                tags=tags,
            )
            self._rows[item] = row
        if selected and selected in self._rows:
            self.tree.selection_set(selected)

    def selected_id(self) -> str | None:
        selection = self.tree.selection()
        return selection[0] if selection else None

    def _can_modify(self, row: sqlite3.Row) -> bool:
        """Guard edits to public NWAs unless the manager setting is enabled."""
        if row["scope"] != "public":
            return True
        if repository.get_setting(self.conn, "allow_public_edits", "0") == "1":
            return True
        messagebox.showerror(
            constants.NWA,
            "Public NWAs come from the imported public list and cannot be changed here. "
            "Enable 'Allow editing public items' on the Settings tab to manage them.",
            parent=self,
        )
        return False

    def add_nwa(self) -> None:
        dialog = NwaDialog(self, f"Add {constants.NWA}")
        if not dialog.result:
            return
        try:
            repository.save_nwa(self.conn, **dialog.result)
            self.on_change()
        except sqlite3.IntegrityError:
            messagebox.showerror(constants.NWA, f"That {constants.NWA} code already exists.", parent=self)
        except ValueError as exc:
            messagebox.showerror(constants.NWA, str(exc), parent=self)

    def edit_nwa(self) -> None:
        row_id = self.selected_id()
        if not row_id or not self._can_modify(self._rows[row_id]):
            return
        dialog = NwaDialog(self, f"Edit {constants.NWA}", self._rows[row_id])
        if not dialog.result:
            return
        try:
            repository.save_nwa(self.conn, nwa_id=row_id, **dialog.result)
            self.on_change()
        except sqlite3.IntegrityError:
            messagebox.showerror(constants.NWA, f"That {constants.NWA} code already exists.", parent=self)
        except ValueError as exc:
            messagebox.showerror(constants.NWA, str(exc), parent=self)

    def remove_nwa(self) -> None:
        row_id = self.selected_id()
        if not row_id or not self._can_modify(self._rows[row_id]):
            return
        if not messagebox.askyesno(f"Remove {constants.NWA}", f"Remove this {constants.NWA} from active lists?", parent=self):
            return
        repository.remove_nwa(self.conn, row_id)
        self.on_change()

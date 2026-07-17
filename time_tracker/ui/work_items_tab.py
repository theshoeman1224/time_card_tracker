from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import messagebox, ttk

from time_tracker.services import repository, tracking
from time_tracker.ui.dialogs import SessionDialog, WorkItemDialog
from time_tracker.util.time_utils import format_datetime, human_duration, seconds_between


class WorkItemsTab(ttk.Frame):
    def __init__(self, parent: tk.Widget, conn: sqlite3.Connection, on_change):
        super().__init__(parent, padding=10)
        self.conn = conn
        self.on_change = on_change
        self._work_rows: dict[str, sqlite3.Row] = {}
        self._session_rows: dict[str, sqlite3.Row] = {}

        status = ttk.Frame(self)
        status.pack(fill="x", pady=(0, 10))
        self.active_label = ttk.Label(status, text="Not tracking", font=("", 13, "bold"))
        self.active_label.pack(side="left")
        self.elapsed_label = ttk.Label(status, text="0:00")
        self.elapsed_label.pack(side="left", padx=16)
        ttk.Button(status, text="Pause / Stop", command=self.pause).pack(side="right")

        content = ttk.PanedWindow(self, orient="horizontal")
        content.pack(fill="both", expand=True)

        left = ttk.Frame(content)
        right = ttk.Frame(content)
        content.add(left, weight=2)
        content.add(right, weight=3)

        item_toolbar = ttk.Frame(left)
        item_toolbar.pack(fill="x", pady=(0, 8))
        ttk.Button(item_toolbar, text="Add", command=self.add_work_item).pack(side="left")
        ttk.Button(item_toolbar, text="Edit", command=self.edit_work_item).pack(side="left", padx=6)
        ttk.Button(item_toolbar, text="Remove", command=self.remove_work_item).pack(side="left")

        self.items = ttk.Treeview(left, columns=("name", "splits"), show="headings", selectmode="browse")
        self.items.heading("name", text="Work Item")
        self.items.heading("splits", text="NWA Splits")
        self.items.column("name", width=220)
        self.items.column("splits", width=260)
        self.items.pack(fill="both", expand=True)
        self.items.bind("<Double-1>", lambda _event: self.start_selected())
        self.items.bind("<Return>", lambda _event: self.start_selected())
        ttk.Button(left, text="Start / Switch to Selected", command=self.start_selected).pack(fill="x", pady=(8, 0))

        session_toolbar = ttk.Frame(right)
        session_toolbar.pack(fill="x", pady=(0, 8))
        ttk.Label(session_toolbar, text="Current Day Sessions").pack(side="left")
        ttk.Button(session_toolbar, text="Edit Session", command=self.edit_session).pack(side="right")

        self.sessions = ttk.Treeview(
            right,
            columns=("start", "end", "duration", "work_item"),
            show="headings",
            selectmode="browse",
        )
        for column, label, width in [
            ("start", "Start", 140),
            ("end", "End", 140),
            ("duration", "Duration", 90),
            ("work_item", "Work Item", 190),
        ]:
            self.sessions.heading(column, text=label)
            self.sessions.column(column, width=width)
        self.sessions.pack(fill="both", expand=True)

        self.summary = ttk.Label(right, text="")
        self.summary.pack(fill="x", pady=(8, 0))

        self.refresh()
        self.after(1000, self._tick)

    def refresh(self) -> None:
        self._refresh_items()
        self._refresh_sessions()
        self._refresh_status()

    def _refresh_items(self) -> None:
        selected = self.selected_work_item_id()
        self.items.delete(*self.items.get_children())
        self._work_rows.clear()
        active = tracking.current_open_session(self.conn)
        for row in repository.list_work_items(self.conn):
            splits = repository.get_work_item_splits(self.conn, row["id"])
            split_text = ", ".join(f"{split['code']} {split['percent_basis_points'] / 100:.0f}%" for split in splits)
            name = row["name"]
            if active and active["work_item_id"] == row["id"]:
                name = f"* {name}"
            self.items.insert("", "end", iid=row["id"], values=(name, split_text))
            self._work_rows[row["id"]] = row
        if selected and selected in self._work_rows:
            self.items.selection_set(selected)

    def _refresh_sessions(self) -> None:
        self.sessions.delete(*self.sessions.get_children())
        self._session_rows.clear()
        day = tracking.today_work_day(self.conn)
        if not day:
            self.summary.config(text="No work tracked today.")
            return
        total = 0
        for row in tracking.list_sessions_for_work_day(self.conn, day["id"]):
            seconds = seconds_between(row["start_at"], row["end_at"])
            total += seconds
            self.sessions.insert(
                "",
                "end",
                iid=row["id"],
                values=(
                    format_datetime(row["start_at"]),
                    format_datetime(row["end_at"]),
                    human_duration(seconds),
                    row["work_item_name"],
                ),
            )
            self._session_rows[row["id"]] = row
        self.summary.config(text=f"Current day total: {human_duration(total)}")

    def _refresh_status(self) -> None:
        active = tracking.current_open_session(self.conn)
        if not active:
            self.active_label.config(text="Not tracking")
            self.elapsed_label.config(text="0:00")
            return
        self.active_label.config(text=f"Tracking: {active['work_item_name']} ({active['work_date']})")
        self.elapsed_label.config(text=human_duration(seconds_between(active["start_at"], None)))

    def _tick(self) -> None:
        self._refresh_status()
        self.after(1000, self._tick)

    def selected_work_item_id(self) -> str | None:
        selection = self.items.selection()
        return selection[0] if selection else None

    def selected_session_id(self) -> str | None:
        selection = self.sessions.selection()
        return selection[0] if selection else None

    def add_work_item(self) -> None:
        if not repository.list_nwas(self.conn):
            messagebox.showerror("Work Item", "Create at least one NWA before adding work items.", parent=self)
            return
        dialog = WorkItemDialog(self, self.conn, "Add Work Item")
        if not dialog.result:
            return
        try:
            repository.save_work_item(self.conn, **dialog.result)
            self.conn.commit()
            self.on_change()
        except ValueError as exc:
            messagebox.showerror("Work Item", str(exc), parent=self)

    def edit_work_item(self) -> None:
        row_id = self.selected_work_item_id()
        if not row_id:
            return
        dialog = WorkItemDialog(self, self.conn, "Edit Work Item", self._work_rows[row_id])
        if not dialog.result:
            return
        try:
            repository.save_work_item(self.conn, work_item_id=row_id, **dialog.result)
            self.conn.commit()
            self.on_change()
        except ValueError as exc:
            messagebox.showerror("Work Item", str(exc), parent=self)

    def remove_work_item(self) -> None:
        row_id = self.selected_work_item_id()
        if not row_id:
            return
        if not messagebox.askyesno("Remove Work Item", "Remove this work item from active lists?", parent=self):
            return
        repository.remove_work_item(self.conn, row_id)
        self.conn.commit()
        self.on_change()

    def start_selected(self) -> None:
        row_id = self.selected_work_item_id()
        if not row_id:
            return
        try:
            tracking.start_or_switch(self.conn, row_id)
            self.conn.commit()
            self.on_change()
        except ValueError as exc:
            messagebox.showerror("Tracking", str(exc), parent=self)

    def pause(self) -> None:
        tracking.pause(self.conn)
        self.conn.commit()
        self.on_change()

    def edit_session(self) -> None:
        row_id = self.selected_session_id()
        if not row_id:
            return
        dialog = SessionDialog(self, self.conn, self._session_rows[row_id])
        if not dialog.result:
            return
        try:
            tracking.update_session(self.conn, row_id, **dialog.result)
            self.conn.commit()
            self.on_change()
        except ValueError as exc:
            messagebox.showerror("Session", str(exc), parent=self)

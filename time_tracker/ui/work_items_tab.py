from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import messagebox, ttk

from time_tracker import constants
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

        left_bottom = ttk.Frame(left)
        left_bottom.pack(side="bottom", fill="x")
        ttk.Button(left_bottom, text="Start / Switch to Selected", command=self.start_selected).pack(fill="x")

        right_bottom = ttk.Frame(right)
        right_bottom.pack(side="bottom", fill="x")
        self.summary = ttk.Label(right_bottom, text="")
        self.summary.pack(fill="x")

        item_toolbar = ttk.Frame(left)
        item_toolbar.pack(fill="x", pady=(0, 8))
        ttk.Button(item_toolbar, text="Add", command=self.add_work_item).pack(side="left")
        ttk.Button(item_toolbar, text="Edit", command=self.edit_work_item).pack(side="left", padx=6)
        ttk.Button(item_toolbar, text="Remove", command=self.remove_work_item).pack(side="left")
        ttk.Button(item_toolbar, text="↑", width=2, command=lambda: self.move_work_item(-1)).pack(side="right", padx=(6, 0))
        ttk.Button(item_toolbar, text="↓", width=2, command=lambda: self.move_work_item(1)).pack(side="right")

        self.items = ttk.Treeview(left, columns=("name", "splits"), show="headings", selectmode="browse")
        self.items.heading("name", text=constants.WORK_ITEM)
        self.items.heading("splits", text=f"{constants.NWA} Splits")
        self.items.column("name", width=220)
        self.items.column("splits", width=260)
        self.items.pack(fill="both", expand=True)
        self.items.bind("<Double-1>", lambda _event: self.start_selected())
        self.items.bind("<Return>", lambda _event: self.start_selected())

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
            ("work_item", constants.WORK_ITEM, 190),
        ]:
            self.sessions.heading(column, text=label)
            self.sessions.column(column, width=width)
        self.sessions.pack(fill="both", expand=True)

        self.refresh()
        self.after(1000, self._tick)

    def refresh(self) -> None:
        active = tracking.current_open_session(self.conn)
        self._refresh_items(active)
        self._refresh_sessions()
        self._refresh_status(active)

    def _refresh_items(self, active: sqlite3.Row | None) -> None:
        selected = self.selected_work_item_id()
        self.items.delete(*self.items.get_children())
        self._work_rows.clear()
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

    def _refresh_status(self, active: sqlite3.Row | None) -> None:
        if not active:
            self.active_label.config(text="Not tracking")
            self.elapsed_label.config(text="0:00")
            return
        self.active_label.config(text=f"Tracking: {active['work_item_name']} ({active['work_date']})")
        self.elapsed_label.config(text=human_duration(seconds_between(active["start_at"], None)))

    def _tick(self) -> None:
        active = tracking.current_open_session(self.conn)
        self._refresh_status(active)
        self.after(1000, self._tick)

    def selected_work_item_id(self) -> str | None:
        selection = self.items.selection()
        return selection[0] if selection else None

    def selected_session_id(self) -> str | None:
        selection = self.sessions.selection()
        return selection[0] if selection else None

    def add_work_item(self) -> None:
        if not repository.list_nwas(self.conn):
            messagebox.showerror(constants.WORK_ITEM, f"Create at least one {constants.NWA} before adding work items.", parent=self)
            return
        dialog = WorkItemDialog(self, self.conn, f"Add {constants.WORK_ITEM}")
        if not dialog.result:
            return
        try:
            repository.save_work_item(self.conn, **dialog.result)
            self.conn.commit()
            self.on_change()
        except ValueError as exc:
            messagebox.showerror(constants.WORK_ITEM, str(exc), parent=self)

    def edit_work_item(self) -> None:
        row_id = self.selected_work_item_id()
        if not row_id:
            return
        dialog = WorkItemDialog(self, self.conn, f"Edit {constants.WORK_ITEM}", self._work_rows[row_id])
        if not dialog.result:
            return
        try:
            repository.save_work_item(self.conn, work_item_id=row_id, **dialog.result)
            self.conn.commit()
            self.on_change()
        except ValueError as exc:
            messagebox.showerror(constants.WORK_ITEM, str(exc), parent=self)

    def remove_work_item(self) -> None:
        row_id = self.selected_work_item_id()
        if not row_id:
            return
        if not messagebox.askyesno(f"Remove {constants.WORK_ITEM}", f"Remove this {constants.WORK_ITEM.lower()} from active lists?", parent=self):
            return
        repository.remove_work_item(self.conn, row_id)
        self.conn.commit()
        self.on_change()

    def move_work_item(self, delta: int) -> None:
        row_id = self.selected_work_item_id()
        if not row_id:
            return
        try:
            repository.move_work_item(self.conn, row_id, delta)
            self.conn.commit()
            self.on_change()
        except ValueError as exc:
            messagebox.showerror(constants.WORK_ITEM, str(exc), parent=self)

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
            messagebox.showerror(constants.SESSION, str(exc), parent=self)

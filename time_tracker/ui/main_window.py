from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import ttk

from time_tracker.ui.saved_nwas_tab import SavedNwasTab
from time_tracker.ui.settings_reports_tab import SettingsReportsTab
from time_tracker.ui.work_items_tab import WorkItemsTab


class MainWindow(ttk.Frame):
    def __init__(self, parent: tk.Tk, conn: sqlite3.Connection):
        super().__init__(parent)
        self.conn = conn

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)

        self.saved_nwas = SavedNwasTab(self.notebook, conn, self.refresh_all)
        self.work_items = WorkItemsTab(self.notebook, conn, self.refresh_all)
        self.reports = SettingsReportsTab(self.notebook, conn, self.refresh_all)

        self.notebook.add(self.saved_nwas, text="Saved NWAs")
        self.notebook.add(self.work_items, text="Work Items / Current Work")
        self.notebook.add(self.reports, text="Settings / Reports")

    def refresh_all(self) -> None:
        self.saved_nwas.refresh()
        self.work_items.refresh()
        self.reports.refresh()

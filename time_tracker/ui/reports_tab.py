from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import messagebox, ttk

from time_tracker import constants
from time_tracker.services import exports, reports
from time_tracker.ui.dialogs import ask_save_path, show_save_error
from time_tracker.util.time_utils import DATE_FORMAT, now_local, parse_date

COLUMNS = ("label", "raw", "rounded")


class ReportTable(ttk.Frame):
    """A scrolling report table with a Total footer pinned underneath.

    The footer is a one-row, headerless tree with the same columns, so its
    values line up with the table's; column widths are copied over whenever
    the table is resized or a column is dragged.
    """

    def __init__(self, parent: tk.Widget, label: str):
        super().__init__(parent)
        self.tree = ttk.Treeview(self, columns=COLUMNS, show="headings")
        self.tree.heading("label", text=label)
        self.tree.heading("raw", text=constants.RAW)
        self.tree.heading("rounded", text=constants.ROUNDED)
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)

        self.footer = ttk.Treeview(self, columns=COLUMNS, show="", height=1, selectmode="none", takefocus=False)
        self.footer.tag_configure("total", font=("", 0, "bold"))
        for tree in (self.tree, self.footer):
            tree.column("label", width=360)
            tree.column("raw", width=120, anchor="e")
            tree.column("rounded", width=120, anchor="e")

        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        ttk.Separator(self, orient="horizontal").grid(row=1, column=0, sticky="ew", pady=(2, 0))
        self.footer.grid(row=2, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        for event in ("<Configure>", "<B1-Motion>", "<ButtonRelease-1>"):
            self.tree.bind(event, self._sync_widths, add="+")

    def show(self, rows, label_key: str, total: dict[str, object]) -> None:
        self.tree.delete(*self.tree.get_children())
        for row in rows:
            self.tree.insert("", "end", values=(row[label_key], row["raw"], row["rounded"]))
        self.footer.delete(*self.footer.get_children())
        self.footer.insert("", "end", values=("Total", total["raw"], total["rounded"]), tags=("total",))

    def _sync_widths(self, _event=None) -> None:
        # after_idle so the table has finished laying out its new widths first.
        self.after_idle(self._copy_widths)

    def _copy_widths(self) -> None:
        for column in COLUMNS:
            self.footer.column(column, width=self.tree.column(column, "width"))


class ReportsTab(ttk.Frame):
    """Daily/weekly/monthly reports with totals, plus CSV/Markdown export."""

    def __init__(self, parent: tk.Widget, conn: sqlite3.Connection):
        super().__init__(parent, padding=10)
        self.conn = conn
        self.current_report: dict[str, object] | None = None

        controls = ttk.LabelFrame(self, text="Reports")
        controls.pack(fill="x", pady=(0, 10))
        ttk.Label(controls, text="Period").pack(side="left", padx=(10, 4), pady=8)
        self.period = ttk.Combobox(controls, values=["daily", "weekly", "monthly"], state="readonly", width=10)
        self.period.pack(side="left", padx=4)
        self.period.set("daily")
        ttk.Label(controls, text="Anchor Date").pack(side="left", padx=(14, 4))
        self.anchor = ttk.Entry(controls, width=14)
        self.anchor.pack(side="left", padx=4)
        self.anchor.insert(0, now_local().strftime(DATE_FORMAT))
        ttk.Button(controls, text="Generate", command=self.generate).pack(side="left", padx=8)
        ttk.Button(controls, text="Copy NWA Values", command=self.copy_nwa_values).pack(side="right", padx=(6, 10))
        ttk.Button(controls, text="Export CSV", command=self.export_csv).pack(side="right", padx=(6, 10))
        ttk.Button(controls, text="Export Markdown", command=self.export_markdown).pack(side="right")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)
        self.work_items = ReportTable(self.notebook, constants.WORK_ITEM)
        self.nwas = ReportTable(self.notebook, constants.NWA)
        self.notebook.add(self.work_items, text=f"{constants.RAW} Time Per {constants.WORK_ITEM}")
        self.notebook.add(self.nwas, text=f"Charge Time Per {constants.NWA}")
        self.nwas.tree.bind("<Control-c>", self.copy_nwa_values)
        self.nwas.tree.bind("<Command-c>", self.copy_nwa_values)
        self.generate()

    def refresh(self) -> None:
        """Regenerate after a change elsewhere (new time, new rounding), skipping a bad anchor date quietly."""
        self.generate(show_errors=False)

    def generate(self, show_errors: bool = True) -> None:
        try:
            anchor_date = parse_date(self.anchor.get())
            self.current_report = reports.generate_report(self.conn, self.period.get(), anchor_date)
        except ValueError as exc:
            if show_errors:
                messagebox.showerror("Report", str(exc), parent=self)
            return
        self.work_items.show(self.current_report["work_items"], "name", self.current_report["work_item_total"])
        self.nwas.show(self.current_report["nwas"], "code", self.current_report["nwa_total"])

    def copy_nwa_values(self, _event=None):
        """Copy NWA codes to the clipboard: selected rows, or all rows if none selected.

        Returns 'break' so Tk's default Ctrl-C binding doesn't also run.
        """
        tree = self.nwas.tree
        selected = tree.selection() or tree.get_children()
        values = [str(tree.item(item, "values")[0]) for item in selected]
        self.clipboard_clear()
        self.clipboard_append("\n".join(values))
        self.update()
        return "break"

    def _ensure_report(self) -> bool:
        if not self.current_report:
            self.generate()
        return bool(self.current_report)

    def export_csv(self) -> None:
        self._export(".csv", exports.export_csv)

    def export_markdown(self) -> None:
        self._export(".md", exports.export_markdown)

    def _export(self, suffix: str, write) -> None:
        if not self._ensure_report():
            return
        path = ask_save_path(self, suffix)
        if not path:
            return
        try:
            write(self.current_report, path)
        except OSError as exc:
            show_save_error(self, "Export", path, exc)
            return
        messagebox.showinfo("Export", f"Exported {path}", parent=self)

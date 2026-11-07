from __future__ import annotations

import tkinter as tk
import weakref
from tkinter import ttk

# Each tree's border and padding: the width it needs beyond its columns.
_insets: weakref.WeakKeyDictionary[ttk.Treeview, int] = weakref.WeakKeyDictionary()


def scrolled_tree(parent: tk.Widget, **options) -> tuple[ttk.Frame, ttk.Treeview]:
    """Make a Treeview with a vertical scrollbar beside it.

    Returns (frame, tree): lay out the frame, and use the tree as usual.
    """
    frame = ttk.Frame(parent)
    tree = ttk.Treeview(frame, **options)
    scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    tree.grid(row=0, column=0, sticky="nsew")
    scroll.grid(row=0, column=1, sticky="ns")
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    _remember_inset(tree)
    # A new theme can change the border; Tk refreshes the requested width then.
    tree.bind("<<ThemeChanged>>", lambda _event: _remember_inset(tree), add="+")
    # Tk only fits columns to the tree after its first resize, so at startup
    # the last column can run under the scrollbar. Run after Tk's own layout.
    tree.bind("<Configure>", lambda _event: tree.after_idle(fit_columns, tree), add="+")
    # Hiding a column while the tree's tab is not shown can't be fitted then;
    # fit when the tab comes back, since that doesn't resize the tree.
    tree.bind("<Map>", lambda _event: tree.after_idle(fit_columns, tree), add="+")
    return frame, tree


def _remember_inset(tree: ttk.Treeview) -> None:
    """Record the tree's border and padding width.

    The requested width is the column widths plus the inset, but Tk only
    recomputes it on creation and theme changes, not when a column is resized,
    so it has to be measured at one of those moments.
    """
    total = sum(int(tree.column(column, "width")) for column in displayed_columns(tree))
    _insets[tree] = max(tree.winfo_reqwidth() - total, 0)


def displayed_columns(tree: ttk.Treeview) -> list[str]:
    """The tree's columns in display order, including the tree column if shown."""
    shown = list(tree.tk.splitlist(tree.cget("displaycolumns")))
    if shown == ["#all"]:
        shown = list(tree.tk.splitlist(tree.cget("columns")))
    if "tree" in str(tree.cget("show")):
        shown.insert(0, "#0")
    return shown


def fit_columns(tree: ttk.Treeview) -> None:
    """Resize stretchable columns so the displayed columns exactly fill the tree's width."""
    if not tree.winfo_exists() or not tree.winfo_ismapped():
        return
    columns = displayed_columns(tree)
    widths = {column: int(tree.column(column, "width")) for column in columns}
    total = sum(widths.values())
    inset = _insets.get(tree)
    if inset is None:
        inset = max(tree.winfo_reqwidth() - total, 0)
    available = tree.winfo_width() - inset
    gap = available - total
    if gap == 0 or available <= 1:
        return
    stretchy = [column for column in columns if tree.column(column, "stretch")]
    if gap > 0:
        # Spare width (e.g. after hiding a column) goes to columns in proportion to their width.
        limits = {column: gap for column in stretchy}
        weights = {column: widths[column] for column in stretchy}
    else:
        # Shrink columns in proportion to how far each can go before its minimum width.
        limits = {column: widths[column] - int(tree.column(column, "minwidth")) for column in stretchy}
        weights = limits
    sign = 1 if gap > 0 else -1
    for column, amount in _share(abs(gap), weights, limits).items():
        if amount:
            tree.column(column, width=widths[column] + sign * amount)


def _share(amount: int, weights: dict[str, int], limits: dict[str, int]) -> dict[str, int]:
    """Split amount in proportion to weights without giving any key more than its limit."""
    total_weight = sum(max(weight, 0) for weight in weights.values())
    if total_weight <= 0:
        return {}
    amount = min(amount, sum(max(limit, 0) for limit in limits.values()))
    shares = {key: min(max(limits[key], 0), amount * max(weight, 0) // total_weight) for key, weight in weights.items()}
    # Hand out the pixels lost to rounding.
    leftover = amount - sum(shares.values())
    for key in shares:
        extra = min(leftover, max(limits[key], 0) - shares[key])
        shares[key] += extra
        leftover -= extra
    return shares


def set_column_visible(tree: ttk.Treeview, column: str, visible: bool) -> None:
    """Show or hide one column, keeping the others in their configured order."""
    all_columns = list(tree.tk.splitlist(tree.cget("columns")))
    wanted = [name for name in all_columns if visible or name != column]
    current = list(tree.tk.splitlist(tree.cget("displaycolumns")))
    if current == ["#all"]:
        current = all_columns
    if current == wanted:
        return
    tree.configure(displaycolumns=wanted)
    tree.after_idle(fit_columns, tree)

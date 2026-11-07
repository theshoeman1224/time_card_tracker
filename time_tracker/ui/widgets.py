from __future__ import annotations

import tkinter as tk
from tkinter import ttk


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
    return frame, tree

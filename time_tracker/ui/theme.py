from __future__ import annotations

import tkinter as tk
from tkinter import ttk

LIGHT = "light"
DARK = "dark"
THEME_SETTING = "theme"

# Light matches ttk's stock "clam" colors, so light mode looks as it always has.
PALETTES: dict[str, dict[str, str]] = {
    LIGHT: {
        "bg": "#dcdad5",
        "fg": "#000000",
        "field": "#ffffff",
        "select_bg": "#4a6984",
        "select_fg": "#ffffff",
        "active": "#eeebe7",
        "heading": "#dcdad5",
        "trough": "#bab5ab",
        "light": "#eeebe7",
        "dark": "#cfcdc8",
        "border": "#9e9a91",
        "disabled_fg": "#999999",
        "danger": "red",
    },
    DARK: {
        "bg": "#2b2b2b",
        "fg": "#e6e6e6",
        "field": "#1e1e1e",
        "select_bg": "#3d6a99",
        "select_fg": "#ffffff",
        "active": "#3c3c3c",
        "heading": "#353535",
        "trough": "#232323",
        "light": "#3a3a3a",
        "dark": "#232323",
        "border": "#4a4a4a",
        "disabled_fg": "#7a7a7a",
        "danger": "#ff6b6b",
    },
}

_current = LIGHT


def normalize(name: str | None) -> str:
    """Map a stored setting value to a known theme name, defaulting to light."""
    return DARK if name == DARK else LIGHT


def color(key: str) -> str:
    """Look up a color in the active palette."""
    return PALETTES[_current][key]


def apply_theme(root: tk.Misc, name: str) -> None:
    """Recolor the whole app, including widgets that already exist.

    ttk widgets are styled through ttk.Style; classic Tk widgets (dialog
    windows, Text boxes, combobox drop-down lists) through tk_setPalette.
    Re-selecting the ttk theme sends <<ThemeChanged>> to every widget, which
    danger_tag() listens for to recolor tree rows.
    """
    global _current
    _current = normalize(name)
    p = PALETTES[_current]

    root.tk_setPalette(
        background=p["bg"],
        foreground=p["fg"],
        activeBackground=p["active"],
        activeForeground=p["fg"],
        highlightColor=p["select_bg"],
        highlightBackground=p["bg"],
        selectBackground=p["select_bg"],
        selectForeground=p["select_fg"],
        insertBackground=p["fg"],
        troughColor=p["trough"],
        disabledForeground=p["disabled_fg"],
    )
    # Text boxes and lists hold user input, so give them the field color.
    for pattern in ("*Text.background", "*Listbox.background", "*Entry.background"):
        root.option_add(pattern, p["field"])
    for path in _walk(root):
        if root.tk.call("winfo", "class", path) in ("Text", "Listbox", "Entry"):
            root.tk.call(path, "configure", "-background", p["field"])

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure(
        ".",
        background=p["bg"],
        foreground=p["fg"],
        fieldbackground=p["field"],
        selectbackground=p["select_bg"],
        selectforeground=p["select_fg"],
        troughcolor=p["trough"],
        bordercolor=p["border"],
        lightcolor=p["light"],
        darkcolor=p["dark"],
        insertcolor=p["fg"],
        arrowcolor=p["fg"],
        indicatorbackground=p["field"],
        indicatorforeground=p["fg"],
    )
    style.map(
        ".",
        background=[("disabled", p["bg"]), ("active", p["active"])],
        foreground=[("disabled", p["disabled_fg"])],
    )
    style.map("TButton", background=[("disabled", p["bg"]), ("pressed", p["dark"]), ("active", p["active"])])
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", p["field"]), ("disabled", p["bg"])],
        foreground=[("disabled", p["disabled_fg"])],
        selectbackground=[("readonly", p["select_bg"])],
        selectforeground=[("readonly", p["select_fg"])],
    )
    style.map("TCheckbutton", indicatorbackground=[("pressed", p["active"]), ("disabled", p["bg"])])
    style.configure("TNotebook.Tab", background=p["dark"])
    style.map("TNotebook.Tab", background=[("selected", p["bg"]), ("active", p["active"])])
    style.configure("Treeview", background=p["field"], fieldbackground=p["field"], foreground=p["fg"])
    style.map(
        "Treeview",
        background=[("selected", p["select_bg"])],
        foreground=[("selected", p["select_fg"])],
    )
    style.configure("Treeview.Heading", background=p["heading"], foreground=p["fg"])
    style.map("Treeview.Heading", background=[("active", p["active"])])
    style.configure("Danger.TLabel", foreground=p["danger"])


def danger_tag(tree: ttk.Treeview, tag: str) -> None:
    """Show rows with this tag in the warning color, following theme changes."""

    def paint(_event=None) -> None:
        tree.tag_configure(tag, foreground=color("danger"))

    paint()
    tree.bind("<<ThemeChanged>>", paint, add="+")


def _walk(root: tk.Misc):
    """Yield the Tk path of every widget under root.

    Works on path names rather than winfo_children() so it also reaches
    widgets Tk creates internally, such as combobox drop-down lists.
    """
    stack = [str(root)]
    while stack:
        path = stack.pop()
        yield path
        stack.extend(str(child) for child in root.tk.splitlist(root.tk.call("winfo", "children", path)))

import tkinter as tk
import unittest
from tkinter import ttk

from tests.helpers import memory_conn
from time_tracker import db
from time_tracker.services import repository
from time_tracker.ui import theme


class NormalizeTests(unittest.TestCase):
    def test_dark_is_kept(self):
        self.assertEqual(theme.normalize("dark"), theme.DARK)

    def test_unknown_or_missing_values_fall_back_to_light(self):
        for value in ("light", "", None, "purple"):
            self.assertEqual(theme.normalize(value), theme.LIGHT)


class StoredThemeTests(unittest.TestCase):
    def test_new_database_defaults_to_light(self):
        conn = memory_conn()
        self.addCleanup(conn.close)
        self.assertEqual(repository.get_setting(conn, theme.THEME_SETTING), theme.LIGHT)

    def test_dark_choice_survives_reopening_the_database(self):
        conn = memory_conn()
        self.addCleanup(conn.close)
        repository.set_setting(conn, theme.THEME_SETTING, theme.DARK)
        # migrate() runs on every startup; it must not reset the choice.
        db.migrate(conn)
        self.assertEqual(repository.get_setting(conn, theme.THEME_SETTING), theme.DARK)


class ApplyThemeTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"no display: {exc}")
        self.root.withdraw()

    def tearDown(self):
        theme.apply_theme(self.root, theme.LIGHT)
        self.root.destroy()

    def test_switching_recolors_existing_widgets(self):
        text = tk.Text(self.root)
        tree = ttk.Treeview(self.root)
        theme.danger_tag(tree, "stale")

        theme.apply_theme(self.root, theme.DARK)
        self.root.update()

        dark = theme.PALETTES[theme.DARK]
        self.assertEqual(text.cget("background"), dark["field"])
        self.assertEqual(ttk.Style(self.root).lookup("TFrame", "background"), dark["bg"])
        self.assertEqual(str(tree.tag_configure("stale", "foreground")), dark["danger"])

        theme.apply_theme(self.root, theme.LIGHT)
        self.root.update()

        light = theme.PALETTES[theme.LIGHT]
        self.assertEqual(text.cget("background"), light["field"])
        self.assertEqual(str(tree.tag_configure("stale", "foreground")), light["danger"])


if __name__ == "__main__":
    unittest.main()

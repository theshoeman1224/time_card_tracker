import time
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from unittest import mock

from tests.helpers import memory_conn, seed_basic
from time_tracker import constants, db
from time_tracker.services import repository
from time_tracker.ui import settings_tab, widgets
from time_tracker.ui.main_window import MainWindow


class ShareTests(unittest.TestCase):
    def test_splits_in_proportion_and_uses_every_pixel(self):
        shares = widgets._share(10, {"a": 1, "b": 1, "c": 1}, {"a": 10, "b": 10, "c": 10})
        self.assertEqual(sum(shares.values()), 10)
        self.assertTrue(all(3 <= value <= 4 for value in shares.values()))

    def test_never_exceeds_a_limit(self):
        shares = widgets._share(50, {"a": 9, "b": 1}, {"a": 5, "b": 100})
        self.assertEqual(shares, {"a": 5, "b": 45})

    def test_stops_when_every_limit_is_reached(self):
        self.assertEqual(widgets._share(50, {"a": 1, "b": 1}, {"a": 3, "b": 4}), {"a": 3, "b": 4})


class ScopeSettingTests(unittest.TestCase):
    def test_scope_column_is_shown_by_default(self):
        conn = memory_conn()
        self.addCleanup(conn.close)
        self.assertFalse(repository.scope_column_hidden(conn))

    def test_hidden_choice_survives_reopening_the_database(self):
        conn = memory_conn()
        self.addCleanup(conn.close)
        repository.set_setting(conn, constants.HIDE_SCOPE_SETTING, "1")
        # migrate() runs on every startup; it must not reset the choice.
        db.migrate(conn)
        self.assertTrue(repository.scope_column_hidden(conn))


def _walk_widgets(widget):
    yield widget
    for child in widget.winfo_children():
        yield from _walk_widgets(child)


class TkTestCase(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"no display: {exc}")
        self.addCleanup(self.root.destroy)
        self.conn = memory_conn()
        self.addCleanup(self.conn.close)
        seed_basic(self.conn)
        # Keep the Settings tab from creating folders in the real user profile.
        for name, path in (("database_path", "/data/db.sqlite3"), ("log_path", "/logs/app.log")):
            patcher = mock.patch.object(settings_tab, name, return_value=Path(path))
            patcher.start()
            self.addCleanup(patcher.stop)

    def settle(self, timeout=2.0):
        """Let the window manager map and size the window, which happens asynchronously."""
        deadline = time.monotonic() + timeout
        last, stable_since = None, time.monotonic()
        while time.monotonic() < deadline:
            self.root.update()
            sizes = tuple((w.winfo_ismapped(), w.winfo_width()) for w in _walk_widgets(self.root))
            now = time.monotonic()
            if sizes != last:
                last, stable_since = sizes, now
            elif self.root.winfo_ismapped() and now - stable_since > 0.2:
                return
            time.sleep(0.01)


class FitColumnsTests(TkTestCase):
    def assert_columns_fit(self, tree):
        widths = [int(tree.column(column, "width")) for column in widgets.displayed_columns(tree)]
        self.assertEqual(sum(widths), tree.winfo_width() - widgets._insets[tree])

    def test_columns_fit_a_narrow_tree_at_startup(self):
        frame, tree = widgets.scrolled_tree(self.root, columns=("a", "b", "c"), show="headings")
        for column in ("a", "b", "c"):
            tree.column(column, width=200)
        frame.pack()
        frame.configure(width=300, height=200)
        frame.pack_propagate(False)
        frame.grid_propagate(False)
        self.settle()
        self.assertLess(tree.winfo_width(), 600)
        self.assert_columns_fit(tree)

    def test_work_items_tab_is_selected_at_startup(self):
        window = MainWindow(self.root, self.conn)
        self.assertEqual(window.notebook.select(), str(window.work_items))

    def test_work_items_scope_column_is_not_under_the_scrollbar_at_startup(self):
        self.root.geometry("1100x720")
        window = MainWindow(self.root, self.conn)
        window.pack(fill="both", expand=True)
        window.notebook.select(window.work_items)
        self.settle()
        self.assert_columns_fit(window.work_items.items)

    def test_hiding_scope_hides_it_on_both_tabs_and_the_rest_fill_the_width(self):
        self.root.geometry("1100x720")
        window = MainWindow(self.root, self.conn)
        window.pack(fill="both", expand=True)
        window.notebook.select(window.work_items)
        self.settle()

        window.settings.hide_scope.set(True)
        window.settings.save_hide_scope()
        self.settle()
        self.assertTrue(repository.scope_column_hidden(self.conn))
        for tree in (window.work_items.items, window.saved_nwas.tree):
            self.assertNotIn("scope", widgets.displayed_columns(tree))
        self.assert_columns_fit(window.work_items.items)

        window.settings.hide_scope.set(False)
        window.settings.save_hide_scope()
        self.settle()
        for tree in (window.work_items.items, window.saved_nwas.tree):
            self.assertIn("scope", widgets.displayed_columns(tree))
        self.assert_columns_fit(window.work_items.items)

    def test_hiding_scope_from_the_settings_tab_leaves_no_gap_on_the_nwas_tab(self):
        self.root.geometry("1100x720")
        window = MainWindow(self.root, self.conn)
        window.pack(fill="both", expand=True)
        self.settle()
        window.notebook.select(window.settings)
        self.settle()

        window.settings.hide_scope.set(True)
        window.settings.save_hide_scope()
        self.settle()
        window.notebook.select(window.saved_nwas)
        self.settle()
        self.assert_columns_fit(window.saved_nwas.tree)

        window.notebook.select(window.settings)
        self.settle()
        window.settings.hide_scope.set(False)
        window.settings.save_hide_scope()
        self.settle()
        window.notebook.select(window.saved_nwas)
        self.settle()
        self.assert_columns_fit(window.saved_nwas.tree)

    def test_scope_starts_hidden_when_the_setting_is_saved(self):
        repository.set_setting(self.conn, constants.HIDE_SCOPE_SETTING, "1")
        window = MainWindow(self.root, self.conn)
        self.assertTrue(window.settings.hide_scope.get())
        for tree in (window.work_items.items, window.saved_nwas.tree):
            self.assertEqual(widgets.displayed_columns(tree), [c for c in tree["columns"] if c != "scope"])


class SettingsPathTests(TkTestCase):
    def make_tab(self):
        return settings_tab.SettingsTab(self.root, self.conn, on_change=lambda: None)

    def test_paths_are_read_only_entries_that_hold_the_full_path(self):
        tab = self.make_tab()
        database = tab.path_entries["Database"]
        self.assertIsInstance(database, ttk.Entry)
        self.assertEqual(str(database.cget("state")), "readonly")
        self.assertEqual(database.get(), str(Path("/data/db.sqlite3")))
        self.assertEqual(tab.path_entries["Log"].get(), str(Path("/logs/app.log")))

    def test_open_folder_failure_is_reported_not_raised(self):
        tab = self.make_tab()
        with mock.patch.object(settings_tab.desktop, "open_folder", side_effect=FileNotFoundError("gone")), \
                mock.patch.object(settings_tab.messagebox, "showerror") as show_error, \
                self.assertLogs(level="WARNING"):
            tab.open_folder(Path("/missing"))
        show_error.assert_called_once()
        self.assertIn("gone", show_error.call_args.args[1])


if __name__ == "__main__":
    unittest.main()

import tkinter as tk
import unittest
from unittest import mock

from tests.helpers import memory_conn, seed_basic
from time_tracker.services import repository
from time_tracker.ui import dialogs
from time_tracker.ui.dialogs import unique_choices, work_item_choices


class UniqueChoicesTests(unittest.TestCase):
    def test_distinct_labels_are_unchanged(self):
        self.assertEqual(unique_choices([("A", "1"), ("B", "2")]), [("A", "1"), ("B", "2")])

    def test_repeated_labels_are_numbered(self):
        self.assertEqual(
            unique_choices([("Admin", "1"), ("Admin", "2"), ("Admin", "3")]),
            [("Admin", "1"), ("Admin (2)", "2"), ("Admin (3)", "3")],
        )


class WorkItemChoicesTests(unittest.TestCase):
    def test_personal_and_public_items_with_one_name_map_to_their_own_ids(self):
        rows = [
            {"id": "personal-id", "name": "Admin", "scope": "personal"},
            {"id": "public-id", "name": "Admin", "scope": "public"},
        ]
        choices = dict(work_item_choices(rows))
        self.assertEqual(choices, {"Admin": "personal-id", "Admin [public]": "public-id"})

    def test_two_personal_items_with_one_name_stay_distinct(self):
        rows = [
            {"id": "first", "name": "Admin", "scope": "personal"},
            {"id": "second", "name": "Admin", "scope": "personal"},
        ]
        self.assertEqual(dict(work_item_choices(rows)), {"Admin": "first", "Admin (2)": "second"})


class DialogTestCase(unittest.TestCase):
    """Builds dialogs without blocking: wait_window and grab_set are stubbed out."""

    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"no display: {exc}")
        self.addCleanup(self.root.destroy)
        self.conn = memory_conn()
        self.addCleanup(self.conn.close)
        self.nwa_a, self.nwa_b, self.work_item = seed_basic(self.conn)
        self.nwa_c = repository.save_nwa(self.conn, "C", "NWA C")
        for name in ("wait_window", "grab_set"):
            patcher = mock.patch.object(dialogs.BaseDialog, name)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(dialogs, "messagebox")
        self.messagebox = patcher.start()
        self.addCleanup(patcher.stop)


class WorkItemDialogSplitTests(DialogTestCase):
    def make_dialog(self, initial=None, on_save=None):
        dialog = dialogs.WorkItemDialog(self.root, self.conn, "Add", initial, on_save=on_save)
        self.addCleanup(lambda: dialog.winfo_exists() and dialog.destroy())
        return dialog

    def pick(self, dialog, nwa_id):
        label = next(label for label, value in dialog.nwa_values if value == nwa_id)
        dialog.nwa_combo.set(label)
        dialog._on_nwa_selected()

    def percents(self, dialog):
        return [dialog.splits.item(item, "values")[1] for item in dialog.splits.get_children()]

    def test_first_nwa_defaults_to_100(self):
        dialog = self.make_dialog()
        self.pick(dialog, self.nwa_a)
        self.assertEqual(dialog.percent.get(), "100")

    def test_next_nwa_defaults_to_what_is_left(self):
        dialog = self.make_dialog()
        self.pick(dialog, self.nwa_a)
        dialog.percent.delete(0, "end")
        dialog.percent.insert(0, "66.67")
        dialog._add_split()
        self.pick(dialog, self.nwa_b)
        self.assertEqual(dialog.percent.get(), "33.33")
        self.assertIn("33.33% left", dialog.total_label.cget("text"))

    def test_repicking_a_listed_nwa_counts_its_own_share_as_free(self):
        row = repository.list_work_items(self.conn)[0]
        dialog = self.make_dialog(initial=row)
        self.pick(dialog, self.nwa_b)
        self.assertEqual(dialog.percent.get(), "30")

    def test_nwa_defaults_to_blank_when_fully_allocated(self):
        dialog = self.make_dialog(initial=repository.list_work_items(self.conn)[0])
        self.pick(dialog, self.nwa_c)
        self.assertEqual(dialog.percent.get(), "")

    def test_adding_past_100_warns_and_changes_nothing(self):
        dialog = self.make_dialog()
        self.pick(dialog, self.nwa_a)
        dialog.percent.delete(0, "end")
        dialog.percent.insert(0, "70")
        dialog._add_split()
        self.pick(dialog, self.nwa_b)
        dialog.percent.delete(0, "end")
        dialog.percent.insert(0, "40")
        dialog._add_split()
        self.messagebox.showwarning.assert_called_once()
        self.assertIn("Only 30% is left", self.messagebox.showwarning.call_args.args[1])
        self.assertEqual(self.percents(dialog), ["70%"])

    def test_adding_when_already_at_100_warns(self):
        dialog = self.make_dialog(initial=repository.list_work_items(self.conn)[0])
        dialog.nwa_combo.set(next(label for label, value in dialog.nwa_values if value == self.nwa_c))
        dialog.percent.insert(0, "10")
        dialog._add_split()
        self.messagebox.showwarning.assert_called_once()
        self.assertEqual(self.percents(dialog), ["70%", "30%"])

    def test_raising_a_listed_split_within_its_own_share_is_allowed(self):
        dialog = self.make_dialog(initial=repository.list_work_items(self.conn)[0])
        self.pick(dialog, self.nwa_a)
        dialog.percent.delete(0, "end")
        dialog.percent.insert(0, "50")
        dialog._add_split()
        self.messagebox.showwarning.assert_not_called()
        self.assertEqual(self.percents(dialog), ["50%", "30%"])

    def test_save_under_100_is_blocked_inside_the_dialog(self):
        on_save = mock.Mock()
        dialog = self.make_dialog(on_save=on_save)
        dialog.name.insert(0, "Task")
        self.pick(dialog, self.nwa_a)
        dialog.percent.delete(0, "end")
        dialog.percent.insert(0, "60")
        dialog._add_split()
        dialog._save()
        on_save.assert_not_called()
        self.assertIsNone(dialog.result)
        self.assertTrue(dialog.winfo_exists())
        self.assertIn("100%", self.messagebox.showerror.call_args.args[1])


class OnSaveTests(DialogTestCase):
    def test_rejected_save_keeps_the_dialog_open(self):
        def on_save(_result):
            raise ValueError("That NWA code already exists.")

        dialog = dialogs.NwaDialog(self.root, "Add", on_save=on_save)
        self.addCleanup(lambda: dialog.winfo_exists() and dialog.destroy())
        dialog.code.insert(0, "A")
        dialog._save()
        self.assertIsNone(dialog.result)
        self.assertTrue(dialog.winfo_exists())
        self.messagebox.showerror.assert_called_once()
        self.assertEqual(dialog.code.get(), "A")

    def test_accepted_save_closes_the_dialog(self):
        saved = []
        dialog = dialogs.NwaDialog(self.root, "Add", on_save=saved.append)
        dialog.code.insert(0, "D")
        dialog._save()
        self.assertEqual(saved, [dialog.result])
        self.assertEqual(dialog.result["code"], "D")
        self.assertFalse(dialog.winfo_exists())

    def test_duplicate_nwa_code_becomes_a_message_the_dialog_can_show(self):
        from time_tracker.ui.saved_nwas_tab import SavedNwasTab

        tab = SavedNwasTab.__new__(SavedNwasTab)
        tab.conn = self.conn
        with self.assertRaisesRegex(ValueError, "already exists"):
            tab._save_nwa({"code": "A", "name": "", "notes": "", "tags": ""})


if __name__ == "__main__":
    unittest.main()

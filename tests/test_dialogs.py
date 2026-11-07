import unittest

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


if __name__ == "__main__":
    unittest.main()

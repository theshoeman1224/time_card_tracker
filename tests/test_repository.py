import sqlite3
import unittest

from tests.helpers import memory_conn, seed_basic
from time_tracker.services import repository


class NwaTests(unittest.TestCase):
    def test_duplicate_code_raises_integrity_error(self):
        conn = memory_conn()
        repository.save_nwa(conn, "A", "NWA A")
        with self.assertRaises(sqlite3.IntegrityError):
            repository.save_nwa(conn, "A", "Another A")

    @unittest.expectedFailure  # Bug: removed codes stay UNIQUE, so re-adding says "already exists".
    def test_readding_a_removed_code_works(self):
        conn = memory_conn()
        nwa_id = repository.save_nwa(conn, "ABC", "First")
        repository.remove_nwa(conn, nwa_id)

        repository.save_nwa(conn, "ABC", "Second")

        self.assertEqual([row["code"] for row in repository.list_nwas(conn)], ["ABC"])

    def test_search_by_tag_finds_the_nwa(self):
        conn = memory_conn()
        repository.save_nwa(conn, "X", "NWA X", tags="alpha, beta")
        repository.save_nwa(conn, "Y", "NWA Y", tags="gamma")

        self.assertEqual([row["code"] for row in repository.list_nwas(conn, query="alpha")], ["X"])

    def test_search_by_tag_returns_all_of_the_nwas_tags(self):
        conn = memory_conn()
        repository.save_nwa(conn, "X", "NWA X", tags="alpha, beta")

        tags = repository.list_nwas(conn, query="alpha")[0]["tags"]

        # Editing from search results saves this column back, so a partial list drops tags.
        self.assertEqual(sorted(tags.split(", ")), ["alpha", "beta"])


class ReplaceNwaTagsTests(unittest.TestCase):
    def test_replace_nwa_tags_saves_all_tags(self):
        conn = memory_conn()
        nwa_id = repository.save_nwa(conn, "X", "NWA X")

        repository.replace_nwa_tags(conn, nwa_id, ["tag1", "tag2", "tag3"])

        tags = repository.list_nwas(conn, query="X")[0]["tags"]
        self.assertEqual(sorted(tags.split(", ")), ["tag1", "tag2", "tag3"])

    def test_replace_nwa_tags_is_atomic(self):
        conn = memory_conn()
        nwa_id = repository.save_nwa(conn, "X", "NWA X", tags="old")
        # Fail the final insert, after the old links were deleted.
        conn.execute(
            "CREATE TEMP TRIGGER fail_tag_link BEFORE INSERT ON nwa_tags "
            "BEGIN SELECT RAISE(ABORT, 'forced failure'); END"
        )

        with self.assertRaises(sqlite3.IntegrityError):
            repository.replace_nwa_tags(conn, nwa_id, ["new"])

        self.assertEqual(repository.list_nwas(conn)[0]["tags"], "old")

    def test_replace_nwa_tags_replaces_existing(self):
        conn = memory_conn()
        nwa_id = repository.save_nwa(conn, "Y", "NWA Y")

        repository.replace_nwa_tags(conn, nwa_id, ["old1", "old2"])
        repository.replace_nwa_tags(conn, nwa_id, ["new1"])

        tags = repository.list_nwas(conn, query="Y")[0]["tags"]
        self.assertEqual(tags, "new1")

    def test_replace_nwa_tags_empty_list_clears(self):
        conn = memory_conn()
        nwa_id = repository.save_nwa(conn, "Z", "NWA Z")

        repository.replace_nwa_tags(conn, nwa_id, ["tag1"])
        repository.replace_nwa_tags(conn, nwa_id, [])

        tags = repository.list_nwas(conn, query="Z")[0]["tags"]
        self.assertEqual(tags, "")


class CreateWorkItemTests(unittest.TestCase):
    def test_create_work_item(self):
        conn = memory_conn()
        seed_basic(conn)
        new_nwa = repository.save_nwa(conn, "C", "NWA C")

        work_item_id = repository.create_work_item(conn, "Test", "Description", [(new_nwa, 10000)])

        item = repository.get_work_item(conn, work_item_id)
        self.assertIsNotNone(item)
        self.assertEqual(item["name"], "Test")
        splits = repository.get_work_item_splits(conn, work_item_id)
        self.assertEqual(len(splits), 1)
        self.assertEqual(splits[0]["percent_basis_points"], 10000)

    def test_create_work_item_empty_name_raises(self):
        conn = memory_conn()
        nwa_a, _, _ = seed_basic(conn)
        with self.assertRaises(ValueError):
            repository.create_work_item(conn, "", "", [(nwa_a, 10000)])


class UpdateWorkItemTests(unittest.TestCase):
    def test_update_work_item(self):
        conn = memory_conn()
        nwa_a, nwa_b, work_item = seed_basic(conn)

        repository.update_work_item(conn, work_item, "Updated", "New desc", [(nwa_a, 6000), (nwa_b, 4000)])

        item = repository.get_work_item(conn, work_item)
        self.assertEqual(item["name"], "Updated")
        self.assertEqual(item["description"], "New desc")
        splits = repository.get_work_item_splits(conn, work_item)
        by_nwa = {s["nwa_id"]: s["percent_basis_points"] for s in splits}
        self.assertEqual(by_nwa[nwa_a], 6000)
        self.assertEqual(by_nwa[nwa_b], 4000)

    def test_update_work_item_empty_name_raises(self):
        conn = memory_conn()
        _, _, work_item = seed_basic(conn)
        with self.assertRaises(ValueError):
            repository.update_work_item(conn, work_item, "", "", [])

    def test_failed_update_work_item_rolls_back(self):
        conn = memory_conn()
        nwa_a, nwa_b, work_item = seed_basic(conn)

        # Valid split total, but the second NWA doesn't exist — the INSERT fails
        # after the template UPDATE and split DELETE, so this exercises rollback.
        with self.assertRaises(sqlite3.IntegrityError):
            repository.update_work_item(conn, work_item, "Updated", "", [(nwa_a, 7000), ("missing-nwa", 3000)])

        item = repository.get_work_item(conn, work_item)
        self.assertEqual(item["name"], "Build")
        splits = repository.get_work_item_splits(conn, work_item)
        self.assertEqual({s["nwa_id"] for s in splits}, {nwa_a, nwa_b})


class MoveWorkItemTests(unittest.TestCase):
    def setUp(self):
        self.conn = memory_conn()
        self.nwa_a, _, self.first = seed_basic(self.conn)
        self.second = repository.save_work_item(self.conn, "Support", "", [(self.nwa_a, 10000)])

    def _order(self):
        return [row["id"] for row in repository.list_work_items(self.conn)]

    def test_move_up_and_back_down(self):
        self.assertEqual(self._order(), [self.first, self.second])

        repository.move_work_item(self.conn, self.second, -1)
        self.assertEqual(self._order(), [self.second, self.first])

        repository.move_work_item(self.conn, self.second, 1)
        self.assertEqual(self._order(), [self.first, self.second])

    def test_move_invalid_id_raises(self):
        with self.assertRaises(ValueError):
            repository.move_work_item(self.conn, "nonexistent-id", 1)

    def test_move_past_top_raises_with_user_facing_message(self):
        with self.assertRaises(ValueError) as ctx:
            repository.move_work_item(self.conn, self.first, -1)
        self.assertIn("top", str(ctx.exception))

    def test_move_past_bottom_raises_with_user_facing_message(self):
        with self.assertRaises(ValueError) as ctx:
            repository.move_work_item(self.conn, self.second, 1)
        self.assertIn("bottom", str(ctx.exception))


class SettingsTests(unittest.TestCase):
    def test_get_setting_returns_default_when_missing(self):
        conn = memory_conn()
        self.assertEqual(repository.get_setting(conn, "no_such_key", "fallback"), "fallback")
        self.assertEqual(repository.get_setting(conn, "no_such_key"), "")

    def test_get_setting_reads_seeded_defaults(self):
        conn = memory_conn()
        self.assertEqual(repository.get_setting(conn, "rounding_increment_minutes"), "15")
        self.assertEqual(repository.get_setting(conn, "rounding_mode"), "nearest")

    def test_set_setting_inserts_then_overwrites(self):
        conn = memory_conn()
        repository.set_setting(conn, "custom", "1")
        self.assertEqual(repository.get_setting(conn, "custom"), "1")

        repository.set_setting(conn, "custom", "2")
        self.assertEqual(repository.get_setting(conn, "custom"), "2")
        count = conn.execute("SELECT COUNT(*) FROM settings WHERE key = 'custom'").fetchone()[0]
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()

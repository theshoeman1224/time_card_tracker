import unittest
from datetime import datetime

from tests.helpers import memory_conn, seed_basic
from time_tracker.services import repository, tracking


class CreateWorkItemTests(unittest.TestCase):
    def test_create_work_item(self):
        conn = memory_conn()
        nwa_a, nwa_b, _ = seed_basic(conn)
        new_nwa = repository.save_nwa(conn, "C", "NWA C")
        conn.commit()

        work_item_id = repository.create_work_item(conn, "Test", "Description", [(new_nwa, 10000)])
        conn.commit()

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
        conn.commit()

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


class ReplaceNwaTagsTests(unittest.TestCase):
    def test_replace_nwa_tags_is_atomic(self):
        conn = memory_conn()
        nwa_id = repository.save_nwa(conn, "X", "NWA X")
        conn.commit()

        repository.replace_nwa_tags(conn, nwa_id, ["tag1", "tag2", "tag3"])
        conn.commit()

        tags = repository.list_nwas(conn, query="X")[0]["tags"]
        self.assertEqual(sorted(tags.split(", ")), ["tag1", "tag2", "tag3"])

    def test_replace_nwa_tags_replaces_existing(self):
        conn = memory_conn()
        nwa_id = repository.save_nwa(conn, "Y", "NWA Y")
        conn.commit()

        repository.replace_nwa_tags(conn, nwa_id, ["old1", "old2"])
        conn.commit()
        repository.replace_nwa_tags(conn, nwa_id, ["new1"])
        conn.commit()

        tags = repository.list_nwas(conn, query="Y")[0]["tags"]
        self.assertEqual(tags, "new1")

    def test_replace_nwa_tags_empty_list_clears(self):
        conn = memory_conn()
        nwa_id = repository.save_nwa(conn, "Z", "NWA Z")
        conn.commit()

        repository.replace_nwa_tags(conn, nwa_id, ["tag1"])
        conn.commit()
        repository.replace_nwa_tags(conn, nwa_id, [])
        conn.commit()

        tags = repository.list_nwas(conn, query="Z")[0]["tags"]
        self.assertEqual(tags, "")


class ValidateSessionUpdateTests(unittest.TestCase):
    def test_update_session_missing_raises(self):
        conn = memory_conn()
        _, _, work_item = seed_basic(conn)
        with self.assertRaises(ValueError) as ctx:
            tracking.update_session(conn, "nonexistent", "2026-07-02T09:00:00-04:00", "2026-07-02T10:00:00-04:00", work_item)
        self.assertIn("Session not found", str(ctx.exception))

    def test_update_session_end_before_start_raises(self):
        conn = memory_conn()
        _, _, work_item = seed_basic(conn)
        session_id = tracking.start_or_switch(conn, work_item, datetime.fromisoformat("2026-07-02T09:00:00-04:00"))
        conn.commit()

        with self.assertRaises(ValueError) as ctx:
            tracking.update_session(conn, session_id, "2026-07-02T10:00:00-04:00", "2026-07-02T09:00:00-04:00", work_item)
        self.assertIn("End time must be after start time", str(ctx.exception))

    def test_update_session_overlap_raises(self):
        conn = memory_conn()
        _, _, work_item = seed_basic(conn)
        session1 = tracking.start_or_switch(conn, work_item, datetime.fromisoformat("2026-07-02T09:00:00-04:00"))
        tracking.pause(conn, datetime.fromisoformat("2026-07-02T10:00:00-04:00"))
        session2 = tracking.start_or_switch(conn, work_item, datetime.fromisoformat("2026-07-02T10:30:00-04:00"))
        conn.commit()

        with self.assertRaises(ValueError) as ctx:
            tracking.update_session(conn, session2, "2026-07-02T09:00:00-04:00", "2026-07-02T10:30:00-04:00", work_item)
        self.assertIn("overlaps", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

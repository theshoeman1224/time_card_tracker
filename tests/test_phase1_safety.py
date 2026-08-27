import sqlite3
import unittest

from tests.helpers import memory_conn, seed_basic
from time_tracker.services import repository


class MoveWorkItemTests(unittest.TestCase):
    def test_move_work_item_invalid_id_raises(self):
        conn = memory_conn()
        seed_basic(conn)
        with self.assertRaises(ValueError):
            repository.move_work_item(conn, "nonexistent-id", 1)

    def test_move_work_item_boundary_returns_false(self):
        conn = memory_conn()
        _, _, work_item = seed_basic(conn)
        result = repository.move_work_item(conn, work_item, 1)
        self.assertFalse(result)


class StatusCheckConstraintTests(unittest.TestCase):
    def test_invalid_status_rejected(self):
        conn = memory_conn()
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO work_days(id, work_date, status) VALUES (?, ?, ?)",
                ("test-id", "2026-01-01", "invalid_status"),
            )

    def test_valid_status_open_accepted(self):
        conn = memory_conn()
        conn.execute(
            "INSERT INTO work_days(id, work_date, status) VALUES (?, ?, ?)",
            ("test-id", "2026-01-01", "open"),
        )
        conn.commit()
        row = conn.execute("SELECT status FROM work_days WHERE id = ?", ("test-id",)).fetchone()
        self.assertEqual(row["status"], "open")

    def test_valid_status_reset_accepted(self):
        conn = memory_conn()
        conn.execute(
            "INSERT INTO work_days(id, work_date, status) VALUES (?, ?, ?)",
            ("test-id", "2026-01-01", "reset"),
        )
        conn.commit()
        row = conn.execute("SELECT status FROM work_days WHERE id = ?", ("test-id",)).fetchone()
        self.assertEqual(row["status"], "reset")


if __name__ == "__main__":
    unittest.main()

import unittest
from datetime import datetime

from tests.helpers import memory_conn, seed_basic
from time_tracker.services import repository, tracking


class TrackingTests(unittest.TestCase):
    def setUp(self):
        self.conn = memory_conn()
        self.nwa_a, self.nwa_b, self.work_item = seed_basic(self.conn)

    def test_start_creates_session(self):
        session_id = tracking.start_or_switch(self.conn, self.work_item, datetime.fromisoformat("2026-07-02T09:00:00-04:00"))

        active = tracking.current_open_session(self.conn)
        self.assertIsNotNone(active)
        self.assertEqual(active["id"], session_id)
        self.assertEqual(active["work_item_id"], self.work_item)

    def test_switch_closes_previous_and_opens_new(self):
        other_nwa = repository.save_nwa(self.conn, "C", "NWA C")
        second = repository.save_work_item(self.conn, "Review", "", [(other_nwa, 10000)])

        first = tracking.start_or_switch(self.conn, self.work_item, datetime.fromisoformat("2026-07-02T09:00:00-04:00"))
        second_id = tracking.start_or_switch(self.conn, second, datetime.fromisoformat("2026-07-02T10:00:00-04:00"))

        active = tracking.current_open_session(self.conn)
        self.assertEqual(active["work_item_id"], second)
        self.assertEqual(active["id"], second_id)

        first_session = self.conn.execute("SELECT * FROM time_sessions WHERE id = ?", (first,)).fetchone()
        self.assertEqual(first_session["end_at"], "2026-07-02T10:00:00-04:00")

    def test_pause_closes_active_session(self):
        tracking.start_or_switch(self.conn, self.work_item, datetime.fromisoformat("2026-07-02T09:00:00-04:00"))
        tracking.pause(self.conn, datetime.fromisoformat("2026-07-02T10:30:00-04:00"))

        self.assertIsNone(tracking.current_open_session(self.conn))
        sessions = list(self.conn.execute("SELECT * FROM time_sessions ORDER BY start_at"))
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["end_at"], "2026-07-02T10:30:00-04:00")

    def test_pause_no_active_session(self):
        tracking.pause(self.conn)
        self.assertIsNone(tracking.current_open_session(self.conn))

    def test_start_or_switch_same_item_returns_existing(self):
        session_id = tracking.start_or_switch(self.conn, self.work_item, datetime.fromisoformat("2026-07-02T09:00:00-04:00"))
        same_id = tracking.start_or_switch(self.conn, self.work_item, datetime.fromisoformat("2026-07-02T09:05:00-04:00"))

        self.assertEqual(session_id, same_id)
        sessions = list(self.conn.execute("SELECT * FROM time_sessions"))
        self.assertEqual(len(sessions), 1)

    def test_midnight_stays_on_original_work_day(self):
        tracking.start_or_switch(self.conn, self.work_item, datetime.fromisoformat("2026-07-02T23:55:00-04:00"))
        tracking.pause(self.conn, datetime.fromisoformat("2026-07-03T00:10:00-04:00"))

        session = self.conn.execute(
            """
            SELECT s.*, w.work_date
            FROM time_sessions s JOIN work_days w ON w.id = s.work_day_id
            """
        ).fetchone()
        self.assertEqual(session["work_date"], "2026-07-02")

    def test_update_open_session_start_time(self):
        session_id = tracking.start_or_switch(self.conn, self.work_item, datetime.fromisoformat("2026-07-02T09:00:00-04:00"))

        tracking.update_session(self.conn, session_id, "2026-07-02T08:45:00-04:00", None, self.work_item)

        session = self.conn.execute("SELECT * FROM time_sessions WHERE id = ?", (session_id,)).fetchone()
        self.assertEqual(session["start_at"], "2026-07-02T08:45:00-04:00")
        self.assertIsNone(session["end_at"])

    def test_update_session_missing_raises(self):
        with self.assertRaises(ValueError) as ctx:
            tracking.update_session(self.conn, "nonexistent", "2026-07-02T09:00:00-04:00", "2026-07-02T10:00:00-04:00", self.work_item)
        self.assertIn("Session not found", str(ctx.exception))

    def test_update_session_end_before_start_raises(self):
        session_id = tracking.start_or_switch(self.conn, self.work_item, datetime.fromisoformat("2026-07-02T09:00:00-04:00"))

        with self.assertRaises(ValueError) as ctx:
            tracking.update_session(self.conn, session_id, "2026-07-02T10:00:00-04:00", "2026-07-02T09:00:00-04:00", self.work_item)
        self.assertIn("End time must be after start time", str(ctx.exception))

    def test_update_session_overlap_raises(self):
        tracking.start_or_switch(self.conn, self.work_item, datetime.fromisoformat("2026-07-02T09:00:00-04:00"))
        tracking.pause(self.conn, datetime.fromisoformat("2026-07-02T10:00:00-04:00"))
        session2 = tracking.start_or_switch(self.conn, self.work_item, datetime.fromisoformat("2026-07-02T10:30:00-04:00"))

        with self.assertRaises(ValueError) as ctx:
            tracking.update_session(self.conn, session2, "2026-07-02T09:00:00-04:00", "2026-07-02T10:30:00-04:00", self.work_item)
        self.assertIn("overlaps", str(ctx.exception))

    def test_reset_day_clears_sessions(self):
        tracking.start_or_switch(self.conn, self.work_item, datetime.fromisoformat("2026-07-02T09:00:00-04:00"))
        tracking.pause(self.conn, datetime.fromisoformat("2026-07-02T10:00:00-04:00"))

        tracking.reset_day(self.conn, datetime.fromisoformat("2026-07-02T10:30:00-04:00"))

        day = tracking.today_work_day(self.conn, datetime.fromisoformat("2026-07-02T11:00:00-04:00"))
        self.assertIsNotNone(day)
        self.assertEqual(day["status"], "reset")


if __name__ == "__main__":
    unittest.main()

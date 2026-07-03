import unittest
from datetime import datetime

from tests.helpers import memory_conn, seed_basic
from time_tracker.services import repository, tracking


class TrackingTests(unittest.TestCase):
    def test_start_switch_and_pause(self):
        conn = memory_conn()
        _, _, first = seed_basic(conn)
        other_nwa = repository.save_nwa(conn, "C", "NWA C")
        second = repository.save_work_item(conn, "Review", "", [(other_nwa, 10000)])
        conn.commit()

        tracking.start_or_switch(conn, first, datetime.fromisoformat("2026-07-02T09:00:00-04:00"))
        tracking.start_or_switch(conn, second, datetime.fromisoformat("2026-07-02T10:00:00-04:00"))
        active = tracking.current_open_session(conn)
        self.assertEqual(active["work_item_id"], second)

        tracking.pause(conn, datetime.fromisoformat("2026-07-02T10:30:00-04:00"))
        self.assertIsNone(tracking.current_open_session(conn))
        sessions = list(conn.execute("SELECT * FROM time_sessions ORDER BY start_at"))
        self.assertEqual(len(sessions), 2)
        self.assertEqual(sessions[0]["end_at"], "2026-07-02T10:00:00-04:00")

    def test_midnight_stays_on_original_work_day(self):
        conn = memory_conn()
        _, _, work_item = seed_basic(conn)
        tracking.start_or_switch(conn, work_item, datetime.fromisoformat("2026-07-02T23:55:00-04:00"))
        tracking.pause(conn, datetime.fromisoformat("2026-07-03T00:10:00-04:00"))
        session = conn.execute(
            """
            SELECT s.*, w.work_date
            FROM time_sessions s JOIN work_days w ON w.id = s.work_day_id
            """
        ).fetchone()
        self.assertEqual(session["work_date"], "2026-07-02")


if __name__ == "__main__":
    unittest.main()

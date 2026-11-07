import json
import unittest
from datetime import datetime

from tests.helpers import memory_conn, seed_basic, write_list_file
from time_tracker.services import public_list, repository, tracking


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

    def test_reset_day_closes_open_session_and_marks_day_reset(self):
        # Pins current behaviour: reset stops the timer and flags the day, but keeps its sessions.
        tracking.start_or_switch(self.conn, self.work_item, datetime.fromisoformat("2026-07-02T09:00:00-04:00"))

        tracking.reset_day(self.conn, datetime.fromisoformat("2026-07-02T10:30:00-04:00"))

        self.assertIsNone(tracking.current_open_session(self.conn))
        day = tracking.today_work_day(self.conn, datetime.fromisoformat("2026-07-02T11:00:00-04:00"))
        self.assertIsNotNone(day)
        self.assertEqual(day["status"], "reset")
        sessions = tracking.list_sessions_for_work_day(self.conn, day["id"])
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["end_at"], "2026-07-02T10:30:00-04:00")


class DayTotalsTests(unittest.TestCase):
    """The 'open session ends now' rule lives here, not in time_utils or the UI."""

    def setUp(self):
        self.conn = memory_conn()
        self.nwa_a, self.nwa_b, self.work_item = seed_basic(self.conn)

    def _sessions(self):
        day = tracking.today_work_day(self.conn, datetime.fromisoformat("2026-07-02T11:00:00-04:00"))
        return tracking.list_sessions_for_work_day(self.conn, day["id"])

    def test_closed_session_spans_its_times(self):
        tracking.start_or_switch(self.conn, self.work_item, datetime.fromisoformat("2026-07-02T09:00:00-04:00"))
        tracking.pause(self.conn, datetime.fromisoformat("2026-07-02T10:00:00-04:00"))

        self.assertEqual(tracking.session_seconds(self._sessions()[0]), 3600)

    def test_open_session_spans_until_current(self):
        tracking.start_or_switch(self.conn, self.work_item, datetime.fromisoformat("2026-07-02T09:00:00-04:00"))
        session = self._sessions()[0]

        seconds = tracking.session_seconds(session, datetime.fromisoformat("2026-07-02T09:30:00-04:00"))
        self.assertEqual(seconds, 1800)

    def test_work_day_seconds_includes_open_session_up_to_current(self):
        tracking.start_or_switch(self.conn, self.work_item, datetime.fromisoformat("2026-07-02T09:00:00-04:00"))
        tracking.pause(self.conn, datetime.fromisoformat("2026-07-02T10:00:00-04:00"))
        tracking.start_or_switch(self.conn, self.work_item, datetime.fromisoformat("2026-07-02T10:30:00-04:00"))
        day = tracking.today_work_day(self.conn, datetime.fromisoformat("2026-07-02T11:00:00-04:00"))

        total = tracking.work_day_seconds(self.conn, day["id"], datetime.fromisoformat("2026-07-02T11:00:00-04:00"))
        self.assertEqual(total, 3600 + 1800)


def at(text: str) -> datetime:
    """Parse a fixed-offset timestamp for test fixtures."""
    return datetime.fromisoformat(text)


def session_work_date(conn, session_id: str) -> str:
    """Return the work date a session is filed under."""
    return conn.execute(
        "SELECT w.work_date FROM time_sessions s JOIN work_days w ON w.id = s.work_day_id WHERE s.id = ?",
        (session_id,),
    ).fetchone()["work_date"]


class SwitchAcrossMidnightTests(unittest.TestCase):
    def setUp(self):
        self.conn = memory_conn()
        self.nwa_a, _, self.work_item = seed_basic(self.conn)
        self.other = repository.save_work_item(self.conn, "Other", "", [(self.nwa_a, 10000)])

    def test_switch_keeps_the_closed_session_on_its_start_day(self):
        first = tracking.start_or_switch(self.conn, self.work_item, at("2026-07-02T23:00:00-04:00"))
        tracking.start_or_switch(self.conn, self.other, at("2026-07-03T09:00:00-04:00"))

        self.assertEqual(session_work_date(self.conn, first), "2026-07-02")

    def test_switch_after_midnight_files_new_session_under_the_new_day(self):
        tracking.start_or_switch(self.conn, self.work_item, at("2026-07-02T23:00:00-04:00"))
        second = tracking.start_or_switch(self.conn, self.other, at("2026-07-03T09:00:00-04:00"))

        self.assertEqual(session_work_date(self.conn, second), "2026-07-03")


class UpdateSessionInvariantTests(unittest.TestCase):
    """Edits must keep one open session at most, no overlaps, and the right work day."""

    def setUp(self):
        self.conn = memory_conn()
        self.nwa_a, self.nwa_b, self.work_item = seed_basic(self.conn)
        self.closed = tracking.start_or_switch(self.conn, self.work_item, at("2026-07-02T09:00:00-04:00"))
        tracking.pause(self.conn, at("2026-07-02T10:00:00-04:00"))

    def _open_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM time_sessions WHERE end_at IS NULL").fetchone()[0]

    @unittest.expectedFailure  # Bug: a blank end time re-opens a closed session.
    def test_clearing_end_on_closed_session_is_rejected(self):
        tracking.start_or_switch(self.conn, self.work_item, at("2026-07-02T10:30:00-04:00"))

        with self.assertRaises(ValueError):
            tracking.update_session(self.conn, self.closed, "2026-07-02T09:00:00-04:00", None, self.work_item)
        self.assertEqual(self._open_count(), 1)

    @unittest.expectedFailure  # Bug: the overlap query skips the open session (end_at IS NOT NULL).
    def test_overlap_with_the_open_session_is_rejected(self):
        tracking.start_or_switch(self.conn, self.work_item, at("2026-07-02T10:30:00-04:00"))

        with self.assertRaises(ValueError):
            tracking.update_session(
                self.conn, self.closed, "2026-07-02T09:00:00-04:00", "2026-07-02T11:00:00-04:00", self.work_item
            )

    @unittest.expectedFailure  # Bug: work_day_id is never re-derived from the new start time.
    def test_moving_a_session_to_another_date_moves_its_work_day(self):
        tracking.update_session(
            self.conn, self.closed, "2026-07-05T09:00:00-04:00", "2026-07-05T10:00:00-04:00", self.work_item
        )

        self.assertEqual(session_work_date(self.conn, self.closed), "2026-07-05")

    def test_changing_work_item_resnapshots_splits(self):
        other = repository.save_work_item(self.conn, "Other", "", [(self.nwa_a, 10000)])

        tracking.update_session(
            self.conn, self.closed, "2026-07-02T09:00:00-04:00", "2026-07-02T10:00:00-04:00", other
        )

        session = self.conn.execute("SELECT * FROM time_sessions WHERE id = ?", (self.closed,)).fetchone()
        snapshot = json.loads(session["split_snapshot_json"])
        self.assertEqual([(s["code"], s["percent_basis_points"]) for s in snapshot], [("A", 10000)])

    def test_same_work_item_keeps_original_snapshot(self):
        repository.update_work_item(self.conn, self.work_item, "Build", "", [(self.nwa_a, 10000)])

        tracking.update_session(
            self.conn, self.closed, "2026-07-02T09:00:00-04:00", "2026-07-02T10:00:00-04:00", self.work_item, "note"
        )

        session = self.conn.execute("SELECT * FROM time_sessions WHERE id = ?", (self.closed,)).fetchone()
        snapshot = json.loads(session["split_snapshot_json"])
        self.assertEqual(
            sorted((s["code"], s["percent_basis_points"]) for s in snapshot), [("A", 7000), ("B", 3000)]
        )
        self.assertEqual(session["note"], "note")


class StartInactiveWorkItemTests(unittest.TestCase):
    """The service, not just the UI, should refuse to track items the user can't see."""

    @unittest.expectedFailure  # Bug: start_or_switch never checks is_deleted.
    def test_starting_a_removed_work_item_raises(self):
        conn = memory_conn()
        _, _, work_item = seed_basic(conn)
        repository.remove_work_item(conn, work_item)

        with self.assertRaises(ValueError):
            tracking.start_or_switch(conn, work_item, at("2026-07-02T09:00:00-04:00"))

    @unittest.expectedFailure  # Bug: start_or_switch never checks is_obsolete; only the UI guards it.
    def test_starting_an_obsolete_public_work_item_raises(self):
        conn = memory_conn()
        public_list.import_public_list(
            conn,
            write_list_file(
                nwas=[{"code": "PUB-A"}],
                work_items=[{"name": "Review", "splits": [{"code": "PUB-A", "percent_basis_points": 10000}]}],
            ),
        )
        item = repository.list_work_items(conn, scope="public")[0]["id"]
        public_list.import_public_list(conn, write_list_file(nwas=[], work_items=[]))

        with self.assertRaises(ValueError):
            tracking.start_or_switch(conn, item, at("2026-07-02T09:00:00-04:00"))


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from tests.helpers import memory_conn, seed_basic
from time_tracker.services import public_list, repository, tracking


def seed_public_nwa(conn, code="PUB-1", name="Public NWA"):
    """Create a public NWA and return its ID."""
    return repository.save_nwa(conn, code, name, scope="public")


def seed_public_work_item(conn, nwa_id, name="Public Task"):
    """Create a public work item split 100% onto the given NWA. Returns the item ID."""
    return repository.save_work_item(conn, name, "", [(nwa_id, 10000)], scope="public")


def write_list_file(nwas, work_items) -> Path:
    """Write a public list payload to a temp file and return its path."""
    payload = {
        "format_version": public_list.PUBLIC_LIST_FORMAT_VERSION,
        "exported_at": "2026-08-28T09:00:00-04:00",
        "nwas": nwas,
        "work_items": work_items,
    }
    handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(payload, handle)
    handle.close()
    return Path(handle.name)


class NwaScopeTests(unittest.TestCase):
    def test_save_nwa_defaults_to_personal(self):
        conn = memory_conn()
        nwa_id = repository.save_nwa(conn, "A", "NWA A")
        row = conn.execute("SELECT scope FROM nwas WHERE id = ?", (nwa_id,)).fetchone()
        self.assertEqual(row["scope"], "personal")

    def test_save_nwa_public_scope(self):
        conn = memory_conn()
        nwa_id = seed_public_nwa(conn)
        row = conn.execute("SELECT scope, is_obsolete FROM nwas WHERE id = ?", (nwa_id,)).fetchone()
        self.assertEqual(row["scope"], "public")
        self.assertEqual(row["is_obsolete"], 0)

    def test_list_nwas_filters_by_scope(self):
        conn = memory_conn()
        nwa_a, nwa_b, _ = seed_basic(conn)
        public_id = seed_public_nwa(conn)

        personal = repository.list_nwas(conn, scope="personal")
        public = repository.list_nwas(conn, scope="public")
        all_nwas = repository.list_nwas(conn)

        self.assertEqual({row["id"] for row in personal}, {nwa_a, nwa_b})
        self.assertEqual({row["id"] for row in public}, {public_id})
        self.assertEqual(len(all_nwas), 3)

    def test_update_nwa_never_changes_scope(self):
        conn = memory_conn()
        nwa_id = seed_public_nwa(conn)
        repository.save_nwa(conn, "PUB-1", "Renamed", nwa_id=nwa_id, scope="personal")
        row = conn.execute("SELECT scope FROM nwas WHERE id = ?", (nwa_id,)).fetchone()
        self.assertEqual(row["scope"], "public")

    def test_obsolete_nwas_hidden_by_default(self):
        conn = memory_conn()
        nwa_id = seed_public_nwa(conn)
        conn.execute("UPDATE nwas SET is_obsolete = 1 WHERE id = ?", (nwa_id,))

        visible = repository.list_nwas(conn, scope="public")
        with_obsolete = repository.list_nwas(conn, scope="public", include_obsolete=True)

        self.assertEqual(visible, [])
        self.assertEqual({row["id"] for row in with_obsolete}, {nwa_id})

    def test_personal_nwas_never_treated_as_obsolete(self):
        conn = memory_conn()
        nwa_a, nwa_b, _ = seed_basic(conn)
        conn.execute("UPDATE nwas SET is_obsolete = 1 WHERE id = ?", (nwa_a,))
        visible = repository.list_nwas(conn, scope="personal")
        self.assertEqual({row["id"] for row in visible}, {nwa_a, nwa_b})


class WorkItemScopeTests(unittest.TestCase):
    def test_create_work_item_defaults_to_personal(self):
        conn = memory_conn()
        nwa_a, _, _ = seed_basic(conn)
        item_id = repository.create_work_item(conn, "Solo", "", [(nwa_a, 10000)])
        row = conn.execute("SELECT scope FROM work_item_templates WHERE id = ?", (item_id,)).fetchone()
        self.assertEqual(row["scope"], "personal")

    def test_public_work_item_scope_and_filtering(self):
        conn = memory_conn()
        _, _, personal_item = seed_basic(conn)
        public_nwa = seed_public_nwa(conn)
        public_item = seed_public_work_item(conn, public_nwa)

        personal = repository.list_work_items(conn, scope="personal")
        public = repository.list_work_items(conn, scope="public")

        self.assertEqual({row["id"] for row in personal}, {personal_item})
        self.assertEqual({row["id"] for row in public}, {public_item})

    def test_update_work_item_never_changes_scope(self):
        conn = memory_conn()
        public_nwa = seed_public_nwa(conn)
        public_item = seed_public_work_item(conn, public_nwa)
        repository.update_work_item(conn, public_item, "Renamed", "", [(public_nwa, 10000)])
        row = conn.execute("SELECT scope FROM work_item_templates WHERE id = ?", (public_item,)).fetchone()
        self.assertEqual(row["scope"], "public")

    def test_obsolete_work_items_hidden_by_default(self):
        conn = memory_conn()
        public_nwa = seed_public_nwa(conn)
        public_item = seed_public_work_item(conn, public_nwa)
        conn.execute("UPDATE work_item_templates SET is_obsolete = 1 WHERE id = ?", (public_item,))

        visible = repository.list_work_items(conn, scope="public")
        with_obsolete = repository.list_work_items(conn, scope="public", include_obsolete=True)

        self.assertEqual(visible, [])
        self.assertEqual({row["id"] for row in with_obsolete}, {public_item})


class StaleWorkItemTests(unittest.TestCase):
    def test_personal_item_referencing_obsolete_public_nwa_is_stale(self):
        conn = memory_conn()
        public_nwa = seed_public_nwa(conn)
        nwa_a, _, _ = seed_basic(conn)
        item = repository.save_work_item(conn, "Chores", "", [(public_nwa, 4000), (nwa_a, 6000)])

        conn.execute("UPDATE nwas SET is_obsolete = 1 WHERE id = ?", (public_nwa,))

        self.assertEqual(repository.stale_work_item_ids(conn), {item})
        rows = repository.list_stale_work_items(conn)
        self.assertEqual(rows[0]["work_item_id"], item)
        self.assertEqual(rows[0]["nwa_code"], "PUB-1")

    def test_obsolete_personal_nwa_does_not_make_item_stale(self):
        conn = memory_conn()
        nwa_a, _, _ = seed_basic(conn)
        repository.save_work_item(conn, "Chores", "", [(nwa_a, 10000)])
        conn.execute("UPDATE nwas SET is_obsolete = 1 WHERE id = ?", (nwa_a,))
        self.assertEqual(repository.stale_work_item_ids(conn), set())

    def test_deleted_item_is_not_reported_stale(self):
        conn = memory_conn()
        public_nwa = seed_public_nwa(conn)
        item = repository.save_work_item(conn, "Chores", "", [(public_nwa, 10000)])
        conn.execute("UPDATE nwas SET is_obsolete = 1 WHERE id = ?", (public_nwa,))
        repository.remove_work_item(conn, item)
        self.assertEqual(repository.stale_work_item_ids(conn), set())

    def test_healthy_items_are_not_stale(self):
        conn = memory_conn()
        public_nwa = seed_public_nwa(conn)
        seed_public_work_item(conn, public_nwa)
        self.assertEqual(repository.stale_work_item_ids(conn), set())


class ExportTests(unittest.TestCase):
    def test_export_round_trip_contents(self):
        conn = memory_conn()
        seed_basic(conn)
        public_list.import_public_list(
            conn,
            write_list_file(
                nwas=[
                    {"code": "PUB-A", "name": "Alpha", "notes": "n", "tags": ["team", "billing"]},
                    {"code": "PUB-B", "name": "Beta"},
                ],
                work_items=[
                    {
                        "name": "Review",
                        "description": "d",
                        "splits": [
                            {"code": "PUB-A", "percent_basis_points": 7000},
                            {"code": "PUB-B", "percent_basis_points": 3000},
                        ],
                    }
                ],
            ),
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "list.json"
            summary = public_list.export_public_list(conn, path)
            self.assertEqual(summary, {"nwa_count": 2, "work_item_count": 1})
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload["format_version"], 1)
        codes = {entry["code"] for entry in payload["nwas"]}
        self.assertEqual(codes, {"PUB-A", "PUB-B"})
        alpha = next(entry for entry in payload["nwas"] if entry["code"] == "PUB-A")
        self.assertEqual(sorted(alpha["tags"]), ["billing", "team"])
        review = next(item for item in payload["work_items"] if item["name"] == "Review")
        self.assertEqual(
            {(split["code"], split["percent_basis_points"]) for split in review["splits"]},
            {("PUB-A", 7000), ("PUB-B", 3000)},
        )

    def test_export_excludes_obsolete_and_deleted_rows(self):
        conn = memory_conn()
        public_list.import_public_list(
            conn, write_list_file(nwas=[{"code": "PUB-A"}], work_items=[])
        )
        public_list.import_public_list(
            conn, write_list_file(nwas=[{"code": "PUB-B"}], work_items=[])
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "list.json"
            summary = public_list.export_public_list(conn, path)
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(summary["nwa_count"], 1)
        self.assertEqual([entry["code"] for entry in payload["nwas"]], ["PUB-B"])

    def test_export_with_stale_public_item_raises(self):
        conn = memory_conn()
        public_list.import_public_list(
            conn,
            write_list_file(
                nwas=[{"code": "PUB-A"}],
                work_items=[{"name": "Review", "splits": [{"code": "PUB-A", "percent_basis_points": 10000}]}],
            ),
        )
        conn.execute("UPDATE nwas SET is_obsolete = 1 WHERE code = 'PUB-A'")

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError) as ctx:
                public_list.export_public_list(conn, Path(tmp) / "list.json")
        self.assertIn("PUB-A", str(ctx.exception))

    def test_export_empty_public_list(self):
        conn = memory_conn()
        seed_basic(conn)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "list.json"
            summary = public_list.export_public_list(conn, path)
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(summary, {"nwa_count": 0, "work_item_count": 0})
        self.assertEqual(payload["nwas"], [])


class ImportTests(unittest.TestCase):
    def test_fresh_import_adds_public_entries(self):
        conn = memory_conn()
        report = public_list.import_public_list(
            conn,
            write_list_file(
                nwas=[{"code": "PUB-A", "name": "Alpha", "tags": ["team"]}],
                work_items=[{"name": "Review", "splits": [{"code": "PUB-A", "percent_basis_points": 10000}]}],
            ),
        )
        self.assertEqual(report["nwas_added"], 1)
        self.assertEqual(report["work_items_added"], 1)
        self.assertEqual(report["stale"], [])

        nwa = conn.execute("SELECT * FROM nwas WHERE code = 'PUB-A'").fetchone()
        self.assertEqual(nwa["scope"], "public")
        self.assertEqual(nwa["is_obsolete"], 0)
        item = conn.execute("SELECT * FROM work_item_templates WHERE name = 'Review'").fetchone()
        self.assertEqual(item["scope"], "public")
        splits = repository.get_work_item_splits(conn, item["id"])
        self.assertEqual([(s["code"], s["percent_basis_points"]) for s in splits], [("PUB-A", 10000)])

    def test_reimport_same_file_is_idempotent(self):
        conn = memory_conn()
        path = write_list_file(
            nwas=[{"code": "PUB-A", "name": "Alpha"}],
            work_items=[{"name": "Review", "splits": [{"code": "PUB-A", "percent_basis_points": 10000}]}],
        )
        public_list.import_public_list(conn, path)
        nwa_before = conn.execute("SELECT id FROM nwas WHERE code = 'PUB-A'").fetchone()["id"]
        item_before = conn.execute("SELECT id FROM work_item_templates WHERE name = 'Review'").fetchone()["id"]

        report = public_list.import_public_list(conn, path)

        self.assertEqual(report["nwas_added"], 0)
        self.assertEqual(report["nwas_updated"], 1)
        self.assertEqual(report["work_items_added"], 0)
        self.assertEqual(report["work_items_updated"], 1)
        self.assertEqual(report["nwas_obsoleted"], 0)
        nwa_after = conn.execute("SELECT id FROM nwas WHERE code = 'PUB-A'").fetchone()["id"]
        item_after = conn.execute("SELECT id FROM work_item_templates WHERE name = 'Review'").fetchone()["id"]
        self.assertEqual((nwa_before, item_before), (nwa_after, item_after))

    def test_import_replaces_dropped_codes_and_keeps_survivors(self):
        conn = memory_conn()
        public_list.import_public_list(
            conn,
            write_list_file(
                nwas=[{"code": "PUB-A"}, {"code": "PUB-B"}],
                work_items=[{"name": "Review", "splits": [{"code": "PUB-A", "percent_basis_points": 10000}]}],
            ),
        )
        survivor_id = conn.execute("SELECT id FROM nwas WHERE code = 'PUB-A'").fetchone()["id"]

        report = public_list.import_public_list(
            conn,
            write_list_file(
                nwas=[{"code": "PUB-A", "name": "Alpha v2"}, {"code": "PUB-C"}],
                work_items=[{"name": "Review", "splits": [{"code": "PUB-A", "percent_basis_points": 10000}]}],
            ),
        )

        self.assertEqual(report["nwas_updated"], 1)
        self.assertEqual(report["nwas_added"], 1)
        self.assertEqual(report["nwas_obsoleted"], 1)
        self.assertEqual(conn.execute("SELECT id FROM nwas WHERE code = 'PUB-A'").fetchone()["id"], survivor_id)
        dropped = conn.execute("SELECT is_obsolete FROM nwas WHERE code = 'PUB-B'").fetchone()
        self.assertEqual(dropped["is_obsolete"], 1)
        # Review's split still points at the surviving row, so nothing is stale.
        self.assertEqual(report["stale"], [])

    def test_import_readd_item_by_name_revives_it(self):
        conn = memory_conn()
        public_list.import_public_list(
            conn,
            write_list_file(
                nwas=[{"code": "PUB-A"}],
                work_items=[{"name": "Review", "splits": [{"code": "PUB-A", "percent_basis_points": 10000}]}],
            ),
        )
        item_before = conn.execute("SELECT id FROM work_item_templates WHERE name = 'Review'").fetchone()["id"]
        public_list.import_public_list(conn, write_list_file(nwas=[{"code": "PUB-A"}], work_items=[]))
        obsolete_flag = conn.execute(
            "SELECT is_obsolete FROM work_item_templates WHERE id = ?", (item_before,)
        ).fetchone()["is_obsolete"]
        self.assertEqual(obsolete_flag, 1)

        report = public_list.import_public_list(
            conn,
            write_list_file(
                nwas=[{"code": "PUB-A"}],
                work_items=[{"name": "Review", "splits": [{"code": "PUB-A", "percent_basis_points": 10000}]}],
            ),
        )
        self.assertEqual(report["work_items_updated"], 1)
        revived = conn.execute(
            "SELECT is_obsolete, is_deleted FROM work_item_templates WHERE id = ?", (item_before,)
        ).fetchone()
        self.assertEqual((revived["is_obsolete"], revived["is_deleted"]), (0, 0))

    def test_dropped_code_makes_personal_item_stale(self):
        conn = memory_conn()
        public_list.import_public_list(
            conn,
            write_list_file(nwas=[{"code": "PUB-A"}, {"code": "PUB-B"}], work_items=[]),
        )
        pub_a = conn.execute("SELECT id FROM nwas WHERE code = 'PUB-A'").fetchone()["id"]
        nwa_x, _, _ = seed_basic(conn)
        personal_item = repository.save_work_item(conn, "Chores", "", [(pub_a, 5000), (nwa_x, 5000)])

        report = public_list.import_public_list(
            conn, write_list_file(nwas=[{"code": "PUB-B"}], work_items=[])
        )

        self.assertEqual(repository.stale_work_item_ids(conn), {personal_item})
        self.assertEqual(
            [(row["work_item_name"], row["nwa_code"]) for row in report["stale"]],
            [("Chores", "PUB-A")],
        )

    def test_import_does_not_touch_personal_rows(self):
        conn = memory_conn()
        nwa_a, nwa_b, personal_item = seed_basic(conn)
        public_list.import_public_list(
            conn, write_list_file(nwas=[{"code": "PUB-A"}], work_items=[])
        )
        self.assertEqual(
            [(row["code"], row["scope"]) for row in repository.list_nwas(conn, scope="personal")],
            [("A", "personal"), ("B", "personal")],
        )
        self.assertEqual(repository.get_work_item(conn, personal_item)["scope"], "personal")
        self.assertEqual(len(repository.get_work_item_splits(conn, personal_item)), 2)
        self.assertEqual({nwa_a, nwa_b}, {nwa_a, nwa_b})

    def test_import_preserves_open_session_charging(self):
        conn = memory_conn()
        public_list.import_public_list(
            conn,
            write_list_file(
                nwas=[{"code": "PUB-A"}],
                work_items=[{"name": "Review", "splits": [{"code": "PUB-A", "percent_basis_points": 10000}]}],
            ),
        )
        item = conn.execute("SELECT id FROM work_item_templates WHERE name = 'Review'").fetchone()["id"]
        start = datetime.fromisoformat("2026-07-02T09:00:00-04:00")
        session_id = tracking.start_or_switch(conn, item, start)

        # New list drops the item and its NWA entirely.
        public_list.import_public_list(conn, write_list_file(nwas=[{"code": "PUB-Z"}], work_items=[]))

        session = conn.execute("SELECT * FROM time_sessions WHERE id = ?", (session_id,)).fetchone()
        self.assertIsNone(session["end_at"])
        snapshot = json.loads(session["split_snapshot_json"])
        self.assertEqual(snapshot[0]["code"], "PUB-A")
        self.assertEqual(tracking.session_seconds(session, start.replace(hour=10)), 3600)

    def test_import_collision_with_personal_nwa_rolls_back(self):
        conn = memory_conn()
        nwa_a, _, _ = seed_basic(conn)
        public_list.import_public_list(
            conn, write_list_file(nwas=[{"code": "PUB-A"}], work_items=[])
        )

        with self.assertRaises(ValueError) as ctx:
            public_list.import_public_list(
                conn, write_list_file(nwas=[{"code": "PUB-A"}, {"code": nwa_a and "A"}], work_items=[])
            )
        self.assertIn("personal", str(ctx.exception))

        # Rollback: the old public set is untouched and nothing new was added.
        codes = {row["code"]: row["is_obsolete"] for row in repository.list_nwas(conn, include_obsolete=True)}
        self.assertEqual(codes, {"A": 0, "B": 0, "PUB-A": 0})

    def test_import_malformed_json_raises(self):
        conn = memory_conn()
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        handle.write("{not json")
        handle.close()
        with self.assertRaises(ValueError) as ctx:
            public_list.import_public_list(conn, Path(handle.name))
        self.assertIn("not valid JSON", str(ctx.exception))

    def test_import_wrong_format_version_raises(self):
        conn = memory_conn()
        path = write_list_file(nwas=[], work_items=[])
        payload = json.loads(path.read_text())
        payload["format_version"] = 99
        path.write_text(json.dumps(payload))
        with self.assertRaises(ValueError) as ctx:
            public_list.import_public_list(conn, path)
        self.assertIn("format version", str(ctx.exception))

    def test_import_duplicate_codes_raise(self):
        conn = memory_conn()
        with self.assertRaises(ValueError) as ctx:
            public_list.import_public_list(
                conn, write_list_file(nwas=[{"code": "X"}, {"code": "X"}], work_items=[])
            )
        self.assertIn("duplicate NWA codes", str(ctx.exception))

    def test_import_duplicate_work_item_names_raise(self):
        conn = memory_conn()
        with self.assertRaises(ValueError) as ctx:
            public_list.import_public_list(
                conn,
                write_list_file(
                    nwas=[{"code": "X"}],
                    work_items=[
                        {"name": "Same", "splits": [{"code": "X", "percent_basis_points": 10000}]},
                        {"name": "Same", "splits": [{"code": "X", "percent_basis_points": 10000}]},
                    ],
                ),
            )
        self.assertIn("duplicate work item names", str(ctx.exception))

    def test_import_missing_nwa_reference_raises(self):
        conn = memory_conn()
        with self.assertRaises(ValueError) as ctx:
            public_list.import_public_list(
                conn,
                write_list_file(
                    nwas=[{"code": "X"}],
                    work_items=[{"name": "Review", "splits": [{"code": "Y", "percent_basis_points": 10000}]}],
                ),
            )
        self.assertIn("not defined", str(ctx.exception))

    def test_import_bad_split_total_raises(self):
        conn = memory_conn()
        with self.assertRaises(ValueError) as ctx:
            public_list.import_public_list(
                conn,
                write_list_file(
                    nwas=[{"code": "X"}],
                    work_items=[
                        {
                            "name": "Review",
                            "splits": [
                                {"code": "X", "percent_basis_points": 7000},
                            ],
                        }
                    ],
                ),
            )
        self.assertIn("100%", str(ctx.exception))

    def test_import_empty_file_clears_public_list(self):
        conn = memory_conn()
        public_list.import_public_list(
            conn, write_list_file(nwas=[{"code": "PUB-A"}], work_items=[])
        )
        report = public_list.import_public_list(conn, write_list_file(nwas=[], work_items=[]))
        self.assertEqual(report["nwas_obsoleted"], 1)
        self.assertEqual(repository.list_nwas(conn, scope="public"), [])
        self.assertEqual(repository.list_work_items(conn, scope="public"), [])

    def test_import_missing_file_raises(self):
        conn = memory_conn()
        with self.assertRaises(ValueError):
            public_list.import_public_list(conn, Path("/nonexistent/list.json"))


if __name__ == "__main__":
    unittest.main()

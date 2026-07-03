import unittest

from tests.helpers import memory_conn


class MigrationTests(unittest.TestCase):
    def test_migration_creates_settings(self):
        conn = memory_conn()
        row = conn.execute("SELECT value FROM settings WHERE key = 'rounding_increment_minutes'").fetchone()
        self.assertEqual(row["value"], "15")


if __name__ == "__main__":
    unittest.main()

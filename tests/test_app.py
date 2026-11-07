import sys
import unittest
from pathlib import Path
from unittest import mock

from time_tracker import app


class ReportCallbackErrorTests(unittest.TestCase):
    def test_logs_the_error_and_shows_it_with_the_log_path(self):
        shown = []
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            exc_info = sys.exc_info()

        with mock.patch.object(app, "log_path", return_value=Path("/logs/app.log")):
            with self.assertLogs(level="ERROR") as logs:
                app.report_callback_error(*exc_info, show_error=lambda title, message: shown.append(message))

        self.assertIn("Unhandled error in a UI callback", logs.output[0])
        self.assertIn("RuntimeError: boom", logs.output[0])
        self.assertEqual(len(shown), 1)
        self.assertIn("boom", shown[0])
        self.assertIn(str(Path("/logs/app.log")), shown[0])


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from time_tracker.util import desktop


class OpenFolderTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = Path(self._tmp.name)

    def test_missing_folder_raises(self):
        with self.assertRaises(FileNotFoundError):
            desktop.open_folder(self.folder / "nope")

    def test_linux_uses_xdg_open(self):
        with mock.patch.object(desktop.sys, "platform", "linux"), mock.patch.object(desktop.subprocess, "Popen") as popen:
            desktop.open_folder(self.folder)
        popen.assert_called_once_with(["xdg-open", str(self.folder)])

    def test_mac_uses_open(self):
        with mock.patch.object(desktop.sys, "platform", "darwin"), mock.patch.object(desktop.subprocess, "Popen") as popen:
            desktop.open_folder(self.folder)
        popen.assert_called_once_with(["open", str(self.folder)])

    def test_windows_uses_startfile(self):
        startfile = mock.Mock()
        with mock.patch.object(desktop.sys, "platform", "win32"), \
                mock.patch.object(desktop.os, "startfile", startfile, create=True):
            desktop.open_folder(self.folder)
        startfile.assert_called_once_with(self.folder)


if __name__ == "__main__":
    unittest.main()

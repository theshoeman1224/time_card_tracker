import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from time_tracker import paths


def platform(name: str):
    """Pretend to run on the given sys.platform value."""
    return mock.patch.object(paths.sys, "platform", name)


@contextmanager
def env(**values):
    """Patch the environment for one test: str values set a variable, None removes it."""
    with mock.patch.dict(os.environ):
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield


class AppDataDirTests(unittest.TestCase):
    def test_linux_uses_xdg_data_home(self):
        with platform("linux"), env(XDG_DATA_HOME="/xdg/data"):
            self.assertEqual(paths.app_data_dir(), Path("/xdg/data") / paths.APP_SLUG)

    def test_linux_falls_back_to_local_share(self):
        with platform("linux"), env(XDG_DATA_HOME=None):
            self.assertEqual(paths.app_data_dir(), Path.home() / ".local" / "share" / paths.APP_SLUG)

    def test_windows_uses_appdata(self):
        with platform("win32"), env(APPDATA="/fake/AppData/Roaming"):
            self.assertEqual(paths.app_data_dir(), Path("/fake/AppData/Roaming") / paths.APP_NAME)

    def test_windows_without_appdata_falls_back_to_home(self):
        with platform("win32"), env(APPDATA=None):
            self.assertEqual(paths.app_data_dir(), Path.home() / "AppData" / "Roaming" / paths.APP_NAME)


class AppStateDirTests(unittest.TestCase):
    def test_linux_uses_xdg_state_home(self):
        with platform("linux"), env(XDG_STATE_HOME="/xdg/state"):
            self.assertEqual(paths.app_state_dir(), Path("/xdg/state") / paths.APP_SLUG)

    def test_linux_falls_back_to_local_state(self):
        with platform("linux"), env(XDG_STATE_HOME=None):
            self.assertEqual(paths.app_state_dir(), Path.home() / ".local" / "state" / paths.APP_SLUG)

    def test_windows_state_is_the_data_dir(self):
        with platform("win32"), env(APPDATA="/fake/AppData/Roaming"):
            self.assertEqual(paths.app_state_dir(), paths.app_data_dir())


class EnsureAppDirsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.data_home = root / "data"
        self.state_home = root / "state"

    def tearDown(self):
        self._tmp.cleanup()

    def _env(self):
        return env(XDG_DATA_HOME=str(self.data_home), XDG_STATE_HOME=str(self.state_home))

    def test_creates_every_directory(self):
        with platform("linux"), self._env():
            dirs = paths.ensure_app_dirs()

        data = self.data_home / paths.APP_SLUG
        state = self.state_home / paths.APP_SLUG
        self.assertEqual(
            dirs,
            {
                "data": data,
                "state": state,
                "logs": state / "logs",
                "exports": data / "exports",
                "backups": data / "backups",
            },
        )
        for path in dirs.values():
            self.assertTrue(path.is_dir(), path)

    def test_is_safe_to_call_twice(self):
        with platform("linux"), self._env():
            self.assertEqual(paths.ensure_app_dirs(), paths.ensure_app_dirs())

    def test_database_and_log_paths(self):
        with platform("linux"), self._env():
            self.assertEqual(
                paths.database_path(), self.data_home / paths.APP_SLUG / "time_card_tracker.sqlite3"
            )
            self.assertEqual(
                paths.log_path(), self.state_home / paths.APP_SLUG / "logs" / "time_card_tracker.log"
            )


if __name__ == "__main__":
    unittest.main()

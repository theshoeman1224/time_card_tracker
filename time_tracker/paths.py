import os
import sys
from pathlib import Path


APP_NAME = "TimeCardTracker"
APP_SLUG = "time-card-tracker"


def app_data_dir() -> Path:
    """Per-user data directory: %APPDATA% on Windows, XDG data home elsewhere."""
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / APP_NAME
        return Path.home() / "AppData" / "Roaming" / APP_NAME
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_SLUG


def app_state_dir() -> Path:
    """Per-user state directory: same as data on Windows, XDG state home elsewhere."""
    if sys.platform.startswith("win"):
        return app_data_dir()
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / APP_SLUG


def ensure_app_dirs() -> dict[str, Path]:
    """Create data, state, log, export, and backup directories if missing, and return them."""
    data = app_data_dir()
    state = app_state_dir()
    paths = {
        "data": data,
        "state": state,
        "logs": state / "logs",
        "exports": data / "exports",
        "backups": data / "backups",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def database_path() -> Path:
    """Path to the SQLite database inside the data directory."""
    return ensure_app_dirs()["data"] / "time_card_tracker.sqlite3"


def log_path() -> Path:
    """Path to the log file inside the state directory."""
    return ensure_app_dirs()["logs"] / "time_card_tracker.log"

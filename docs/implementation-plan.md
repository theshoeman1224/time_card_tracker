# Time Card Tracker Implementation Plan

Runtime implementation uses Python 3.11 standard library modules only:
`tkinter`, `sqlite3`, `csv`, `pathlib`, `datetime`, `zoneinfo`, `logging`, and `unittest`.

Run from source:

```bash
python time_tracker_app.py
```

The database is stored in the user app-data directory. On Windows this is
`%APPDATA%\TimeCardTracker\time_card_tracker.sqlite3`; on Linux it is
`~/.local/share/time-card-tracker/time_card_tracker.sqlite3`.

Optional Windows packaging can be performed on a separate build machine with
PyInstaller as a build-time-only dependency:

```bash
pyinstaller --onefile --windowed --name TimeCardTracker time_tracker_app.py
```

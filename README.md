# Time Card Tracker

Local, standard-library-first desktop time tracking app for Python 3.11.

## Run

```bash
python time_tracker_app.py
```

On systems where `python` is not available:

```bash
python3 time_tracker_app.py
```

No `pip install` is required.

## Test

```bash
python -m unittest discover
```

or:

```bash
python3 -m unittest discover
```

## Data

The app stores data in SQLite under the current user's app-data directory.

- Windows: `%APPDATA%\TimeCardTracker\time_card_tracker.sqlite3`
- Linux: `~/.local/share/time-card-tracker/time_card_tracker.sqlite3`

## Optional Windows Packaging

Packaging is optional and uses a build-time-only dependency on a separate
Windows machine:

```bash
pyinstaller --onefile --windowed --name TimeCardTracker time_tracker_app.py
```

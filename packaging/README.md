# Packaging

The application has no third-party runtime dependencies. Packaging is optional.

Recommended Windows build command on a separate machine with PyInstaller installed:

```bash
pyinstaller --onefile --windowed --name TimeCardTracker time_tracker_app.py
```

Keep the SQLite database outside the executable. The app writes user data under
the normal per-user app-data directory.

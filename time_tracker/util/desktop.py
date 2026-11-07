from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def open_folder(folder: Path) -> None:
    """Open a folder in the system file manager.

    Raises OSError if the folder is missing or no file manager could be started.
    """
    folder = Path(folder)
    if not folder.is_dir():
        raise FileNotFoundError(f"Folder not found: {folder}")
    if sys.platform.startswith("win"):
        os.startfile(folder)  # noqa: S606 - opens Explorer on a folder we own
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(folder)])  # noqa: S603, S607
    else:
        subprocess.Popen(["xdg-open", str(folder)])  # noqa: S603, S607

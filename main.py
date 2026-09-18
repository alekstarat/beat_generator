#!/usr/bin/env python3
"""
Beat Generator — desktop prototype (Python + PySide6).

Architecture:
  core/   — pure generation engine (no Qt). Ready to port to C++/JUCE.
  ui/     — PySide6 front-end only.

Run:
  python main.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from project root without installing the package.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont , QIcon

from ui.main_window import MainWindow

def resource_path(relative_path: str) -> Path:
    if getattr(sys, 'frozen', False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / relative_path

    return Path(__file__).resolve().parent / relative_path

def main():
    app = QApplication(sys.argv)

    app.setApplicationName("Beat Generator")
    app.setOrganizationName("BeatGen")

    icon_path = resource_path("icon.ico")
    app.setWindowIcon(QIcon(str(icon_path)))

    font = QFont("Segoe UI", 10)
    app.setFont(font)

    win = MainWindow()
    win.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

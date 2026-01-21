"""Application entry for the mkgui runtime UI."""

from __future__ import annotations

import sys
from typing import Any

from PyQt6.QtWidgets import QApplication

from .ui.main_window import MainWindow


def run_app(spec: dict[str, Any]) -> int:
    """Launch the GUI runtime for a spec."""
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow(spec)
    window.show()
    return app.exec()

"""Output console widget for showing stdout/stderr and results."""

from __future__ import annotations

from PyQt6.QtWidgets import QPlainTextEdit


class OutputConsole(QPlainTextEdit):
    """Read-only console output."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)

    def append_text(self, text: str) -> None:
        """Append text to the console."""
        if text.endswith("\n"):
            text = text[:-1]
        self.appendPlainText(text)

"""Preflight panel showing runtime context information."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QWidget,
)


class PreflightPanel(QGroupBox):
    """Show key context details for the current spec."""

    def __init__(self, spec: dict[str, Any], parent=None) -> None:
        super().__init__("Preflight", parent)
        self._warnings = list(spec.get("warnings") or [])

        layout = QFormLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        layout.addRow("Python", self._make_value(sys.executable or "python"))

        project_root = spec.get("project_root") or ""
        layout.addRow("Project Root", self._make_value(project_root or "(none)"))
        layout.addRow("Sys.path +", self._make_value(self._sys_path_root(project_root)))

        analysis_mode = spec.get("analysis_mode") or "(unknown)"
        layout.addRow("Analysis Mode", self._make_value(str(analysis_mode)))

        module_count = len(spec.get("modules") or [])
        layout.addRow("Modules", self._make_value(str(module_count)))

        layout.addRow("Warnings", self._warnings_row())

    def _make_value(self, text: str) -> QLabel:
        label = QLabel(text, self)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setWordWrap(True)
        return label

    def _sys_path_root(self, project_root: str) -> str:
        if not project_root:
            return "(none)"
        path = Path(project_root)
        if path.is_file():
            path = path.parent
        return str(path)

    def _warnings_row(self) -> QWidget:
        wrapper = QWidget(self)
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)

        count_label = QLabel(str(len(self._warnings)), wrapper)
        layout.addWidget(count_label)
        layout.addStretch(1)

        if self._warnings:
            button = QPushButton("View", wrapper)
            button.clicked.connect(self._show_warnings)
            layout.addWidget(button)

        return wrapper

    def _show_warnings(self) -> None:
        lines: list[str] = []
        for warning in self._warnings:
            code = warning.get("code", "WARN")
            message = warning.get("message", "")
            file_path = warning.get("file_path") or ""
            line = warning.get("line")
            location = ""
            if file_path:
                location = f"{file_path}:{line}" if line else file_path
            if location:
                lines.append(f"[{code}] {location} - {message}")
            else:
                lines.append(f"[{code}] {message}")

        QMessageBox.information(self, "Analysis Warnings", "\n".join(lines))

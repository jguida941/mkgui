"""Run history table for executed actions."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


@dataclass
class RunRecord:
    """A single run record for history tracking."""
    started_at: str
    action: str
    plan: str
    status: str
    duration_ms: int | None = None
    exit_code: int | None = None


class RunHistory(QWidget):
    """Table widget that tracks action executions."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._table = QTableWidget(0, 6, self)
        self._table.setHorizontalHeaderLabels([
            "Started",
            "Action",
            "Plan",
            "Status",
            "Duration (ms)",
            "Exit",
        ])
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._table.verticalHeader().setVisible(False)

        layout.addWidget(self._table)

    def add_run(self, record: RunRecord) -> int:
        """Append a run record and return its row index."""
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._set_row(row, record)
        return row

    def update_run(self, row: int, record: RunRecord) -> None:
        """Update an existing run row."""
        if row < 0 or row >= self._table.rowCount():
            return
        self._set_row(row, record)

    def _set_row(self, row: int, record: RunRecord) -> None:
        values = [
            record.started_at,
            record.action,
            record.plan,
            record.status,
            "" if record.duration_ms is None else str(record.duration_ms),
            "" if record.exit_code is None else str(record.exit_code),
        ]
        for col, value in enumerate(values):
            item = QTableWidgetItem(value)
            if col in (4, 5):
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, col, item)

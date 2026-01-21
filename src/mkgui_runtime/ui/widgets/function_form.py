"""Dynamic parameter form for action execution."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from PyQt6.QtCore import QDate, QDateTime, QRegularExpression, QTime, Qt
from PyQt6.QtGui import QRegularExpressionValidator
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDateTimeEdit,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTimeEdit,
    QWidget,
    QFileDialog,
)


_MISSING = object()


@dataclass
class FieldAdapter:
    """Adapter for reading and writing a field widget."""
    name: str
    kind: str
    widget_type: str
    widget: QWidget
    getter: Callable[[], Any]
    setter: Callable[[Any], None]
    required: bool
    default: dict[str, Any]


class FilePicker(QWidget):
    """Line edit with a browse button."""

    def __init__(self, parent=None, directory: bool = False) -> None:
        super().__init__(parent)
        self._line_edit = QLineEdit(self)
        self._button = QPushButton("Browse", self)
        self._button.clicked.connect(self._browse)
        self._directory = directory

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._line_edit)
        layout.addWidget(self._button)

    def _browse(self) -> None:
        if self._directory:
            path = QFileDialog.getExistingDirectory(self, "Select Folder")
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Select File")
        if path:
            self._line_edit.setText(path)

    def text(self) -> str:
        return self._line_edit.text()

    def set_text(self, value: str) -> None:
        self._line_edit.setText(value)


class FunctionForm(QWidget):
    """Form widget that renders parameters for an action."""

    def __init__(self, action: dict[str, Any], parent=None) -> None:
        super().__init__(parent)
        self._action = action
        self._fields: list[FieldAdapter] = []

        layout = QFormLayout(self)
        layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        for param in action.get("parameters", []):
            field = self._build_field(param)
            label = QLabel(self._label_text(param), self)
            layout.addRow(label, field.widget)
            self._fields.append(field)

    def _label_text(self, param: dict[str, Any]) -> str:
        name = param.get("name", "")
        required = bool(param.get("required", True))
        return f"{name} *" if required else name

    def _build_field(self, param: dict[str, Any]) -> FieldAdapter:
        widget_type = (param.get("ui") or {}).get("widget") or "line_edit"
        name = param.get("name", "")
        kind = param.get("kind", "")
        required = bool(param.get("required", True))
        default = param.get("default") or {}
        validation = param.get("validation") or {}

        if widget_type == "spin_box":
            widget = QSpinBox(self)
            widget.setRange(
                int(validation.get("min", -999999)),
                int(validation.get("max", 999999)),
            )
            return FieldAdapter(
                name=name,
                kind=kind,
                widget_type=widget_type,
                widget=widget,
                getter=widget.value,
                setter=widget.setValue,
                required=required,
                default=default,
            )

        if widget_type == "double_spin_box":
            widget = QDoubleSpinBox(self)
            widget.setDecimals(6)
            widget.setRange(
                float(validation.get("min", -999999.0)),
                float(validation.get("max", 999999.0)),
            )
            return FieldAdapter(
                name=name,
                kind=kind,
                widget_type=widget_type,
                widget=widget,
                getter=widget.value,
                setter=widget.setValue,
                required=required,
                default=default,
            )

        if widget_type == "check_box":
            widget = QCheckBox(self)
            return FieldAdapter(
                name=name,
                kind=kind,
                widget_type=widget_type,
                widget=widget,
                getter=widget.isChecked,
                setter=widget.setChecked,
                required=required,
                default=default,
            )

        if widget_type == "combo_box":
            widget = QComboBox(self)
            options = list((param.get("ui") or {}).get("options") or [])
            widget.addItems([str(opt) for opt in options])
            widget.setEditable(len(options) == 0)
            return FieldAdapter(
                name=name,
                kind=kind,
                widget_type=widget_type,
                widget=widget,
                getter=widget.currentText,
                setter=widget.setCurrentText,
                required=required,
                default=default,
            )

        if widget_type == "plain_text_edit":
            widget = QPlainTextEdit(self)
            return FieldAdapter(
                name=name,
                kind=kind,
                widget_type=widget_type,
                widget=widget,
                getter=widget.toPlainText,
                setter=widget.setPlainText,
                required=required,
                default=default,
            )

        if widget_type == "json_editor":
            widget = QPlainTextEdit(self)
            widget.setTabChangesFocus(True)
            return FieldAdapter(
                name=name,
                kind=kind,
                widget_type=widget_type,
                widget=widget,
                getter=widget.toPlainText,
                setter=widget.setPlainText,
                required=required,
                default=default,
            )

        if widget_type == "file_picker":
            name_lower = name.lower()
            directory = any(token in name_lower for token in ("dir", "directory", "folder"))
            widget = FilePicker(self, directory=directory)
            return FieldAdapter(
                name=name,
                kind=kind,
                widget_type=widget_type,
                widget=widget,
                getter=widget.text,
                setter=widget.set_text,
                required=required,
                default=default,
            )

        if widget_type == "date_edit":
            widget = QDateEdit(self)
            widget.setDisplayFormat("yyyy-MM-dd")
            widget.setCalendarPopup(True)
            return FieldAdapter(
                name=name,
                kind=kind,
                widget_type=widget_type,
                widget=widget,
                getter=lambda: widget.date().toString(Qt.DateFormat.ISODate),
                setter=lambda value: widget.setDate(
                    QDate.fromString(str(value), Qt.DateFormat.ISODate)
                ),
                required=required,
                default=default,
            )

        if widget_type == "datetime_edit":
            widget = QDateTimeEdit(self)
            widget.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
            widget.setCalendarPopup(True)
            return FieldAdapter(
                name=name,
                kind=kind,
                widget_type=widget_type,
                widget=widget,
                getter=lambda: widget.dateTime().toString(Qt.DateFormat.ISODate),
                setter=lambda value: widget.setDateTime(
                    QDateTime.fromString(str(value), Qt.DateFormat.ISODate)
                ),
                required=required,
                default=default,
            )

        if widget_type == "time_edit":
            widget = QTimeEdit(self)
            widget.setDisplayFormat("HH:mm:ss")
            return FieldAdapter(
                name=name,
                kind=kind,
                widget_type=widget_type,
                widget=widget,
                getter=lambda: widget.time().toString(Qt.DateFormat.ISODate),
                setter=lambda value: widget.setTime(
                    QTime.fromString(str(value), Qt.DateFormat.ISODate)
                ),
                required=required,
                default=default,
            )

        widget = QLineEdit(self)
        if "regex" in validation and validation["regex"]:
            regex = QRegularExpression(str(validation["regex"]))
            widget.setValidator(QRegularExpressionValidator(regex, widget))
        return FieldAdapter(
            name=name,
            kind=kind,
            widget_type=widget_type,
            widget=widget,
            getter=widget.text,
            setter=widget.setText,
            required=required,
            default=default,
        )

    def apply_defaults(self) -> None:
        """Populate fields with literal defaults when available."""
        for field in self._fields:
            default = field.default or {}
            if default.get("present") and default.get("is_literal"):
                literal = default.get("literal")
                value, apply_value = self._coerce_default(field, literal)
                if apply_value:
                    field.setter(value)

    def _coerce_default(self, field: FieldAdapter, literal: Any) -> tuple[Any, bool]:
        """Coerce literal defaults to widget-friendly values."""
        if literal is None:
            return None, False

        widget_type = field.widget_type
        if widget_type in ("line_edit", "file_picker"):
            return str(literal), True

        if widget_type == "plain_text_edit":
            if isinstance(literal, list):
                return "\n".join(str(item) for item in literal), True
            return str(literal), True

        if widget_type == "json_editor":
            if isinstance(literal, str):
                return literal, True
            return json.dumps(literal, indent=2), True

        if widget_type == "combo_box":
            return str(literal), True

        if widget_type == "spin_box":
            try:
                return int(literal), True
            except (TypeError, ValueError):
                return None, False

        if widget_type == "double_spin_box":
            try:
                return float(literal), True
            except (TypeError, ValueError):
                return None, False

        if widget_type == "check_box":
            if isinstance(literal, bool):
                return literal, True
            if isinstance(literal, (int, float)) and literal in (0, 1):
                return bool(literal), True
            if isinstance(literal, str):
                value = literal.strip().lower()
                if value in ("true", "1", "yes", "y", "on"):
                    return True, True
                if value in ("false", "0", "no", "n", "off"):
                    return False, True
            return None, False

        if widget_type in ("date_edit", "datetime_edit", "time_edit"):
            return str(literal), True

        return literal, True

    def collect_values(self) -> tuple[list[Any], dict[str, Any], list[str]]:
        """Collect positional args and kwargs from the form."""
        args: list[Any] = []
        kwargs: dict[str, Any] = {}
        errors: list[str] = []
        positional_fields: list[tuple[int, FieldAdapter, Any]] = []

        for field in self._fields:
            raw_value = field.getter()
            value, has_value, error = self._normalize_value(field, raw_value)
            if error:
                errors.append(error)
                continue

            kind = field.kind
            if kind in ("positional_only", "positional_or_keyword"):
                positional_fields.append((len(positional_fields), field, value if has_value else _MISSING))
                continue

            if kind == "var_positional":
                if has_value:
                    if isinstance(value, list):
                        args.extend(value)
                    else:
                        errors.append(f"{field.name} must be a list")
                continue

            if kind == "var_keyword":
                if has_value:
                    if isinstance(value, dict):
                        kwargs.update(value)
                    else:
                        errors.append(f"{field.name} must be a JSON object")
                continue

            if kind == "keyword_only":
                if has_value:
                    kwargs[field.name] = value
                continue

            if has_value:
                kwargs[field.name] = value

        if positional_fields:
            args = self._build_positional_args(positional_fields, errors)

        return args, kwargs, errors

    def _build_positional_args(
        self,
        fields: list[tuple[int, FieldAdapter, Any]],
        errors: list[str],
    ) -> list[Any]:
        values = [value for _, _, value in fields]
        last_provided = None
        for idx, value in enumerate(values):
            if value is not _MISSING:
                last_provided = idx
        if last_provided is None:
            return []
        for idx, value in enumerate(values):
            if value is _MISSING and idx < last_provided:
                errors.append("Missing positional value before later arguments")
                return []
        trimmed = values[: last_provided + 1]
        return [value for value in trimmed if value is not _MISSING]

    def _normalize_value(
        self,
        field: FieldAdapter,
        raw_value: Any,
    ) -> tuple[Any, bool, str | None]:
        if field.widget_type in ("plain_text_edit", "json_editor", "line_edit", "file_picker"):
            if isinstance(raw_value, str):
                raw_value = raw_value.strip()

        if raw_value in ("", None):
            default = field.default or {}
            if default.get("present") and default.get("is_literal"):
                literal = default.get("literal")
                if literal is None:
                    return None, False, None
                return literal, True, None
            if field.required:
                return None, False, f"{field.name} is required"
            return None, False, None

        if field.widget_type == "json_editor":
            try:
                return json.loads(raw_value), True, None
            except json.JSONDecodeError as exc:
                return None, False, f"{field.name} has invalid JSON: {exc}"

        if field.widget_type == "plain_text_edit":
            if isinstance(raw_value, str):
                items = [line.strip() for line in raw_value.splitlines() if line.strip()]
                return items, True, None
            return raw_value, True, None

        return raw_value, True, None

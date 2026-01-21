"""Main window for the mkgui runtime UI."""

from __future__ import annotations

import json
import shlex
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..protocol import InvocationRequest, ResultEnvelope, ResultKind
from .process_runner import ActionRunner
from .widgets.function_form import FunctionForm
from .widgets.output_console import OutputConsole
from .widgets.preflight_panel import PreflightPanel
from .widgets.run_history import RunHistory, RunRecord


class MainWindow(QMainWindow):
    """UI for browsing and executing spec actions."""

    def __init__(self, spec: dict[str, Any], parent=None) -> None:
        super().__init__(parent)
        self._spec = spec
        self._current_action: dict[str, Any] | None = None
        self._form: FunctionForm | None = None
        self._runner = ActionRunner(self)
        self._runner.output.connect(self._append_output)
        self._runner.finished.connect(self._handle_finished)
        self._command_base: list[str] | None = None
        self._last_command: str | None = None
        self._current_run_row: int | None = None
        self._current_run_record: RunRecord | None = None

        self.setWindowTitle("mkgui")
        self.resize(1000, 700)

        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)

        splitter = QSplitter(Qt.Orientation.Horizontal, central)
        layout.addWidget(splitter)

        left_panel = QWidget(splitter)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(8, 8, 8, 8)

        self._search = QLineEdit(left_panel)
        self._search.setPlaceholderText("Filter actions")
        self._search.textChanged.connect(self._apply_filter)
        left_layout.addWidget(self._search)

        self._tree = QTreeWidget(left_panel)
        self._tree.setHeaderHidden(True)
        self._tree.itemSelectionChanged.connect(self._on_selection)
        left_layout.addWidget(self._tree)

        right_panel = QWidget(splitter)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 8, 8, 8)

        self._preflight = PreflightPanel(spec, self)
        right_layout.addWidget(self._preflight)

        self._doc_label = QLabel(self)
        self._doc_label.setWordWrap(True)
        right_layout.addWidget(self._doc_label)

        plan_row = QWidget(self)
        plan_layout = QHBoxLayout(plan_row)
        plan_layout.setContentsMargins(0, 0, 0, 0)
        self._plan_label = QLabel(self)
        self._plan_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._copy_command = QPushButton("Copy Command", self)
        self._copy_command.clicked.connect(self._copy_command_to_clipboard)
        plan_layout.addWidget(self._plan_label)
        plan_layout.addStretch(1)
        plan_layout.addWidget(self._copy_command)
        right_layout.addWidget(plan_row)

        self._command_label = QLabel(self)
        self._command_label.setWordWrap(True)
        self._command_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        right_layout.addWidget(self._command_label)

        self._raw_args_label = QLabel("Raw Args", self)
        self._raw_args_input = QLineEdit(self)
        self._raw_args_input.setPlaceholderText("Example: --flag value")
        self._raw_args_input.textChanged.connect(self._update_command_label)
        right_layout.addWidget(self._raw_args_label)
        right_layout.addWidget(self._raw_args_input)

        self._form_container = QWidget(self)
        self._form_layout = QVBoxLayout(self._form_container)
        self._form_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self._form_container)

        button_row = QWidget(self)
        button_layout = QHBoxLayout(button_row)
        button_layout.setContentsMargins(0, 0, 0, 0)

        self._run_button = QPushButton("Run", self)
        self._run_button.clicked.connect(self._run_action)
        self._cancel_button = QPushButton("Cancel", self)
        self._cancel_button.clicked.connect(self._cancel_action)
        self._cancel_button.setEnabled(False)
        self._quit_button = QPushButton("Quit", self)
        self._quit_button.clicked.connect(self._quit_app)

        button_layout.addWidget(self._run_button)
        button_layout.addWidget(self._cancel_button)
        button_layout.addWidget(self._quit_button)
        right_layout.addWidget(button_row)

        self._tabs = QTabWidget(self)
        self._output = OutputConsole(self)
        self._history = RunHistory(self)
        self._tabs.addTab(self._output, "Output")
        self._tabs.addTab(self._history, "History")
        right_layout.addWidget(self._tabs, 1)

        self._build_tree()
        self._raw_args_label.hide()
        self._raw_args_input.hide()
        self._plan_label.hide()
        self._command_label.hide()
        self._copy_command.hide()

    def _build_tree(self) -> None:
        self._tree.clear()
        for module in self._spec.get("modules", []):
            module_label = module.get("display_name") or module.get("module_id") or "module"
            module_item = QTreeWidgetItem([module_label])
            module_item.setData(0, Qt.ItemDataRole.UserRole, None)
            for action in module.get("actions", []):
                action_label = action.get("name") or action.get("qualname") or "action"
                action_item = QTreeWidgetItem([action_label])
                action_item.setData(0, Qt.ItemDataRole.UserRole, action)
                module_item.addChild(action_item)
            self._tree.addTopLevelItem(module_item)
            module_item.setExpanded(True)

    def _apply_filter(self, text: str) -> None:
        text = text.strip().lower()
        for i in range(self._tree.topLevelItemCount()):
            module_item = self._tree.topLevelItem(i)
            any_visible = False
            for j in range(module_item.childCount()):
                action_item = module_item.child(j)
                label = action_item.text(0).lower()
                visible = text in label
                action_item.setHidden(not visible)
                any_visible = any_visible or visible
            module_item.setHidden(not any_visible and text != "")

    def _on_selection(self) -> None:
        items = self._tree.selectedItems()
        if not items:
            return
        action = items[0].data(0, Qt.ItemDataRole.UserRole)
        if action is None:
            return
        self._load_action(action)

    def _load_action(self, action: dict[str, Any]) -> None:
        self._current_action = action
        self._doc_label.setText(action.get("doc", {}).get("text") or "")
        self._raw_args_input.clear()

        plan = action.get("invocation_plan") or "direct_call"
        show_raw = plan != "direct_call"
        self._raw_args_label.setVisible(show_raw)
        self._raw_args_input.setVisible(show_raw)

        plan_label = plan.replace("_", " ")
        self._plan_label.setText(f"Invocation: {plan_label}")
        self._plan_label.setVisible(True)

        self._command_base = None
        self._last_command = None
        if show_raw:
            self._command_base = self._build_cli_argv(action)
        self._update_command_label()

        has_command = bool(self._last_command)
        self._command_label.setVisible(has_command)
        self._copy_command.setVisible(has_command)

        if self._form:
            self._form.setParent(None)
            self._form.deleteLater()
            self._form = None

        if not show_raw:
            self._form = FunctionForm(action, self)
            self._form.apply_defaults()
            self._form_layout.addWidget(self._form)

    def _append_output(self, text: str) -> None:
        self._output.append_text(text)

    def _run_action(self) -> None:
        action = self._current_action
        if not action:
            return

        plan = action.get("invocation_plan") or "direct_call"
        if plan == "direct_call":
            if not self._form:
                return
            args, kwargs, errors = self._form.collect_values()
            if errors:
                QMessageBox.warning(self, "Input Error", "\n".join(errors))
                return
            self._start_direct_call(action, args, kwargs)
        else:
            raw_args = self._parse_raw_args()
            self._start_cli_call(action, raw_args)

    def _cancel_action(self) -> None:
        self._runner.cancel()

    def _quit_app(self) -> None:
        if self._run_button.isEnabled():
            self.close()
            return
        response = QMessageBox.question(
            self,
            "Exit",
            "An action is still running. Cancel and exit?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if response == QMessageBox.StandardButton.Yes:
            self._runner.cancel()
            self.close()

    def _copy_command_to_clipboard(self) -> None:
        if not self._last_command:
            return
        QApplication.clipboard().setText(self._last_command)
        self.statusBar().showMessage("Command copied to clipboard", 2000)

    def _parse_raw_args(self) -> list[str]:
        text = self._raw_args_input.text().strip()
        return shlex.split(text) if text else []

    def _start_direct_call(self, action: dict[str, Any], args: list[Any], kwargs: dict[str, Any]) -> None:
        working_dir, sys_path = self._project_paths()
        module_root = self._module_source_root(action)
        if module_root and module_root not in sys_path:
            sys_path.insert(0, module_root)
        module_dir = self._module_dir(action)
        if module_dir and module_dir not in sys_path:
            sys_path.insert(0, module_dir)
        request = InvocationRequest(
            action_id=str(action.get("action_id", "")),
            module_import_path=str(action.get("module_import_path", "")),
            qualname=str(action.get("qualname", "")),
            args=args,
            kwargs=kwargs,
            working_dir=working_dir,
            sys_path=sys_path,
        )
        self._record_run_start(action, "direct call")
        self._set_running(True)
        self._runner.start_direct_call(request, working_dir)

    def _start_cli_call(self, action: dict[str, Any], raw_args: list[str]) -> None:
        argv = self._build_cli_argv(action)
        if not argv:
            QMessageBox.warning(self, "Run Error", "No runnable target for action.")
            return
        plan_label = (action.get("invocation_plan") or "cli").replace("_", " ")
        self._record_run_start(action, plan_label)
        self._set_running(True)
        self._runner.start_cli(argv + raw_args, self._action_working_dir(action))

    def _build_cli_argv(self, action: dict[str, Any]) -> list[str]:
        plan = action.get("invocation_plan") or "direct_call"
        module_id = action.get("module_id") or action.get("module_import_path")
        module_file = self._find_module_file(action)
        if plan == "script_path" and module_file:
            return [sys.executable, module_file]
        if plan == "module_as_script" and module_id:
            return [sys.executable, "-m", module_id]
        if plan == "console_script_entrypoint":
            for tag in action.get("tags", []):
                if isinstance(tag, str) and tag.startswith("console_script:"):
                    return [tag.split(":", 1)[1]]
            if module_file:
                return [sys.executable, module_file]
            if module_id:
                return [sys.executable, "-m", module_id]
        if module_file:
            return [sys.executable, module_file]
        if module_id:
            return [sys.executable, "-m", module_id]
        return []

    def _find_module_file(self, action: dict[str, Any]) -> str | None:
        action_id = action.get("action_id")
        for module in self._spec.get("modules", []):
            for candidate in module.get("actions", []):
                if candidate.get("action_id") == action_id:
                    return module.get("file_path")
        return None

    def _project_paths(self) -> tuple[str | None, list[str]]:
        project_root = self._spec.get("project_root")
        if not project_root:
            return None, []
        project_path = Path(project_root)
        if project_path.is_file():
            return str(project_path.parent), [str(project_path.parent)]
        return str(project_path), [str(project_path)]

    def _action_working_dir(self, action: dict[str, Any]) -> str | None:
        module_root = self._module_source_root(action)
        if module_root:
            return module_root
        return self._project_paths()[0]

    def _module_source_root(self, action: dict[str, Any]) -> str | None:
        module_file = self._find_module_file(action)
        module_import_path = action.get("module_import_path") or action.get("module_id")
        if not module_file or not module_import_path:
            return None
        file_path = Path(module_file)
        parts = str(module_import_path).split(".")
        steps = max(len(parts) - 1, 0)
        if file_path.name == "__init__.py":
            steps = len(parts)
        root = file_path.parent
        for _ in range(steps):
            root = root.parent
        return str(root)

    def _module_dir(self, action: dict[str, Any]) -> str | None:
        module_file = self._find_module_file(action)
        if not module_file:
            return None
        return str(Path(module_file).parent)

    def _handle_finished(self, envelope: ResultEnvelope) -> None:
        self._set_running(False)
        self._record_run_finish(envelope)
        if envelope.cancelled:
            self._output.append_text("Execution cancelled.")
            return
        if envelope.ok:
            self._render_result(envelope)
        else:
            self._output.append_text(envelope.error or "Execution failed")

    def _render_result(self, envelope: ResultEnvelope) -> None:
        if envelope.result_kind == ResultKind.TEXT:
            self._output.append_text(str(envelope.payload))
        elif envelope.result_kind == ResultKind.JSON:
            self._output.append_text(json.dumps(envelope.payload, indent=2))
        elif envelope.result_kind == ResultKind.REPR:
            self._output.append_text(str(envelope.payload))
        elif envelope.result_kind == ResultKind.FILE:
            self._output.append_text("Binary result returned.")
        elif envelope.result_kind == ResultKind.NONE:
            self._output.append_text("Execution completed.")

    def _set_running(self, running: bool) -> None:
        self._run_button.setEnabled(not running)
        self._cancel_button.setEnabled(running)

    def _record_run_start(self, action: dict[str, Any], plan_label: str) -> None:
        started_at = datetime.now().strftime("%H:%M:%S")
        action_label = action.get("qualname") or action.get("name") or "action"
        record = RunRecord(
            started_at=started_at,
            action=action_label,
            plan=plan_label,
            status="running",
        )
        self._current_run_row = self._history.add_run(record)
        self._current_run_record = record

    def _record_run_finish(self, envelope: ResultEnvelope) -> None:
        if self._current_run_record is None or self._current_run_row is None:
            return
        status = "ok" if envelope.ok else "cancelled" if envelope.cancelled else "error"
        record = RunRecord(
            started_at=self._current_run_record.started_at,
            action=self._current_run_record.action,
            plan=self._current_run_record.plan,
            status=status,
            duration_ms=envelope.duration_ms,
            exit_code=envelope.exit_code,
        )
        self._history.update_run(self._current_run_row, record)
        self._current_run_record = None
        self._current_run_row = None

    def _update_command_label(self) -> None:
        if not self._command_base:
            self._last_command = None
            self._command_label.hide()
            self._copy_command.hide()
            return

        argv = list(self._command_base)
        argv.extend(self._parse_raw_args())
        self._last_command = shlex.join(argv)
        self._command_label.setText(self._last_command)
        self._command_label.show()
        self._copy_command.show()

"""QProcess-based action runner."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, pyqtSignal

from ..protocol import InvocationRequest, ResultEnvelope, ResultKind


class ActionRunner(QObject):
    """Run actions via QProcess and emit output and results."""

    output = pyqtSignal(str)
    finished = pyqtSignal(ResultEnvelope)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._process = QProcess(self)
        self._process.readyReadStandardOutput.connect(self._read_stdout)
        self._process.readyReadStandardError.connect(self._read_stderr)
        self._process.finished.connect(self._on_finished)
        self._result_path: Path | None = None
        self._start_time: float | None = None
        self._expect_result = False
        self._cancelled = False

    def start_direct_call(self, request: InvocationRequest, working_dir: str | None) -> None:
        """Start a direct-call action via the child runner."""
        self._cancelled = False
        with tempfile.NamedTemporaryFile(delete=False) as handle:
            self._result_path = Path(handle.name)

        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONUNBUFFERED", "1")
        env.insert("WRAP_RESULT_PATH", str(self._result_path))
        self._inject_runtime_path(env)

        payload = json.dumps({
            "action_id": request.action_id,
            "module_import_path": request.module_import_path,
            "qualname": request.qualname,
            "args": request.args,
            "kwargs": request.kwargs,
            "working_dir": request.working_dir,
            "env_overrides": request.env_overrides,
            "sys_path": request.sys_path,
            "attr_path": request.attr_path,
        })

        self._expect_result = True
        self._start_time = time.perf_counter()
        self._process.setProcessEnvironment(env)
        if working_dir:
            self._process.setWorkingDirectory(working_dir)
        self._process.start(sys.executable, ["-m", "mkgui_runtime.child"])
        self._process.write(payload.encode("utf-8"))
        self._process.closeWriteChannel()

    def start_cli(self, argv: list[str], working_dir: str | None) -> None:
        """Start a CLI action via QProcess."""
        self._cancelled = False
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONUNBUFFERED", "1")
        self._inject_runtime_path(env)

        self._expect_result = False
        self._start_time = time.perf_counter()
        self._process.setProcessEnvironment(env)
        if working_dir:
            self._process.setWorkingDirectory(working_dir)
        program = argv[0]
        arguments = argv[1:]
        self._process.start(program, arguments)

    def cancel(self) -> None:
        """Cancel a running process."""
        if self._process.state() == QProcess.ProcessState.NotRunning:
            return
        self._cancelled = True
        self._process.terminate()
        QTimer.singleShot(2000, self._process.kill)

    def _read_stdout(self) -> None:
        data = bytes(self._process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if data:
            self.output.emit(data)

    def _read_stderr(self) -> None:
        data = bytes(self._process.readAllStandardError()).decode("utf-8", errors="replace")
        if data:
            self.output.emit(data)

    def _inject_runtime_path(self, env: QProcessEnvironment) -> None:
        runtime_root = str(Path(__file__).resolve().parents[2])
        existing = env.value("PYTHONPATH", "")
        if existing:
            env.insert("PYTHONPATH", f"{runtime_root}{os.pathsep}{existing}")
        else:
            env.insert("PYTHONPATH", runtime_root)

    def _on_finished(self, exit_code: int, _status: QProcess.ExitStatus) -> None:
        duration_ms = 0
        if self._start_time is not None:
            duration_ms = int((time.perf_counter() - self._start_time) * 1000)

        was_cancelled = self._cancelled
        self._cancelled = False

        if self._expect_result and self._result_path:
            if self._result_path.exists():
                data = json.loads(self._result_path.read_text(encoding="utf-8"))
                self._result_path.unlink(missing_ok=True)
                envelope = ResultEnvelope.from_dict(data)
                if was_cancelled and not envelope.ok:
                    envelope.cancelled = True
                self.finished.emit(envelope)
                return
            if was_cancelled:
                envelope = ResultEnvelope(
                    ok=False,
                    cancelled=True,
                    exit_code=exit_code,
                    duration_ms=duration_ms,
                    result_kind=ResultKind.NONE,
                    payload=None,
                    error="Execution cancelled",
                )
            else:
                envelope = ResultEnvelope(
                    ok=False,
                    cancelled=False,
                    exit_code=exit_code,
                    duration_ms=duration_ms,
                    result_kind=ResultKind.NONE,
                    payload=None,
                    error="Result file not created",
                )
            self.finished.emit(envelope)
            return

        ok = exit_code == 0
        if was_cancelled:
            ok = False
        envelope = ResultEnvelope(
            ok=ok,
            cancelled=was_cancelled,
            exit_code=exit_code,
            duration_ms=duration_ms,
            result_kind=ResultKind.NONE,
            payload=None,
            error=None if ok else ("Execution cancelled" if was_cancelled else f"Process exited with code {exit_code}"),
        )
        self.finished.emit(envelope)

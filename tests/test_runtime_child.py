"""Tests for the runtime child runner."""

import json
import os
import sys
from pathlib import Path

import subprocess

from mkgui_runtime.child import run_request
from mkgui_runtime.protocol import InvocationRequest, ResultKind


def test_child_run_request_success(tmp_path: Path):
    """Child runner should execute callable and return JSON result."""
    (tmp_path / "calc.py").write_text(
        """
def add(a, b):
    return a + b
"""
    )

    request = InvocationRequest(
        action_id="calc.add",
        module_import_path="calc",
        qualname="calc.add",
        args=[2, 3],
        kwargs={},
        sys_path=[str(tmp_path)],
    )

    result = run_request(request)
    assert result.ok is True
    assert result.result_kind == ResultKind.JSON
    assert result.payload == 5


def test_child_run_request_error(tmp_path: Path):
    """Child runner should capture errors."""
    (tmp_path / "boom.py").write_text(
        """
def explode():
    raise ValueError("boom")
"""
    )

    request = InvocationRequest(
        action_id="boom.explode",
        module_import_path="boom",
        qualname="boom.explode",
        args=[],
        kwargs={},
        sys_path=[str(tmp_path)],
    )

    result = run_request(request)
    assert result.ok is False
    assert "ValueError" in (result.error or "")


def test_child_subprocess_result_file(tmp_path: Path):
    """Child CLI should write result file when env var is set."""
    (tmp_path / "echoer.py").write_text(
        """
def echo(value):
    return value
"""
    )

    request = {
        "action_id": "echoer.echo",
        "module_import_path": "echoer",
        "qualname": "echoer.echo",
        "args": ["ok"],
        "kwargs": {},
        "sys_path": [str(tmp_path)],
    }

    result_path = tmp_path / "result.json"
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([
        str(Path(__file__).resolve().parents[1] / "src"),
        env.get("PYTHONPATH", ""),
    ])
    env["WRAP_RESULT_PATH"] = str(result_path)

    proc = subprocess.run(
        [sys.executable, "-m", "mkgui_runtime.child"],
        input=json.dumps(request),
        text=True,
        env=env,
    )
    assert proc.returncode == 0
    assert result_path.exists()
    data = json.loads(result_path.read_text())
    assert data["ok"] is True

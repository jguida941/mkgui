"""Tests for the runtime runner."""

from pathlib import Path

from mkgui_runtime.runner import run_action_subprocess


def test_runner_module_as_script(tmp_path: Path):
    """Runner should execute module-as-script actions."""
    (tmp_path / "cli_mod.py").write_text(
        """
if __name__ == "__main__":
    print("ok")
"""
    )

    spec = {
        "project_root": str(tmp_path),
        "modules": [
            {
                "module_id": "cli_mod",
                "display_name": "cli_mod",
                "file_path": str(tmp_path / "cli_mod.py"),
                "actions": [
                    {
                        "action_id": "cli_mod.__main__:abc",
                        "name": "__main__",
                        "module_import_path": "cli_mod",
                        "qualname": "cli_mod.__main__",
                        "invocation_plan": "module_as_script",
                        "parameters": [],
                        "tags": [],
                    }
                ],
            }
        ],
    }

    action = spec["modules"][0]["actions"][0]
    action["module_id"] = "cli_mod"
    action["module_file_path"] = str(tmp_path / "cli_mod.py")
    result = run_action_subprocess(spec, action)

    assert result.ok is True


def test_runner_in_process(monkeypatch, tmp_path: Path):
    """Runner should support in-process direct calls."""
    (tmp_path / "ops.py").write_text(
        """
def ping():
    return "pong"
"""
    )

    spec = {
        "project_root": str(tmp_path),
        "modules": [
            {
                "module_id": "ops",
                "display_name": "ops",
                "file_path": str(tmp_path / "ops.py"),
                "actions": [
                    {
                        "action_id": "ops.ping:abc",
                        "name": "ping",
                        "module_import_path": "ops",
                        "qualname": "ops.ping",
                        "invocation_plan": "direct_call",
                        "parameters": [],
                        "tags": [],
                    }
                ],
            }
        ],
    }

    action = spec["modules"][0]["actions"][0]
    action["module_id"] = "ops"
    action["module_file_path"] = str(tmp_path / "ops.py")

    monkeypatch.setenv("MKGUI_RUNNER", "in_process")
    result = run_action_subprocess(spec, action)

    assert result.ok is True
    assert result.payload == "pong"

"""Headless runtime runner that executes actions via the child process."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from .child import run_request
from .protocol import InvocationRequest, ResultEnvelope, ResultKind


def _flatten_actions(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten spec modules into a list of actions with module info."""
    actions: list[dict[str, Any]] = []
    for module in spec.get("modules", []):
        module_id = module.get("module_id")
        module_name = module.get("display_name", module_id)
        module_file = module.get("file_path")
        for action in module.get("actions", []):
            entry = dict(action)
            entry["module_id"] = module_id
            entry["module_name"] = module_name
            entry["module_file_path"] = module_file
            actions.append(entry)
    return actions


def _pick_action(actions: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick an action via environment variables or interactive prompt."""
    action_id = os.environ.get("MKGUI_ACTION_ID")
    if action_id:
        for action in actions:
            if action.get("action_id") == action_id:
                return action
        return None

    if not sys.stdin.isatty():
        return None

    for idx, action in enumerate(actions, start=1):
        module_name = action.get("module_name") or action.get("module_id")
        label = f"{idx}. {module_name}.{action.get('name')} [{action.get('action_id')}]"
        print(label)

    selection = input("Select action number: ").strip()
    if not selection:
        return None
    try:
        index = int(selection) - 1
    except ValueError:
        return None
    if 0 <= index < len(actions):
        return actions[index]
    return None


def _parse_env_json(name: str) -> Any | None:
    """Parse a JSON value from an environment variable."""
    raw = os.environ.get(name)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _collect_raw_args() -> list[str]:
    """Collect raw CLI args from env var or prompt."""
    raw = os.environ.get("MKGUI_RAW_ARGS")
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except json.JSONDecodeError:
            return shlex.split(raw)

    if not sys.stdin.isatty():
        return []

    value = input("Args (shell-style): ").strip()
    return shlex.split(value) if value else []


def _prompt_value(name: str) -> Any:
    """Prompt for a value and parse JSON when possible."""
    raw = input(f"{name}: ").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _collect_arguments(action: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    """Collect arguments from env vars or interactive prompt."""
    args = _parse_env_json("MKGUI_ARGS")
    kwargs = _parse_env_json("MKGUI_KWARGS")
    if isinstance(args, list) and isinstance(kwargs, dict):
        return args, kwargs

    if not sys.stdin.isatty():
        return [], {}

    collected_kwargs: dict[str, Any] = {}
    for param in action.get("parameters", []):
        name = param.get("name")
        if not name:
            continue
        required = bool(param.get("required", True))
        value = _prompt_value(name)
        if value is None and required:
            print(f"{name} is required.")
            return [], {}
        if value is not None:
            collected_kwargs[name] = value
    return [], collected_kwargs


def _project_paths(spec: dict[str, Any]) -> tuple[str | None, list[str]]:
    """Compute working dir and sys.path entries from spec."""
    project_root = spec.get("project_root")
    if not project_root:
        return None, []
    project_path = Path(project_root)
    if project_path.is_file():
        return str(project_path.parent), [str(project_path.parent)]
    return str(project_path), [str(project_path)]


def _run_cli_action(
    spec: dict[str, Any],
    action: dict[str, Any],
    raw_args: list[str],
) -> ResultEnvelope:
    """Execute a CLI-oriented action as a script or module."""
    plan = action.get("invocation_plan") or "direct_call"
    module_id = action.get("module_id") or action.get("module_import_path")
    file_path = action.get("module_file_path")
    working_dir = _action_working_dir(spec, action)

    argv: list[str] = []
    if plan == "script_path" and file_path:
        argv = [sys.executable, file_path]
    elif plan == "module_as_script" and module_id:
        argv = [sys.executable, "-m", module_id]
    elif plan == "console_script_entrypoint":
        script_name = None
        for tag in action.get("tags", []):
            if isinstance(tag, str) and tag.startswith("console_script:"):
                script_name = tag.split(":", 1)[1]
                break
        if script_name:
            argv = [script_name]
        elif file_path:
            argv = [sys.executable, file_path]
        elif module_id:
            argv = [sys.executable, "-m", module_id]
    elif file_path:
        argv = [sys.executable, file_path]
    elif module_id:
        argv = [sys.executable, "-m", module_id]

    if not argv:
        return ResultEnvelope(
            ok=False,
            cancelled=False,
            exit_code=1,
            duration_ms=0,
            result_kind=ResultKind.NONE,
            payload=None,
            error="No executable path found for CLI action",
        )

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    _inject_runtime_path(env)
    start = time.perf_counter()
    proc = subprocess.run(
        argv + raw_args,
        cwd=working_dir,
        env=env,
        stdin=subprocess.DEVNULL,
    )
    duration_ms = int((time.perf_counter() - start) * 1000)
    ok = proc.returncode == 0
    return ResultEnvelope(
        ok=ok,
        cancelled=False,
        exit_code=proc.returncode,
        duration_ms=duration_ms,
        result_kind=ResultKind.NONE,
        payload=None,
        error=None if ok else f"Process exited with code {proc.returncode}",
    )


def run_action_subprocess(spec: dict[str, Any], action: dict[str, Any]) -> ResultEnvelope:
    """Execute an action via the child runner and return its result."""
    plan = action.get("invocation_plan") or "direct_call"
    if plan != "direct_call":
        raw_args = _collect_raw_args()
        return _run_cli_action(spec, action, raw_args)

    args, kwargs = _collect_arguments(action)
    working_dir, sys_path = _action_sys_path(spec, action)

    request = InvocationRequest(
        action_id=str(action.get("action_id", "")),
        module_import_path=str(action.get("module_import_path", "")),
        qualname=str(action.get("qualname", "")),
        args=args,
        kwargs=kwargs,
        working_dir=working_dir,
        sys_path=sys_path,
    )

    if os.environ.get("MKGUI_RUNNER") == "in_process":
        return run_request(request)

    with tempfile.NamedTemporaryFile(delete=False) as handle:
        result_path = handle.name

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["WRAP_RESULT_PATH"] = result_path
    _inject_runtime_path(env)

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
    proc = subprocess.run(
        [sys.executable, "-m", "mkgui_runtime.child"],
        input=payload,
        text=True,
        env=env,
    )

    result_file = Path(result_path)
    if not result_file.exists():
        return ResultEnvelope(
            ok=False,
            cancelled=False,
            exit_code=proc.returncode,
            duration_ms=0,
            result_kind=ResultKind.NONE,
            payload=None,
            error="Result file not created by child process",
        )

    data = json.loads(result_file.read_text(encoding="utf-8"))
    result_file.unlink(missing_ok=True)
    return ResultEnvelope.from_dict(data)


def _inject_runtime_path(env: dict[str, str]) -> None:
    runtime_root = str(Path(__file__).resolve().parents[1])
    existing = env.get("PYTHONPATH", "")
    if existing:
        env["PYTHONPATH"] = f"{runtime_root}{os.pathsep}{existing}"
    else:
        env["PYTHONPATH"] = runtime_root


def run_app(spec: dict[str, Any]) -> int:
    """Run a headless CLI application for a spec."""
    actions = _flatten_actions(spec)
    if not actions:
        print("No actions found in spec.")
        return 0

    action = _pick_action(actions)
    if not action:
        print("No action selected.")
        return 1

    result = run_action_subprocess(spec, action)
    if result.ok:
        if result.result_kind == ResultKind.TEXT:
            print(result.payload)
        elif result.result_kind == ResultKind.JSON:
            print(json.dumps(result.payload, indent=2))
        elif result.result_kind == ResultKind.REPR:
            print(result.payload)
        elif result.result_kind == ResultKind.FILE:
            print("Binary result returned.")
        return 0

    sys.stderr.write(result.error or "Execution failed\n")
    sys.stderr.write("\n")
    return result.exit_code or 1


def _action_sys_path(spec: dict[str, Any], action: dict[str, Any]) -> tuple[str | None, list[str]]:
    working_dir, sys_path = _project_paths(spec)
    module_root = _module_source_root(action)
    if module_root and module_root not in sys_path:
        sys_path.insert(0, module_root)
    module_dir = _module_dir(action)
    if module_dir and module_dir not in sys_path:
        sys_path.insert(0, module_dir)
    return working_dir, sys_path


def _action_working_dir(spec: dict[str, Any], action: dict[str, Any]) -> str | None:
    module_root = _module_source_root(action)
    if module_root:
        return module_root
    return _project_paths(spec)[0]


def _module_source_root(action: dict[str, Any]) -> str | None:
    module_file = action.get("module_file_path") or action.get("file_path")
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


def _module_dir(action: dict[str, Any]) -> str | None:
    module_file = action.get("module_file_path") or action.get("file_path")
    if not module_file:
        return None
    return str(Path(module_file).parent)

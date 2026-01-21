"""Subprocess child runner for executing actions."""

from __future__ import annotations

import base64
import importlib
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from .protocol import InvocationRequest, ResultEnvelope, ResultKind

RESULT_ENV_VAR = "WRAP_RESULT_PATH"


def _resolve_attr(obj: object, attr_path: str) -> object:
    """Resolve a dotted attribute path on an object."""
    current = obj
    for part in attr_path.split("."):
        if not part:
            continue
        current = getattr(current, part)
    return current


def _resolve_callable(request: InvocationRequest) -> object:
    """Resolve a callable from an invocation request."""
    module_path = request.module_import_path
    qualname = request.qualname
    attr_path = request.attr_path

    if not attr_path and module_path and qualname.startswith(f"{module_path}."):
        attr_path = qualname[len(module_path) + 1:]

    if module_path:
        try:
            module = importlib.import_module(module_path)
            if attr_path:
                return _resolve_attr(module, attr_path)
            return module
        except ImportError:
            if "." in module_path:
                base_module, prefix = module_path.rsplit(".", 1)
                module = importlib.import_module(base_module)
                obj = getattr(module, prefix)
                if attr_path:
                    return _resolve_attr(obj, attr_path)
                if qualname.startswith(f"{module_path}."):
                    return _resolve_attr(obj, qualname[len(module_path) + 1:])
                return obj
            raise

    if qualname:
        parts = qualname.split(".")
        if len(parts) >= 2:
            module = importlib.import_module(".".join(parts[:-1]))
            return getattr(module, parts[-1])

    raise ValueError("Invocation request missing module import path and qualname")


def _serialize_result(value: Any) -> tuple[ResultKind, Any]:
    """Serialize a result into a ResultKind and JSON-friendly payload."""
    if value is None:
        return ResultKind.NONE, None
    if isinstance(value, str):
        return ResultKind.TEXT, value
    if isinstance(value, (dict, list, int, float, bool)):
        return ResultKind.JSON, value
    if isinstance(value, (tuple, set)):
        return ResultKind.JSON, [item for item in value]
    if isinstance(value, (bytes, bytearray)):
        data = base64.b64encode(value).decode("ascii")
        return ResultKind.FILE, {
            "encoding": "base64",
            "data": data,
        }
    return ResultKind.REPR, repr(value)


def run_request(request: InvocationRequest) -> ResultEnvelope:
    """Execute an invocation request and return a result envelope."""
    if request.env_overrides:
        os.environ.update({k: str(v) for k, v in request.env_overrides.items()})

    if request.working_dir:
        os.chdir(request.working_dir)
        sys.path.insert(0, request.working_dir)

    for path_entry in request.sys_path:
        if path_entry:
            sys.path.insert(0, path_entry)

    start = time.perf_counter()
    try:
        target = _resolve_callable(request)
        result = target(*request.args, **request.kwargs)
        result_kind, payload = _serialize_result(result)
        duration_ms = int((time.perf_counter() - start) * 1000)
        return ResultEnvelope(
            ok=True,
            cancelled=False,
            exit_code=0,
            duration_ms=duration_ms,
            result_kind=result_kind,
            payload=payload,
        )
    except SystemExit as exc:
        duration_ms = int((time.perf_counter() - start) * 1000)
        code = exc.code if isinstance(exc.code, int) else 1
        return ResultEnvelope(
            ok=code == 0,
            cancelled=False,
            exit_code=code,
            duration_ms=duration_ms,
            result_kind=ResultKind.NONE,
            payload=None,
            error=None if code == 0 else f"SystemExit: {code}",
        )
    except Exception:
        duration_ms = int((time.perf_counter() - start) * 1000)
        return ResultEnvelope(
            ok=False,
            cancelled=False,
            exit_code=1,
            duration_ms=duration_ms,
            result_kind=ResultKind.NONE,
            payload=None,
            error=traceback.format_exc().strip(),
        )


def _write_result(path: Path, envelope: ResultEnvelope) -> None:
    """Write the result envelope to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(envelope.to_dict(), handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def main() -> int:
    """Read an invocation request and execute it."""
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"Invalid invocation JSON: {exc}\n")
        return 2

    request = InvocationRequest.from_dict(payload)
    envelope = run_request(request)

    result_path = os.environ.get(RESULT_ENV_VAR) or payload.get("result_path")
    if result_path:
        _write_result(Path(result_path), envelope)
    else:
        json.dump(envelope.to_dict(), sys.stdout)
        sys.stdout.write("\n")

    return 0 if envelope.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

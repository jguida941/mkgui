"""Runtime protocol helpers for subprocess execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ResultKind(str, Enum):
    """Kinds of results produced by the runtime."""
    NONE = "none"
    TEXT = "text"
    JSON = "json"
    TABLE = "table"
    FILE = "file"
    REPR = "repr"


@dataclass
class ResultEnvelope:
    """Structured result payload for child execution."""
    ok: bool
    cancelled: bool
    exit_code: int
    duration_ms: int
    result_kind: ResultKind
    payload: Any = None
    error: str | None = None
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    limits: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return {
            "ok": self.ok,
            "cancelled": self.cancelled,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "result_kind": self.result_kind.value,
            "payload": self.payload,
            "error": self.error,
            "stdout_truncated": self.stdout_truncated,
            "stderr_truncated": self.stderr_truncated,
            "limits": self.limits,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResultEnvelope":
        """Create a ResultEnvelope from a dict."""
        return cls(
            ok=bool(data.get("ok")),
            cancelled=bool(data.get("cancelled")),
            exit_code=int(data.get("exit_code", 0)),
            duration_ms=int(data.get("duration_ms", 0)),
            result_kind=ResultKind(data.get("result_kind", ResultKind.NONE.value)),
            payload=data.get("payload"),
            error=data.get("error"),
            stdout_truncated=bool(data.get("stdout_truncated")),
            stderr_truncated=bool(data.get("stderr_truncated")),
            limits=dict(data.get("limits") or {}),
        )


@dataclass
class InvocationRequest:
    """Request for executing a callable in the child runtime."""
    action_id: str
    module_import_path: str
    qualname: str
    args: list[Any] = field(default_factory=list)
    kwargs: dict[str, Any] = field(default_factory=dict)
    working_dir: str | None = None
    env_overrides: dict[str, str] = field(default_factory=dict)
    sys_path: list[str] = field(default_factory=list)
    attr_path: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InvocationRequest":
        """Create an InvocationRequest from a dict."""
        return cls(
            action_id=str(data.get("action_id", "")),
            module_import_path=str(data.get("module_import_path", "")),
            qualname=str(data.get("qualname", "")),
            args=list(data.get("args") or []),
            kwargs=dict(data.get("kwargs") or {}),
            working_dir=data.get("working_dir"),
            env_overrides=dict(data.get("env_overrides") or {}),
            sys_path=list(data.get("sys_path") or []),
            attr_path=data.get("attr_path"),
        )

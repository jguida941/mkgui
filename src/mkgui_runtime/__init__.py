"""Runtime package for executing mkgui specs."""

from __future__ import annotations

from typing import Any


def run_app(spec: dict[str, Any]) -> int:
    """Launch the GUI runtime for a spec."""
    from .app import run_app as _run_app

    return _run_app(spec)


def run_cli(spec: dict[str, Any]) -> int:
    """Launch the headless runtime for a spec."""
    from .runner import run_app as _run_cli

    return _run_cli(spec)


__all__ = ["run_app", "run_cli"]

# Status

Last updated: 2026-01-21

## Summary
- Runtime-driven PyQt6 GUI scaffold is implemented and bundled for standalone output.
- Analyzer and inspector handle more real-world projects (src/ roots, path params, non-JSON defaults).
- Runtime execution paths handle module imports from src/ and top-level modules reliably.

## Key Changes
- Added runtime package `mkgui_runtime` with GUI (MainWindow, form widgets, output, preflight, history) and subprocess runner.
- Standalone scaffold mode now bundles the runtime into output (no external runtime install required).
- Fixed form default handling to coerce literals for widget types and avoid QLineEdit type errors.
- Added cancellation tracking and a Quit button in the GUI.
- Added run history and copy-command UX; output tab keeps stdout/stderr/result.
- Analyzer: JSON-serializable defaults, input() warnings, introspection mode, module_source_hash, console_scripts detection.
- Analyzer: treat top-level src/ as a source root when it lacks __init__.py.
- Inspector: path widget heuristics by parameter name; Annotated metadata parsing; enum/dataclass mapping.
- Runtime: ensure sys.path includes module root and module directory so top-level imports (e.g., `from formatter import ...`) work.
- Runtime: lazy imports in `mkgui_runtime.__init__` to avoid runpy warnings.

## Manual Verification
- disk-analyzer repo (GUI file removed): GUI loads 4 modules / 10 actions; `scan_directory` executes and returns file info list.
- Test fixture in /tmp: `add(2, 7)` returns 9; `summarize([a,b,c])` returns dict.

## Tests Run
- `PYTHONPATH=src pytest -q tests/test_analyzer.py tests/test_runtime_runner.py tests/test_runtime_child.py tests/test_inspector.py`

## Known Issues / Notes
- Projects with `src/__init__.py` remain `src.*` module IDs by design; runtime now compensates by adding module dir to sys.path.
- PyQt6 is required to launch the GUI.
- pytest_asyncio deprecation warning about `asyncio_default_fixture_loop_scope` persists.

## Next Steps
- Run full test suite (requires hypothesis in the active environment).
- Validate GUI flows on additional real repos, especially CLI-only modules.
- Decide if generator should emit a custom scaffold layout instead of bundling runtime.

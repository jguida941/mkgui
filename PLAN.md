# Code-to-GUI Scaffold Tool - Implementation Plan

## What This Tool Does

Takes existing Python code and generates a PyQt6 GUI wrapper around it.

**Key principle**: The original code stays intact. We generate adapters that call into it.

---

## Core Concept

```
┌─────────────────────────────────────────────────────────────┐
│  YOUR EXISTING CODE                                         │
│  (CLI tool, library, scripts)                               │
│                                                             │
│  • database.py - create_task(), get_all_tasks()             │
│  • models.py - Task, Project, User dataclasses              │
│  • config.py - load_config(), save_config()                 │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  ANALYZER (AST + inspect)                                   │
│                                                             │
│  Detects:                                                   │
│  • Entrypoints (main(), if __name__, CLI decorators)        │
│  • Public functions (not starting with _)                   │
│  • Function signatures with types                           │
│  • Classes and their public methods                         │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  GENERATED GUI PROJECT                                      │
│                                                             │
│  • Services layer (thin wrappers)                           │
│  • Controller (validation + runners)                        │
│  • Dynamic forms from signatures                            │
│  • Output console for stdout/stderr                         │
└─────────────────────────────────────────────────────────────┘
```

---

## Detection Rules (Deterministic, No Magic)

### A) Entrypoint Detection (Priority Order)

1. `if __name__ == "__main__":` blocks
2. Functions decorated with `@click.command`, `@typer.command`, `@app.command`
3. Functions using `argparse.ArgumentParser`
4. Functions named: `main()`, `run()`, `cli()`, `start()`, `execute()`

### B) Public API Surface

1. If `__all__` is defined, include only those names
2. Else include top-level functions/classes not starting with `_`
3. Class methods follow class lifecycle rules (v1: staticmethod/classmethod only)
4. Use module name hints for grouping/tabs (core, engine, api, service, utils, helpers)

### C) Ignore Patterns

- `tests/`, `test_*.py`, `*_test.py`
- `venv/`, `.venv/`, `env/`
- `build/`, `dist/`, `__pycache__/`
- `setup.py`, `conftest.py`
- Files starting with `.`

---

## Type-to-Widget Mapping (Static, Deterministic)

Uses AST-only analysis plus optional runtime introspection for resolved types - no guessing.

| Python Type | PyQt6 Widget | Notes |
|-------------|--------------|-------|
| `int` | `QSpinBox` | Range: -999999 to 999999 |
| `float` | `QDoubleSpinBox` | 2 decimal places default |
| `bool` | `QCheckBox` | |
| `str` | `QLineEdit` | |
| `Path`, `pathlib.Path` | `QLineEdit` + Browse button | Opens file dialog |
| `Enum`, `Literal[...]` | `QComboBox` | Populated from enum values |
| `List[str]` | `QPlainTextEdit` | One item per line |
| `Optional[T]` | Widget for T + "None" checkbox | |
| `dict`, `Any`, unknown | `QPlainTextEdit` | JSON input |

**Default**: If type cannot be inferred → `QLineEdit` (plain text)

---

## Widget Registry and Mapping Rules

### GUI Component Taxonomy (Static Catalog)

Core shells:
- MainWindow
- DockPanel (optional)
- CentralWidget
- Dialog (optional)
- Wizard (optional)

Interaction widgets:
- ActionList (callable list)
- ParamForm (auto-generated inputs)
- RunButton
- OutputConsole
- ResultView (text/json/table)
- ProgressBar (with cancel)
- FilePicker (Path-like params)
- ToggleGroup (bools/options)
- TableView (tabular results)
- PlotView (v2)

Execution infrastructure:
- TaskRunner (QProcess default; QThreadPool/QRunnable for in-process v2)
- CancellationToken (cooperative)
- ResultSerializer (safe conversion to display)
- ErrorPresenter (structured errors -> UI + console)

### Deterministic Mapping Table (Code -> GUI)

A) Entry points -> Actions
- main(), click/typer commands, argparse, public functions/classes
- Each callable becomes an ActionList item; single callable auto-selected

B) Parameter types -> ParamForm widgets
- int -> QSpinBox
- float -> QDoubleSpinBox
- bool -> QCheckBox
- str -> QLineEdit
- Path/pathlib.Path -> FilePicker (line edit + browse)
- Enum/Literal -> QComboBox (values)
- Optional[T] -> widget for T + allow empty
- list[str]/tuple[str] -> multiline editor (v1)
- *args -> list editor (one per line) or JSON list input
- **kwargs -> JSON dict input
- keyword-only args -> render under an "Advanced" section
- dict/Any/unknown -> QPlainTextEdit (raw JSON/text)
- Default values populate widgets; literal defaults use ast.literal_eval in AST-only mode
- Unknown types always fall back to text input

C) Return types -> ResultView
- Subprocess mode renders a ResultEnvelope payload; in-process can render objects directly
- None -> Completed + logs
- str -> plain text
- dict/list -> JSON tree view (or pretty text v1)
- pandas.DataFrame/list[dict] -> TableView (subprocess uses head() to records)
- bytes -> offer save dialog (v2)
- matplotlib Figure -> PlotView (v2)

D) I/O patterns -> Extra UI (optional heuristics)
- input() usage -> warn and require adapter stub
- stdout heavy -> OutputConsole becomes primary focus
- file reads + Path params -> suggest FilePicker defaults

E) Long-running calls -> TaskRunner + Progress
- Default: subprocess runner via QProcess (single task at a time in v1)
- In-process runner is opt-in; cancellation is best-effort only
- Always expose cancellation token where supported

### Fallback Rules and Non-Goals
- No AI guessing; only static rules + introspection
- Unknown types -> plain text input
- No UI inference from arbitrary code beyond stated rules

---

## Accuracy and Correctness Upgrades

### Analysis Modes (Avoid Import Side Effects)
- Level A: AST-only scan (no imports) extracts defs, arg names, defaults (as source), annotation strings, docstrings, decorators, __all__, __main__ blocks
- If default is a literal, use ast.literal_eval; otherwise keep source repr
- Level B: Optional runtime introspection in a subprocess with timeouts to resolve annotations/signatures
- Track per-callable fields: introspection_status, introspection_error, annotations_resolved, side_effect_risk
- side_effect_risk is true if top-level AST has any calls or statements beyond imports, defs, docstring, or simple constant assigns
- Prefer static outputs for determinism; enrich only when safe

### TypeExpr Parser (AST-Only Type Mapping)
- Parse annotation AST into a deterministic TypeExpr (no eval/import)
- Supported patterns only: Name, Attribute, Subscript (Optional, Literal, list), and X | None unions
- Unknown patterns map to "unknown" and use default widgets

### AST Class Classifier (Enum/Dataclass)
- Detect Enum classes (Enum/enum.Enum bases) and extract literal members for ComboBox
- Detect dataclasses via @dataclass decorators and allow structured JSON template (v1) or nested form (v2)

### AnalysisResult Schema (spec.json)
- Top-level: spec_version, generator_version, created_at, project_root, analysis_mode, python_target (optional), spec_source_hash, override_schema_version, modules[], warnings[]
- ModuleSpec: module_id, display_name, file_path (optional), module_source_hash, actions[]
- ActionSpec: action_id, kind, qualname, module_import_path, doc {text, format}, parameters[], returns, invocation_plan, introspection, tags[]
- ParamSpec: name, kind, required, default {present, repr, literal}, annotation {raw, resolved}, ui {widget, options}, validation {min, max, regex}
- ReturnSpec: annotation {raw, resolved}, ui {result_kind, options}

### Spec Stability and Overrides
- Hash module sources and full analysis inputs for deterministic regen checks
- Override precedence: runtime defaults -> inferred mapping -> Annotated metadata -> overrides.yml
- Track override schema version for compatibility

### Invocation Plan (How Each Action Runs)
- Add per-action InvocationPlan: DIRECT_CALL, MODULE_AS_SCRIPT, SCRIPT_PATH, CLICK_COMMAND, TYPER_COMMAND, CONSOLE_SCRIPT_ENTRYPOINT, CLI_GENERIC
- Detect console_scripts entry points from pyproject.toml / entry_points
- Do not assume CLI detection equals callable invocation
- CLI_GENERIC always exposes a Raw Args input; structured forms are optional

### Click/Typer Structured Forms (Gated)
- Only build structured forms when Level B introspection succeeds and click/typer params are resolved
- Otherwise fall back to CLI_GENERIC raw args
- Map click types: Choice -> combo, Path -> file/dir picker, IntRange/FloatRange -> min/max, multiple=True -> list editor

### Child Runner Shim (Subprocess Library Calls)
- Add a runtime-owned child entrypoint (e.g., python -m pyqt6_wrap_runtime.child)
- ChildInvocationRequest (JSON) includes action_id, module_import_path, qualname, args/kwargs (wire values), working_dir, env_overrides
- Child resolves callable, converts wire values, executes, writes ResultEnvelope to WRAP_RESULT_PATH, and exits with status code

### Execution Modes and stdout/stderr
- Default to subprocess runner for robust stdout/stderr capture and cancellation
- In-process runner is opt-in, best-effort cancellation only
- Avoid redirect_stdout in threads; use a multiplexer if in-process capture is needed
- Subprocess runner uses QProcess and a result file protocol for structured results
- Run subprocess with stdin closed to fail fast on input()

### QProcess Robustness
- Set PYTHONUNBUFFERED=1 for real-time output
- Decode stdout/stderr as UTF-8 with errors="replace"
- Set working directory explicitly (project root or configured)
- Cancellation: terminate -> wait N ms -> kill, always emit cancelled ResultEnvelope
- Ensure result file cleanup on cancel/crash

### Result Envelope and Result File Protocol
- Parent allocates a temp result path and passes it via env (e.g., WRAP_RESULT_PATH)
- Child writes structured output to the result file; stdout/stderr remain console output
- ResultEnvelope: ok, cancelled, exit_code, duration_ms, result_kind (none|text|json|table|file|repr), payload, stdout_truncated, stderr_truncated, limits

### Class Lifecycle
- v1: only expose @staticmethod/@classmethod
- v2: instance sessions (constructor form, stored instance, reset/new instance)

### Deterministic Type Extensions
- Support Annotated[T, metadata] for explicit widget overrides (min/max, file filters)
- Add high-value builtin types: date, datetime, time, Decimal
- Optional[bool] -> tristate checkbox
- Union (non-Optional) -> type selector + stacked widget (v2)
- Define conversion rules and error messages explicitly; test them

### Conversion Pipeline
- UIValue -> WireValue -> RuntimeValue conversion contract
- Freeze accepted formats for bool/float/list parsing and JSON validation

### In-Process Limits and Token Injection
- Single in-process task at a time in v1
- No stdout capture by default; label any capture as best-effort
- If signature includes cancel_token/progress parameters, inject those objects deterministically

### Runtime Architecture Shift (Spec-First)
- Generate spec.json + thin launcher; keep UI engine in a runtime package
- This reduces template surface area, improves determinism, and simplifies upgrades
- Support two output modes: thin (default) and standalone scaffold

### UI Scalability
- Use a tree-based ActionList (package -> module -> callable) with search filter
- Details panel: docstring, ParamForm, Run/Cancel, ResultView

### Operational UX for Correctness
- Show InvocationPlan for each action and provide "Copy command"
- Preflight panel: interpreter, sys.path additions, import status, dependency errors
- Run history with inputs, duration, exit code, argv, and env snapshot

### Cancellation Semantics
- In-process: cooperative only (requestInterruption)
- Subprocess: terminate/kill with timeout; document guarantees clearly

---

## Phased Rollout (Exit Criteria)

### Phase 0: Spec Freeze
- Deliverable: AnalysisResult schema + analyze-only -> spec.json
- Exit: stable ordering + snapshot tests pass

### Phase 1: Viewer GUI (No Execution)
- Deliverable: UI renders ActionList + forms from spec
- Exit: widget mapping tests + GUI layout tests pass

### Phase 2: Subprocess Execution (Default)
- Deliverable: child shim for library calls, plus CLI_GENERIC raw args and script/module/entrypoint invocation with cancel/timeout
- Exit: stdout/stderr capture tests + cancel tests pass

### Phase 3: In-Process Execution (Opt-in)
- Deliverable: DIRECT_CALL only, single-task at a time, basic ResultView
- Exit: success + exception + responsiveness tests pass

### Phase 4: Instance Lifecycle (Optional v2)
- Deliverable: create instance flow + method calls
- Exit: instance persistence tests pass

### Phase 5: Hardening + Plugins
- Deliverable: robust imports, logging UI, plugin hooks

---

## Minimum Vertical Slice (End-to-End)
- analyze-only produces spec.json
- viewer GUI loads spec.json and renders ActionList + ParamForm
- pick any action and run via QProcess (child shim for library call)
- stdout/stderr stream live; ResultEnvelope is read from result file
- cancel works on a sleeping action
- coverage targets: library function, script path, console_script entrypoint

Exit criteria:
- structured result displays correctly even with noisy stdout/stderr
- cancel produces a cancelled ResultEnvelope and terminates the process
- exit code and duration are captured in run history

---

## Testing Additions (Accuracy Focus)

### Fixture Corpus ("Nasty" Samples)
- Import side effects (sleep, file write), missing optional deps, forward refs
- Click/Typer/Argparse CLIs, __main__ scripts, console_scripts
- Heavy stdout/stderr, deep exceptions, large results
- Prints without newline or partial line updates
- Class constructors + instance methods, kw-only, varargs/kwargs

### Analysis Mode Tests
- AST-only never imports (sentinel file guard)
- Runtime introspection runs in subprocess and respects timeouts
- Slow import fixture validates introspection timeout and fallback behavior

### Must-Have Regression Tests
- AST-only analysis never imports (side-effect file + sleep fixture)
- Subprocess result file protocol: stdout/stderr noise + structured result + cancel

### GUI Tests (Headless)
- Use QT_QPA_PLATFORM=offscreen and pytest-qt
- Assert widgets + defaults, run/cancel flows, output console updates

### Spec Snapshot Tests
- Snapshot spec.json ordering, not template text

### Property Tests (Conversions)
- Explicit accepted formats for int/float/bool
- JSON parsing for dict/list, enum handling, path normalization

---

## Small Accuracy Upgrades
- Enforce __all__ precedence for public API surface
- Stable callable IDs: module:qualname:signature_hash for config persistence
- Lazy import: import only at execution time
- Result size guards + "save to file" for large outputs
- Traceback UI: friendly summary + expandable details
- Persist last values per callable via QSettings
- Disable Run while running; show explicit running state

---

## Generated Project Structure

### Mode 1: Thin Output (default)

```
my_app_gui/
├── main.py                      # Thin launcher
├── spec.json                    # AnalysisResult
├── overrides.yml                # OPTIONAL: UI overrides/config
└── original_src/                # OPTIONAL: vendored copy of source
    └── (copied from input)
```

Runtime UI engine lives in an installed package (e.g., pyqt6_wrap_runtime).

### Mode 2: Standalone Scaffold (optional)

```
my_app_gui/
├── main.py                      # Entry point
├── pyproject.toml
├── requirements.txt
├── README.md
│
├── ui/
│   ├── __init__.py
│   ├── main_window.py           # Main window with ActionList/details
│   ├── widgets/
│   │   ├── __init__.py
│   │   ├── function_form.py     # Dynamic form generator
│   │   └── output_console.py    # Stdout/stderr display
│   └── dialogs/
│       └── __init__.py
│
├── controllers/
│   ├── __init__.py
│   └── main_controller.py       # Validation, runner orchestration
│
├── services/
│   ├── __init__.py
│   └── wrapped_api.py           # Thin wrappers around original code
│
├── workers/
│   ├── __init__.py
│   └── process_runner.py        # QProcess subprocess runner
│
└── original_src/                # OPTIONAL: vendored copy of source
    └── (copied from input)
```

---

## Generated UI Layout

Note: default layout is a tree-based ActionList with a details panel; the diagram below is illustrative.

```
┌─────────────────────────────────────────────────────────────┐
│  [File]  [Edit]  [Help]                          Menu Bar   │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────┬─────────┬─────────┐                            │
│  │ Tasks   │ Config  │ Users   │            Tabs (1 per     │
│  └─────────┴─────────┴─────────┘            module/group)   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─ create_task() ────────────────────────────────────────┐ │
│  │                                                        │ │
│  │  title:       [________________________]               │ │
│  │  description: [________________________]               │ │
│  │  priority:    [▼ HIGH    ]                             │ │
│  │  status:      [▼ TODO    ]                             │ │
│  │                                                        │ │
│  │                              [ Run create_task() ]     │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌─ get_all_tasks() ──────────────────────────────────────┐ │
│  │  (no parameters)            [ Run get_all_tasks() ]    │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  Output Console                                    [Clear]  │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ > Running create_task()...                              ││
│  │ Created task with ID: 5                                 ││
│  │ > Done (0.02s)                                          ││
│  └─────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────┤
│  Ready                                         Status Bar   │
└─────────────────────────────────────────────────────────────┘
```

---

## Execution Model

### Subprocess Runner (QProcess)

```python
class ProcessRunner(QObject):
    output = pyqtSignal(str)      # stdout/stderr lines
    finished = pyqtSignal(dict)   # ResultEnvelope
    error = pyqtSignal(str)       # non-zero exit or result read error

    def __init__(self, argv, env, result_path):
        super().__init__()
        self.argv = argv
        self.env = env
        self.result_path = result_path
        self.proc = QProcess()

    def start(self):
        self.proc.setProgram(self.argv[0])
        self.proc.setArguments(self.argv[1:])
        self.proc.setProcessEnvironment(self.env)
        self.proc.readyReadStandardOutput.connect(self._read_stdout)
        self.proc.readyReadStandardError.connect(self._read_stderr)
        self.proc.finished.connect(self._on_finished)
        self.proc.start()
```

### Controller Flow

1. User fills form fields
2. User clicks "Run"
3. Controller validates inputs (type conversion)
4. Controller starts runner (QProcess default or in-process opt-in)
5. Runner executes action, streams output
6. Output console displays stdout/stderr in real-time
7. Result displayed when complete (or error shown)

---

## CLI Commands

```bash
# Wrap existing code in a GUI
pyqt6-wrap ./my_project/
pyqt6-wrap ./my_script.py

# Options
pyqt6-wrap ./src/ --output ./my_gui/
pyqt6-wrap ./src/ --copy-source        # Vendor source into output
pyqt6-wrap ./src/ --import-source      # Import from original location (default)
pyqt6-wrap ./src/ --analysis-mode ast-only|introspect
pyqt6-wrap ./src/ --scaffold-mode thin|standalone
pyqt6-wrap ./src/ --runner subprocess|in-process
pyqt6-wrap ./src/ --include "*.py"     # Only analyze matching files
pyqt6-wrap ./src/ --exclude "tests/*"  # Skip patterns

# Show what would be detected (dry run)
pyqt6-wrap ./src/ --analyze-only
```

---

## Implementation Phases

### Phase 1: Enhanced Analyzer ✅
- [x] AST-only scan (no imports) to collect defs, docs, decorators, __all__, __main__ blocks
- [x] Extract defaults; use ast.literal_eval for literals
- [x] Detect entrypoints (main blocks, CLI decorators, argparse usage)
- [x] Build AnalysisResult schema (spec.json) with stable ordering and IDs
- [x] CLI decorator precedence (click/typer fully-qualified → specific plan; bare → CLI_GENERIC)
- [x] __all__ filtering respects class exports (class methods included when parent class exported)
- [x] Signature-based action IDs (stable across line number changes)
- [x] fnmatch-based ignore patterns (*.egg-info, test_*.py)
- [x] Positional-only parameter defaults handled correctly
- [x] 14 automated tests covering all Phase 1 functionality

### Phase 2: Signature Inspector + Enhancements
- [ ] Create `inspector.py` for type-to-widget mapping
- [ ] Handle all basic types (int, str, bool, float)
- [ ] Handle Path types (add file browser)
- [ ] Handle Enum/Literal (populate combobox)
- [ ] Handle Optional (add None checkbox)
- [ ] Add Annotated overrides and date/datetime/time/Decimal
- [ ] Handle *args/**kwargs and keyword-only grouping
- [ ] Define conversion rules and error messages
- [ ] Parse TypeExpr annotations for AST-only type mapping
- [ ] Classify Enum/dataclass definitions for UI hints
- [ ] Detect console_scripts from pyproject.toml/entry_points
- [ ] Optional introspection in subprocess to resolve annotations/signatures

### Phase 3: Spec + Launcher Generator (Thin Mode)
- [ ] Generate spec.json and thin `main.py` launcher
- [ ] Optional overrides.yml for UI/config
- [ ] Keep UI engine in runtime package; standalone scaffold optional
- [ ] Support copy/import source modes

### Phase 4: Execution Runner (Subprocess Default)
- [ ] Implement QProcess runner with stdout/stderr streaming
- [ ] Implement result file protocol + ResultEnvelope
- [ ] Implement child runner shim for library calls (InvocationRequest)
- [ ] Add unbuffered output, working dir, termination policy, and result cleanup
- [ ] Raw args fallback for CLI_GENERIC invocation
- [ ] In-process runner opt-in (single task, no stdout capture by default)

### Phase 5: Dynamic Form Generator
- [ ] Create `ui/widgets/function_form.py`
- [ ] Build form from spec/signature at runtime
- [ ] Wire up "Run" button to controller
- [ ] Display validation errors

### Phase 6: Main Window Generator
- [ ] Tree-based ActionList with search
- [ ] Add function forms to details panel
- [ ] Add output console at bottom
- [ ] Add preflight panel and run history
- [ ] Wire up controller

### Phase 7: Controller Generator
- [ ] Validate and convert form inputs
- [ ] Resolve InvocationPlan and start runner
- [ ] Route output to console
- [ ] Handle errors and show invocation plan

### Phase 8: Polish
- [ ] Generate pyproject.toml
- [ ] Generate README with usage instructions
- [ ] Add dark/light theme support
- [ ] Test with real projects

### Phase 9: Production Hardening
- [ ] Dependency resolution strategy (venv selection, pip/poetry/uv detection)
- [ ] Subprocess execution default + in-process opt-in (timeout, cancel/kill, crash capture)
- [ ] Deterministic outputs (template/version manifest, idempotent regen policy)
- [ ] Logging + diagnostics (log file, debug mode, error dialog with traceback)
- [ ] Config file support (widget overrides, include/exclude, theme, grouping)
- [ ] Plugin/extension hooks for custom widgets and adapters
- [ ] Robust import handling (sys.path management, vendor vs in-place guardrails)
- [ ] Output rendering strategy (ResultEnvelope limits, export, pretty-print, JSON views)

### Phase 10: Testing + CI
- [ ] Unit tests: analyzer detection, signature parsing, ignore rules
- [ ] Unit tests: type-to-widget mapping and conversions (edge cases)
- [ ] Property-based tests for conversions and validation
- [ ] Snapshot/golden tests for spec.json and thin output (standalone optional)
- [ ] Integration tests: CLI flows, copy/import modes, analyze-only
- [ ] GUI tests with pytest-qt (forms, QProcess runner, stdout capture)
- [ ] OS/Python matrix in CI, coverage thresholds, lint/type checks
- [ ] Packaging smoke tests (build + run generated GUI)

---

## Example: What Gets Generated

Note: In thin output mode, the generator emits spec.json + a launcher only. The wrappers below apply to standalone scaffold mode.

### Input: `sample_project/database.py`

```python
def create_task(task: Task, project_id: Optional[int] = None) -> int:
    """Create a new task in the database."""
    ...

def get_all_tasks() -> list[dict]:
    """Get all tasks from the database."""
    ...

def update_task_status(task_id: int, status: Status) -> None:
    """Update the status of a task."""
    ...

def delete_task(task_id: int) -> None:
    """Delete a task from the database."""
    ...
```

### Output (standalone scaffold): `services/wrapped_api.py`

```python
"""Auto-generated service wrappers for database module."""

from sample_project.database import (
    create_task,
    get_all_tasks,
    update_task_status,
    delete_task,
)

class DatabaseService:
    """Wrapper for database.py functions."""

    @staticmethod
    def create_task(task, project_id=None):
        """Create a new task in the database."""
        return create_task(task, project_id)

    @staticmethod
    def get_all_tasks():
        """Get all tasks from the database."""
        return get_all_tasks()

    @staticmethod
    def update_task_status(task_id: int, status):
        """Update the status of a task."""
        return update_task_status(task_id, status)

    @staticmethod
    def delete_task(task_id: int):
        """Delete a task from the database."""
        return delete_task(task_id)
```

### Output: Dynamic Form for `create_task()`

The form generator reads the signature and builds:

```python
# Generated from spec (optionally enriched by inspect.signature)
# Parameters detected:
#   task: Task (complex type -> JSON editor)
#   project_id: Optional[int] (spinbox + None checkbox)

form = FunctionForm(
    name="create_task",
    docstring="Create a new task in the database.",
    parameters=[
        Parameter("task", type=Task, widget=JsonEditor),
        Parameter("project_id", type=Optional[int], widget=OptionalSpinBox),
    ]
)
```

---

## Compatibility

### Supported Input Types
- Pure functions
- Modules with functions
- Classes with staticmethod/classmethod (instance methods in v2)
- CLI tools (click, typer, argparse)
- Scripts with `if __name__ == "__main__"`

### Not Supported (v1)
- Code requiring interactive terminal input (`input()`)
- GUI-to-GUI porting
- Async code (partial support)
- Code with complex side effects

---

## Production-Grade Requirements (Missing)

### Environment & Dependency Management
- Resolve dependencies for the target project (venv path, pip/poetry/uv)
- Allow explicit interpreter selection via CLI/config
- Offer `--copy-source` vs `--import-source` with clear behavior and warnings

### Execution Isolation & Safety
- Default subprocess execution to isolate user code
- Add timeouts and cancellation semantics (terminate/kill)
- Detect and warn about `input()` usage and blocking calls

### Configurability & Extensibility
- Add config file for widget overrides and type coercion
- Provide plugin hooks for custom widgets or adapters
- Allow grouping and labeling overrides for modules/functions

### Observability & Diagnostics
- Structured logs to file
- Error dialogs with stack traces and user-friendly summaries
- Verbose/debug mode to surface import/analysis issues

### Determinism & Upgrades
- Embed generator version in output (manifest)
- Idempotent regeneration rules (overwrite vs merge)
- Stable ordering for modules/functions

---

## Testing Strategy (Extensive)

### Unit + Property Tests
- Analyzer entrypoint detection, ignore rules, public API surface
- Signature parsing, defaults, kw-only, Optional/Union/Enum/Literal handling
- Type coercion with fuzz/property tests for numeric/boolean/list parsing

### Snapshot/Golden Tests
- spec.json and thin output; standalone scaffold optional
- Stable ordering and deterministic output

### Integration Tests
- CLI `wrap` and `analyze-only` flows against sample projects
- Copy/import source modes, missing dependency scenarios
- Subprocess vs in-process execution paths

### GUI Tests (pytest-qt)
- Form rendering for common signatures
- Run/cancel flows with QProcess runner
- Stdout/stderr streaming to output console

### CI + Quality Gates
- Linux/macOS/Windows and Python version matrix
- Coverage thresholds, linting, type checking
- Packaging smoke tests (build + run generated GUI)

---

## Questions Answered

**Q1: Is target input usually a CLI or library?**
Both. Detect CLI decorators for CLIs, detect public functions for libraries.

**Q2: Import in-place or vendor?**
Default: import in-place. Flag `--copy-source` to vendor.

**Q3: One generic runner or multiple tabs?**
Tree-based ActionList with a details panel; optional tabs for high-level grouping.

---

## Prior Art & Research

Existing tools that solve similar problems - we should learn from these:

### 1. Gooey (CLI → GUI)
**What it does**: Decorator that turns argparse CLI into wxPython GUI automatically.
**Key insight**: Parses ArgumentParser at runtime, maps argument types to widgets.
**Source**: [GitHub - chriskiehl/Gooey](https://github.com/chriskiehl/Gooey)

How Gooey works:
- Attaches via `@Gooey` decorator on the method with argparse declarations
- At runtime, parses Python script for ArgumentParser references
- Maps argparse types to wxPython widgets (FileChooser, IntegerField, etc.)
- Speaks JSON internally, decoupled from argparse itself
- GooeyParser extends argparse API with `widget` and `gooey_options` keywords

**What we steal**: The decorator/introspection pattern. We use deterministic mapping with optional `inspect.signature()` enrichment.

---

### 2. magicgui (Type Hints → GUI)
**What it does**: Generates GUI widgets directly from Python type annotations.
**Key insight**: `@magicgui` decorator + type hint → widget mapping.
**Source**: [magicgui Documentation](https://pyapp-kit.github.io/magicgui/)

Built-in type mappings:
| Type | Widget |
|------|--------|
| `bool` | Checkbox |
| `int` | SpinBox |
| `float` | FloatSpinBox |
| `str` | LineEdit |
| `pathlib.Path` | FileEdit |
| `Enum` | ComboBox |
| `Literal['a','b']` | ComboBox |
| `datetime` | DateTimeEdit |
| `range`, `slice` | RangeSlider |

Customization via `Annotated`:
```python
@magicgui(x={'widget_type': 'Slider', 'step': 10, 'max': 50})
def my_func(x: int): ...
```

Third-party registration:
```python
magicgui.register_type(MyType, widget_type=MyWidget)
```

**What we steal**: Their exact type-to-widget mapping table. This is proven and battle-tested.

---

### 3. EZInput (Declarative Parameter Spec)
**What it does**: Cross-environment UI generation (Jupyter, terminal, Colab) from parameter specs.
**Key insight**: "Write once, run anywhere" - same parameter definition works everywhere.
**Source**: [GitHub - HenriquesLab/EZInput](https://github.com/HenriquesLab/EZInput)

Key features:
- Declarative specification: define inputs once, library handles rendering
- Auto-persistence: widget values saved/restored via YAML
- Type-safe validated inputs
- Environment detection (notebook vs terminal)

**What we steal**: The persistence pattern (save/restore last values) and declarative parameter blocks.

---

### 4. PySimpleGUI (Simplified GUI API)
**What it does**: High-level wrapper making GUI creation simpler with Python lists.
**Key insight**: Windows = lists of elements, return values = (event, values dict).
**Source**: [PySimpleGUI Documentation](https://docs.pysimplegui.com/)

Architecture:
- Linear code flow (not callback-based)
- No OOP required
- Every widget has optional parameters for customization
- `key` parameter used to read values from forms

**What we steal**: The linear event loop pattern and the "form returns dict of values" approach.

---

### 5. Pline (CLI → Web UI)
**What it does**: Generates web interfaces for command-line programs from JSON specs.
**Key insight**: Program description + web standards = dynamic GUI.
**Source**: [Pline - wasabiapp.org](http://wasabiapp.org/pline/)

**What we steal**: The idea that a JSON/structured description of a CLI can be mechanically transformed into UI.

---

### 6. Click/Typer Introspection
**How to introspect CLI tools**:
- Typer: `typer.main.get_command(app)` converts Typer app to Click Command
- Click Command has `.params` (list of parameters) and `.commands` (subcommands)
- Each param has: `name`, `type`, `default`, `required`, `help`

**What we steal**: For CLI tools, convert to Click internally, then introspect `.params`.

---

### Key Patterns We're Using

| Pattern | Source | How We Use It |
|---------|--------|---------------|
| Type hint → widget mapping | magicgui | Our inspector.py uses same table |
| Optional runtime introspection | inspect module | `inspect.signature()` when safe |
| Decorator-based analysis | Gooey | Optional `@guiwrap` decorator for hints |
| CLI command introspection | Click/Typer | Convert CLI apps to introspectable objects |
| Declarative parameter specs | EZInput | Config file for widget overrides |
| Value persistence | EZInput | Save/restore last form values |
| Linear event loop | PySimpleGUI | Controller processes events sequentially |
| JSON spec → UI | Pline | Analysis result is structured data → UI |

---

## File Changes Required

### Delete
- `src/pyqt6_gen/templates/` (all old templates)
- `src/pyqt6_gen/wizard.py` (not needed for wrap mode)
- `src/pyqt6_gen/spec_loader.py` (not needed)

### Rewrite
- `src/pyqt6_gen/analyzer.py` → AST-only analysis + optional introspection, spec.json output
- `src/pyqt6_gen/generator.py` → Generate spec.json + thin launcher; optional standalone scaffold
- `src/pyqt6_gen/cli.py` → New `wrap` command with modes
- `src/pyqt6_gen/config.py` → UI overrides and mapping config

### New Files
- `src/pyqt6_gen/inspector.py` → Type-to-widget mapping
- `src/pyqt6_wrap_runtime/` → Runtime UI engine and QProcess runner
- `src/pyqt6_gen/templates/wrap/` → Standalone scaffold templates (optional)

---

## Verification

1. Run `pyqt6-wrap ./examples/sample_project/`
2. Verify it detects: `create_task`, `get_all_tasks`, `update_task_status`, `delete_task`
3. Verify generated GUI shows ActionList tree and details panel
4. Verify forms have correct widgets for each parameter type
5. Click "Run" on `get_all_tasks()` → see results in console
6. Fill form for `create_task()`, click Run → see task created

"""Data models for the AnalysisResult schema (spec.json).

This module defines the structured output of code analysis, which drives
the GUI generation process.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class AnalysisMode(str, Enum):
    """How the analysis was performed."""
    AST_ONLY = "ast_only"
    INTROSPECT = "introspect"


class InvocationPlan(str, Enum):
    """How each action should be invoked at runtime."""
    DIRECT_CALL = "direct_call"
    MODULE_AS_SCRIPT = "module_as_script"
    SCRIPT_PATH = "script_path"
    CLICK_COMMAND = "click_command"
    TYPER_COMMAND = "typer_command"
    CONSOLE_SCRIPT_ENTRYPOINT = "console_script_entrypoint"
    CLI_GENERIC = "cli_generic"


class ActionKind(str, Enum):
    """The kind of callable detected."""
    FUNCTION = "function"
    METHOD = "method"
    STATICMETHOD = "staticmethod"
    CLASSMETHOD = "classmethod"
    CLASS = "class"
    ENTRYPOINT = "entrypoint"
    CLI_COMMAND = "cli_command"


class ParamKind(str, Enum):
    """Parameter kind from inspect module."""
    POSITIONAL_ONLY = "positional_only"
    POSITIONAL_OR_KEYWORD = "positional_or_keyword"
    VAR_POSITIONAL = "var_positional"
    KEYWORD_ONLY = "keyword_only"
    VAR_KEYWORD = "var_keyword"


class WidgetType(str, Enum):
    """Widget types for parameter input."""
    SPIN_BOX = "spin_box"
    DOUBLE_SPIN_BOX = "double_spin_box"
    CHECK_BOX = "check_box"
    LINE_EDIT = "line_edit"
    FILE_PICKER = "file_picker"
    COMBO_BOX = "combo_box"
    PLAIN_TEXT_EDIT = "plain_text_edit"
    JSON_EDITOR = "json_editor"
    DATE_EDIT = "date_edit"
    DATETIME_EDIT = "datetime_edit"
    TIME_EDIT = "time_edit"


class ResultKind(str, Enum):
    """Result display types."""
    NONE = "none"
    TEXT = "text"
    JSON = "json"
    TABLE = "table"
    FILE = "file"
    REPR = "repr"


@dataclass
class DefaultValue:
    """Represents a parameter's default value."""
    present: bool = False
    repr: str | None = None
    literal: Any = None
    is_literal: bool = False


@dataclass
class Annotation:
    """Type annotation information."""
    raw: str | None = None
    resolved: str | None = None


@dataclass
class ParamUI:
    """UI configuration for a parameter."""
    widget: WidgetType = WidgetType.LINE_EDIT
    options: list[str] = field(default_factory=list)


@dataclass
class ParamValidation:
    """Validation rules for a parameter."""
    min: float | None = None
    max: float | None = None
    regex: str | None = None


@dataclass
class ParamSpec:
    """Specification for a function/method parameter."""
    name: str
    kind: ParamKind = ParamKind.POSITIONAL_OR_KEYWORD
    required: bool = True
    default: DefaultValue = field(default_factory=DefaultValue)
    annotation: Annotation = field(default_factory=Annotation)
    ui: ParamUI = field(default_factory=ParamUI)
    validation: ParamValidation = field(default_factory=ParamValidation)


@dataclass
class ReturnUI:
    """UI configuration for return value display."""
    result_kind: ResultKind = ResultKind.TEXT
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReturnSpec:
    """Specification for a function/method return value."""
    annotation: Annotation = field(default_factory=Annotation)
    ui: ReturnUI = field(default_factory=ReturnUI)


@dataclass
class DocSpec:
    """Documentation for a callable."""
    text: str | None = None
    format: str = "plain"


@dataclass
class IntrospectionStatus:
    """Status of runtime introspection for a callable."""
    attempted: bool = False
    success: bool = False
    error: str | None = None
    annotations_resolved: bool = False


@dataclass
class ActionSpec:
    """Specification for a callable action (function, method, etc.)."""
    action_id: str
    kind: ActionKind
    qualname: str
    name: str
    module_import_path: str
    doc: DocSpec = field(default_factory=DocSpec)
    parameters: list[ParamSpec] = field(default_factory=list)
    returns: ReturnSpec = field(default_factory=ReturnSpec)
    invocation_plan: InvocationPlan = InvocationPlan.DIRECT_CALL
    introspection: IntrospectionStatus = field(default_factory=IntrospectionStatus)
    tags: list[str] = field(default_factory=list)
    side_effect_risk: bool = False
    source_line: int | None = None


@dataclass
class ModuleSpec:
    """Specification for an analyzed module."""
    module_id: str
    display_name: str
    file_path: str | None = None
    import_path: str | None = None
    actions: list[ActionSpec] = field(default_factory=list)
    has_main_block: bool = False
    all_exports: list[str] | None = None
    side_effect_risk: bool = False


@dataclass
class Warning:
    """Analysis warning."""
    code: str
    message: str
    file_path: str | None = None
    line: int | None = None


@dataclass
class AnalysisResult:
    """Top-level analysis result (spec.json)."""
    spec_version: str = "1.0"
    generator_version: str = "0.1.0"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    project_root: str = ""
    analysis_mode: AnalysisMode = AnalysisMode.AST_ONLY
    python_target: str | None = None
    modules: list[ModuleSpec] = field(default_factory=list)
    warnings: list[Warning] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return _to_dict(self)


def _to_dict(obj: Any) -> Any:
    """Recursively convert dataclass to dict."""
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _to_dict(v) for k, v in obj.__dict__.items()}
    elif isinstance(obj, Enum):
        return obj.value
    elif isinstance(obj, list):
        return [_to_dict(item) for item in obj]
    elif isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    return obj

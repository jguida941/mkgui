"""Type-to-widget mapping inspector.

Parses Python type annotations (as strings from AST) and determines
the appropriate PyQt6 widget and conversion rules.
"""

import ast
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .models import ParamKind, ParamSpec, ParamUI, ParamValidation, WidgetType


class TypeCategory(str, Enum):
    """Categories of types for widget mapping."""
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    STRING = "string"
    PATH = "path"
    ENUM = "enum"
    LITERAL = "literal"
    OPTIONAL = "optional"
    LIST = "list"
    DICT = "dict"
    DATE = "date"
    DATETIME = "datetime"
    TIME = "time"
    DECIMAL = "decimal"
    ANY = "any"
    UNKNOWN = "unknown"


@dataclass
class TypeInfo:
    """Parsed type information."""
    category: TypeCategory
    raw: str
    inner_type: "TypeInfo | None" = None  # For Optional[T], List[T]
    options: list[str] = field(default_factory=list)  # For Enum/Literal values
    is_optional: bool = False
    widget: WidgetType = WidgetType.LINE_EDIT
    validation: ParamValidation = field(default_factory=ParamValidation)


# Regex patterns for parsing type annotations (fallback only)
# Support both bare names and typing.* prefixed forms
#
# CONTRACT: Date/time conversion assumes ISO format strings. The UI layer
# must call .toString(Qt.ISODate) for QDate/QDateTime/QTime widgets.
_OPTIONAL_PATTERN = re.compile(r"^(?:typing\.)?Optional\[(.+)\]$")
_UNION_NONE_PATTERN = re.compile(r"^(?:typing\.)?Union\[(.+),\s*None\]$|^(?:typing\.)?Union\[None,\s*(.+)\]$")
_PIPE_NONE_PATTERN = re.compile(r"^(.+)\s*\|\s*None$|^None\s*\|\s*(.+)$")
_LIST_PATTERN = re.compile(r"^(?:typing\.)?(?:list|List)\[(.+)\]$")
_TUPLE_PATTERN = re.compile(r"^(?:typing\.)?(?:tuple|Tuple)\[(.+)\]$")
_DICT_PATTERN = re.compile(r"^(?:typing\.)?(?:dict|Dict)(?:\[.+\])?$")
_LITERAL_PATTERN = re.compile(r"^(?:typing\.)?Literal\[(.+)\]$")
_ANNOTATED_PATTERN = re.compile(r"^(?:typing\.)?Annotated\[(.+?),\s*(.+)\]$")

# Simple type mappings
_SIMPLE_TYPES: dict[str, TypeCategory] = {
    "int": TypeCategory.INTEGER,
    "float": TypeCategory.FLOAT,
    "bool": TypeCategory.BOOLEAN,
    "str": TypeCategory.STRING,
    "list": TypeCategory.LIST,
    "List": TypeCategory.LIST,
    "set": TypeCategory.LIST,
    "Set": TypeCategory.LIST,
    "tuple": TypeCategory.LIST,
    "Tuple": TypeCategory.LIST,
    "dict": TypeCategory.DICT,
    "Dict": TypeCategory.DICT,
    "Path": TypeCategory.PATH,
    "pathlib.Path": TypeCategory.PATH,
    "PurePath": TypeCategory.PATH,
    "date": TypeCategory.DATE,
    "datetime.date": TypeCategory.DATE,
    "datetime": TypeCategory.DATETIME,
    "datetime.datetime": TypeCategory.DATETIME,
    "time": TypeCategory.TIME,
    "datetime.time": TypeCategory.TIME,
    "Decimal": TypeCategory.DECIMAL,
    "decimal.Decimal": TypeCategory.DECIMAL,
    "Any": TypeCategory.ANY,
    "typing.Any": TypeCategory.ANY,
    "object": TypeCategory.ANY,
    "None": TypeCategory.ANY,
    "NoneType": TypeCategory.ANY,
}

# Widget mappings by category
_CATEGORY_WIDGETS: dict[TypeCategory, WidgetType] = {
    TypeCategory.INTEGER: WidgetType.SPIN_BOX,
    TypeCategory.FLOAT: WidgetType.DOUBLE_SPIN_BOX,
    TypeCategory.BOOLEAN: WidgetType.CHECK_BOX,
    TypeCategory.STRING: WidgetType.LINE_EDIT,
    TypeCategory.PATH: WidgetType.FILE_PICKER,
    TypeCategory.ENUM: WidgetType.COMBO_BOX,
    TypeCategory.LITERAL: WidgetType.COMBO_BOX,
    TypeCategory.LIST: WidgetType.PLAIN_TEXT_EDIT,
    TypeCategory.DICT: WidgetType.JSON_EDITOR,
    TypeCategory.DATE: WidgetType.DATE_EDIT,
    TypeCategory.DATETIME: WidgetType.DATETIME_EDIT,
    TypeCategory.TIME: WidgetType.TIME_EDIT,
    TypeCategory.DECIMAL: WidgetType.LINE_EDIT,  # String input with validation
    TypeCategory.ANY: WidgetType.JSON_EDITOR,
    TypeCategory.UNKNOWN: WidgetType.LINE_EDIT,
    TypeCategory.OPTIONAL: WidgetType.LINE_EDIT,  # Determined by inner type
}

_PATH_NAME_HINTS = ("path", "file", "dir", "folder", "directory")


def _normalize_widget_name(name: str) -> str:
    """Normalize widget name for lookup."""
    return name.strip().lower().replace("-", "_")


_WIDGET_ALIASES: dict[str, WidgetType] = {}
for _widget in WidgetType:
    _WIDGET_ALIASES[_normalize_widget_name(_widget.value)] = _widget
    _WIDGET_ALIASES[_normalize_widget_name(_widget.name)] = _widget


def _parse_widget_override(value: object) -> WidgetType | None:
    """Parse a widget override into a WidgetType."""
    if isinstance(value, WidgetType):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.startswith("WidgetType."):
        text = text.split(".", 1)[1]
    key = _normalize_widget_name(text)
    return _WIDGET_ALIASES.get(key)


def _coerce_number(value: object) -> float | int | None:
    """Coerce a value into a number if possible."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            if any(char in text.lower() for char in (".", "e")):
                return float(text)
            return int(text)
        except ValueError:
            try:
                return float(text)
            except ValueError:
                return None
    return None


def _looks_like_path_name(name: str) -> bool:
    """Return True if a parameter name suggests a filesystem path."""
    lowered = name.lower()
    return any(token in lowered for token in _PATH_NAME_HINTS)


def _coerce_options(value: object) -> list[str] | None:
    """Coerce a value into a list of string options."""
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        return [part.strip() for part in text.split(",") if part.strip()]
    return None


def _parse_metadata_string(value: str) -> dict[str, object]:
    """Parse a key=value metadata string."""
    if "=" not in value:
        return {}
    key, raw_value = value.split("=", 1)
    key = key.strip()
    raw_value = raw_value.strip()
    if not key:
        return {}
    try:
        parsed_value = ast.literal_eval(raw_value)
    except (ValueError, SyntaxError):
        parsed_value = raw_value
    return {key: parsed_value}


def _is_annotated_base(node: ast.AST) -> bool:
    """Check if a node refers to typing.Annotated."""
    if isinstance(node, ast.Name):
        return node.id == "Annotated"
    if isinstance(node, ast.Attribute):
        return node.attr == "Annotated"
    return False


def _parse_annotated(raw: str) -> tuple[str, list[object]] | None:
    """Parse Annotated[T, ...] into base type and metadata list."""
    try:
        expr = ast.parse(raw, mode="eval").body
    except SyntaxError:
        return None
    if not isinstance(expr, ast.Subscript):
        return None
    if not _is_annotated_base(expr.value):
        return None
    slice_node = expr.slice
    if isinstance(slice_node, ast.Tuple):
        elements = list(slice_node.elts)
    else:
        elements = [slice_node]
    if not elements:
        return None
    base_node = elements[0]
    metadata_nodes = elements[1:]
    base_type = ast.unparse(base_node)
    metadata_values: list[object] = []
    for node in metadata_nodes:
        try:
            metadata_values.append(ast.literal_eval(node))
        except (ValueError, TypeError, SyntaxError):
            metadata_values.append(ast.unparse(node))
    return base_type, metadata_values


def _apply_annotated_metadata(info: TypeInfo, metadata_values: list[object]) -> None:
    """Apply Annotated metadata overrides to TypeInfo."""
    overrides: dict[str, object] = {}

    for meta in metadata_values:
        if isinstance(meta, dict):
            overrides.update(meta)
        elif isinstance(meta, str):
            overrides.update(_parse_metadata_string(meta))
        elif isinstance(meta, (list, tuple, set)):
            if "options" not in overrides and "choices" not in overrides:
                overrides["options"] = meta

    widget_override = _parse_widget_override(
        overrides.get("widget") or overrides.get("widget_type")
    )
    if widget_override is not None:
        info.widget = widget_override

    options_value = overrides.get("options") or overrides.get("choices")
    options = _coerce_options(options_value) if options_value is not None else None
    if options is not None:
        info.options = options
        if widget_override is None and info.widget != WidgetType.COMBO_BOX:
            info.widget = WidgetType.COMBO_BOX

    min_value = _coerce_number(overrides.get("min")) if "min" in overrides else None
    max_value = _coerce_number(overrides.get("max")) if "max" in overrides else None
    if min_value is not None:
        info.validation.min = min_value
    if max_value is not None:
        info.validation.max = max_value

    if "regex" in overrides and overrides["regex"] is not None:
        info.validation.regex = str(overrides["regex"])


def _subscript_elements(node: ast.AST) -> list[ast.AST]:
    """Return subscript slice elements as a list."""
    if isinstance(node, ast.Tuple):
        return list(node.elts)
    return [node]


def _is_none_expr(node: ast.AST) -> bool:
    """Check if a node represents None."""
    if isinstance(node, ast.Constant):
        return node.value is None
    if isinstance(node, ast.Name):
        return node.id == "None"
    return False


def _literal_options_from_nodes(nodes: list[ast.AST]) -> list[str]:
    """Convert Literal nodes into option strings."""
    options: list[str] = []
    for node in nodes:
        try:
            value = ast.literal_eval(node)
        except (ValueError, TypeError, SyntaxError):
            value = ast.unparse(node)
        if isinstance(value, str):
            options.append(value)
        else:
            options.append(str(value))
    return options


def _type_info_from_name(raw_name: str) -> TypeInfo:
    """Create TypeInfo from a simple name or attribute."""
    raw_name = raw_name.strip()
    if raw_name in _SIMPLE_TYPES:
        category = _SIMPLE_TYPES[raw_name]
        return TypeInfo(
            category=category,
            raw=raw_name,
            widget=_CATEGORY_WIDGETS[category],
            validation=_get_default_validation(category),
        )

    base_name = raw_name.split(".")[-1]
    if base_name in _SIMPLE_TYPES:
        category = _SIMPLE_TYPES[base_name]
        return TypeInfo(
            category=category,
            raw=raw_name,
            widget=_CATEGORY_WIDGETS[category],
            validation=_get_default_validation(category),
        )

    if _looks_like_enum(raw_name):
        return TypeInfo(
            category=TypeCategory.ENUM,
            raw=raw_name,
            widget=WidgetType.LINE_EDIT,
        )

    return TypeInfo(
        category=TypeCategory.UNKNOWN,
        raw=raw_name,
        widget=WidgetType.LINE_EDIT,
    )


def _type_info_from_expr(expr: ast.AST) -> TypeInfo | None:
    """Parse TypeInfo from an annotation expression."""
    if isinstance(expr, ast.Constant):
        if isinstance(expr.value, str):
            return _parse_type_annotation_ast(expr.value)
        if expr.value is None:
            return _type_info_from_name("None")
        return None

    if isinstance(expr, (ast.Name, ast.Attribute)):
        return _type_info_from_name(ast.unparse(expr))

    if isinstance(expr, ast.Subscript):
        base_full = ast.unparse(expr.value)
        base_name = base_full.split(".")[-1]
        elements = _subscript_elements(expr.slice)
        if not elements:
            return None

        if base_name == "Annotated":
            base_expr = elements[0]
            metadata_nodes = elements[1:]
            info = _type_info_from_expr(base_expr)
            if info is None:
                info = TypeInfo(
                    category=TypeCategory.UNKNOWN,
                    raw=ast.unparse(base_expr),
                    widget=WidgetType.LINE_EDIT,
                )
            metadata_values: list[object] = []
            for node in metadata_nodes:
                try:
                    metadata_values.append(ast.literal_eval(node))
                except (ValueError, TypeError, SyntaxError):
                    metadata_values.append(ast.unparse(node))
            _apply_annotated_metadata(info, metadata_values)
            return info

        if base_name == "Optional":
            inner = _type_info_from_expr(elements[0])
            if inner is None:
                inner = TypeInfo(
                    category=TypeCategory.UNKNOWN,
                    raw=ast.unparse(elements[0]),
                    widget=WidgetType.LINE_EDIT,
                )
            inner.is_optional = True
            return inner

        if base_name == "Union":
            non_none = [node for node in elements if not _is_none_expr(node)]
            none_count = len(elements) - len(non_none)
            if none_count >= 1 and len(non_none) == 1:
                inner = _type_info_from_expr(non_none[0])
                if inner is None:
                    inner = TypeInfo(
                        category=TypeCategory.UNKNOWN,
                        raw=ast.unparse(non_none[0]),
                        widget=WidgetType.LINE_EDIT,
                    )
                inner.is_optional = True
                return inner
            return TypeInfo(
                category=TypeCategory.UNKNOWN,
                raw=ast.unparse(expr),
                widget=WidgetType.LINE_EDIT,
            )

        if base_name in ("List", "list", "Tuple", "tuple", "Set", "set"):
            inner = _type_info_from_expr(elements[0])
            return TypeInfo(
                category=TypeCategory.LIST,
                raw=ast.unparse(expr),
                inner_type=inner,
                widget=WidgetType.PLAIN_TEXT_EDIT,
            )

        if base_name in ("Dict", "dict"):
            return TypeInfo(
                category=TypeCategory.DICT,
                raw=ast.unparse(expr),
                widget=WidgetType.JSON_EDITOR,
            )

        if base_name == "Literal":
            options = _literal_options_from_nodes(elements)
            return TypeInfo(
                category=TypeCategory.LITERAL,
                raw=ast.unparse(expr),
                options=options,
                widget=WidgetType.COMBO_BOX,
            )

        return TypeInfo(
            category=TypeCategory.UNKNOWN,
            raw=ast.unparse(expr),
            widget=WidgetType.LINE_EDIT,
        )

    if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.BitOr):
        if _is_none_expr(expr.left):
            inner = _type_info_from_expr(expr.right)
            if inner is None:
                inner = TypeInfo(
                    category=TypeCategory.UNKNOWN,
                    raw=ast.unparse(expr.right),
                    widget=WidgetType.LINE_EDIT,
                )
            inner.is_optional = True
            return inner
        if _is_none_expr(expr.right):
            inner = _type_info_from_expr(expr.left)
            if inner is None:
                inner = TypeInfo(
                    category=TypeCategory.UNKNOWN,
                    raw=ast.unparse(expr.left),
                    widget=WidgetType.LINE_EDIT,
                )
            inner.is_optional = True
            return inner
        return TypeInfo(
            category=TypeCategory.UNKNOWN,
            raw=ast.unparse(expr),
            widget=WidgetType.LINE_EDIT,
        )

    return None


def _parse_type_annotation_ast(raw: str) -> TypeInfo | None:
    """Parse a type annotation string via AST."""
    try:
        expr = ast.parse(raw, mode="eval").body
    except SyntaxError:
        return None

    info = _type_info_from_expr(expr)
    if info is not None:
        info.raw = raw
    return info


def _extract_base_type(raw: str) -> str:
    """Extract the base type from Optional/Annotated wrappers."""
    annotated = _parse_annotated(raw)
    if annotated:
        return _extract_base_type(annotated[0])

    optional_match = _OPTIONAL_PATTERN.match(raw)
    if optional_match:
        return _extract_base_type(optional_match.group(1))

    union_none_match = _UNION_NONE_PATTERN.match(raw)
    if union_none_match:
        inner_type = union_none_match.group(1) or union_none_match.group(2)
        return _extract_base_type(inner_type)

    pipe_none_match = _PIPE_NONE_PATTERN.match(raw)
    if pipe_none_match:
        inner_type = pipe_none_match.group(1) or pipe_none_match.group(2)
        return _extract_base_type(inner_type)

    return raw


def parse_type_annotation(raw: str | None) -> TypeInfo:
    """Parse a type annotation string and return TypeInfo.

    Args:
        raw: The raw type annotation string from AST (e.g., "int", "Optional[str]")

    Returns:
        TypeInfo with category, widget type, and any parsed options
    """
    if not raw:
        return TypeInfo(
            category=TypeCategory.UNKNOWN,
            raw="",
            widget=WidgetType.LINE_EDIT,
        )

    raw = raw.strip()

    ast_info = _parse_type_annotation_ast(raw)
    if ast_info is not None:
        return ast_info

    # Handle Annotated[T, metadata]
    annotated = _parse_annotated(raw)
    if annotated:
        base_type, metadata_values = annotated
        info = parse_type_annotation(base_type)
        info.raw = raw
        _apply_annotated_metadata(info, metadata_values)
        return info

    annotated_match = _ANNOTATED_PATTERN.match(raw)
    if annotated_match:
        base_type = annotated_match.group(1)
        info = parse_type_annotation(base_type)
        info.raw = raw
        return info

    # Handle Optional[T] / Union[T, None] / T | None
    optional_match = _OPTIONAL_PATTERN.match(raw)
    if optional_match:
        inner = parse_type_annotation(optional_match.group(1))
        inner.is_optional = True
        inner.raw = raw
        return inner

    union_none_match = _UNION_NONE_PATTERN.match(raw)
    if union_none_match:
        inner_type = union_none_match.group(1) or union_none_match.group(2)
        inner = parse_type_annotation(inner_type)
        inner.is_optional = True
        inner.raw = raw
        return inner

    pipe_none_match = _PIPE_NONE_PATTERN.match(raw)
    if pipe_none_match:
        inner_type = pipe_none_match.group(1) or pipe_none_match.group(2)
        inner = parse_type_annotation(inner_type)
        inner.is_optional = True
        inner.raw = raw
        return inner

    # Handle Literal["a", "b", "c"]
    literal_match = _LITERAL_PATTERN.match(raw)
    if literal_match:
        options = _parse_literal_values(literal_match.group(1))
        return TypeInfo(
            category=TypeCategory.LITERAL,
            raw=raw,
            options=options,
            widget=WidgetType.COMBO_BOX,
        )

    # Handle list[T] / List[T]
    list_match = _LIST_PATTERN.match(raw)
    if list_match:
        inner = parse_type_annotation(list_match.group(1))
        return TypeInfo(
            category=TypeCategory.LIST,
            raw=raw,
            inner_type=inner,
            widget=WidgetType.PLAIN_TEXT_EDIT,
        )

    # Handle tuple[T, ...] / Tuple[T, ...]
    tuple_match = _TUPLE_PATTERN.match(raw)
    if tuple_match:
        # Treat tuples like lists for input purposes
        inner = parse_type_annotation(tuple_match.group(1).split(",")[0].strip())
        return TypeInfo(
            category=TypeCategory.LIST,
            raw=raw,
            inner_type=inner,
            widget=WidgetType.PLAIN_TEXT_EDIT,
        )

    # Handle dict / Dict[K, V]
    if _DICT_PATTERN.match(raw):
        return TypeInfo(
            category=TypeCategory.DICT,
            raw=raw,
            widget=WidgetType.JSON_EDITOR,
        )

    # Handle simple types
    if raw in _SIMPLE_TYPES:
        category = _SIMPLE_TYPES[raw]
        return TypeInfo(
            category=category,
            raw=raw,
            widget=_CATEGORY_WIDGETS[category],
            validation=_get_default_validation(category),
        )

    # Check if it looks like an Enum (heuristic: PascalCase and not a known type)
    # Use LineEdit since we don't have enum values without runtime introspection
    # ComboBox would be empty and unusable
    if _looks_like_enum(raw):
        return TypeInfo(
            category=TypeCategory.ENUM,
            raw=raw,
            widget=WidgetType.LINE_EDIT,  # Fallback until runtime introspection
        )

    # Unknown type - default to line edit
    return TypeInfo(
        category=TypeCategory.UNKNOWN,
        raw=raw,
        widget=WidgetType.LINE_EDIT,
    )


def _parse_literal_values(literal_content: str) -> list[str]:
    """Parse the values inside Literal[...].

    Handles: Literal["a", "b", 1, 2, True]
    """
    values = []
    # Simple split by comma, handling quoted strings
    parts = []
    current = ""
    in_string = False
    string_char = None

    for char in literal_content:
        if char in ('"', "'") and not in_string:
            in_string = True
            string_char = char
            current += char
        elif char == string_char and in_string:
            in_string = False
            string_char = None
            current += char
        elif char == "," and not in_string:
            parts.append(current.strip())
            current = ""
        else:
            current += char

    if current.strip():
        parts.append(current.strip())

    for part in parts:
        # Remove quotes from strings
        if (part.startswith('"') and part.endswith('"')) or \
           (part.startswith("'") and part.endswith("'")):
            values.append(part[1:-1])
        else:
            values.append(part)

    return values


def _looks_like_enum(raw: str) -> bool:
    """Heuristic to detect if a type might be an Enum.

    Looks for PascalCase names that aren't known types.
    """
    if not raw:
        return False

    # Remove module prefix if present
    name = raw.split(".")[-1]

    # Check if PascalCase (starts with uppercase, has lowercase)
    if not name or not name[0].isupper():
        return False

    # Known non-enum types
    known_non_enums = {
        "Path", "PurePath", "Decimal", "Any", "None", "NoneType",
        "List", "Dict", "Set", "Tuple", "Optional", "Union",
        "Callable", "Type", "Generic", "Protocol",
    }
    if name in known_non_enums:
        return False

    return True


def _get_default_validation(category: TypeCategory) -> ParamValidation:
    """Get default validation rules for a type category."""
    if category == TypeCategory.INTEGER:
        return ParamValidation(min=-999999, max=999999)
    elif category == TypeCategory.FLOAT:
        return ParamValidation(min=-999999.0, max=999999.0)
    return ParamValidation()


def inspect_parameter(
    param: ParamSpec,
    enum_options: dict[str, list[str]] | None = None,
    dataclass_names: set[str] | None = None,
) -> ParamSpec:
    """Inspect a parameter and update its UI configuration based on type.

    Args:
        param: The parameter specification from the analyzer

    Returns:
        Updated parameter with widget type and validation set
    """
    if param.kind == ParamKind.VAR_POSITIONAL:
        param.ui = ParamUI(widget=WidgetType.PLAIN_TEXT_EDIT)
        param.validation = ParamValidation()
        return param

    if param.kind == ParamKind.VAR_KEYWORD:
        param.ui = ParamUI(widget=WidgetType.JSON_EDITOR)
        param.validation = ParamValidation()
        return param

    type_info = parse_type_annotation(param.annotation.raw)
    if type_info.category == TypeCategory.UNKNOWN and _looks_like_path_name(param.name):
        type_info.category = TypeCategory.PATH
        type_info.widget = WidgetType.FILE_PICKER

    # Update the parameter's UI configuration
    param.ui = ParamUI(
        widget=type_info.widget,
        options=type_info.options,
    )
    param.validation = type_info.validation

    base_type = _extract_base_type(param.annotation.raw or "")

    if enum_options and type_info.category == TypeCategory.ENUM:
        enum_name = base_type.split(".")[-1]
        options = enum_options.get(enum_name)
        if options:
            param.ui.widget = WidgetType.COMBO_BOX
            param.ui.options = options
            return param

    if dataclass_names:
        class_name = base_type.split(".")[-1]
        if class_name in dataclass_names:
            param.ui.widget = WidgetType.JSON_EDITOR
            return param

    # Mark as optional if type is Optional[T]
    if type_info.is_optional and param.required:
        param.required = False

    return param


def inspect_parameters(
    params: list[ParamSpec],
    enum_options: dict[str, list[str]] | None = None,
    dataclass_names: set[str] | None = None,
) -> list[ParamSpec]:
    """Inspect all parameters and update their UI configurations.

    Args:
        params: List of parameter specifications from the analyzer

    Returns:
        Updated parameters with widget types and validation set
    """
    return [
        inspect_parameter(
            p,
            enum_options=enum_options,
            dataclass_names=dataclass_names,
        )
        for p in params
    ]


# ============================================================================
# Conversion Rules: UI Value → Python Value
# ============================================================================

@dataclass
class ConversionError:
    """Error during value conversion."""
    message: str
    field: str
    value: Any


@dataclass
class ConversionResult:
    """Result of converting a UI value to a Python value."""
    success: bool
    value: Any = None
    error: ConversionError | None = None


def _is_empty_value(value: Any) -> bool:
    """Check if a value represents 'empty' input.

    Only None and empty string "" are considered empty.
    False, 0, and other falsy values are valid inputs.
    """
    return value is None or value == ""


def convert_value(ui_value: Any, type_info: TypeInfo) -> ConversionResult:
    """Convert a UI widget value to the appropriate Python type.

    Args:
        ui_value: The value from the UI widget (str, bool, int, etc.)
        type_info: The parsed type information

    Returns:
        ConversionResult with success status and converted value or error
    """
    # Handle empty values for optional types
    if _is_empty_value(ui_value) and type_info.is_optional:
        return ConversionResult(success=True, value=None)

    # Handle empty values for required types
    if _is_empty_value(ui_value):
        return ConversionResult(
            success=False,
            error=ConversionError(
                message="Value is required",
                field="",
                value=ui_value,
            )
        )

    # If value is already the correct type (e.g., bool from checkbox, int from spinbox),
    # return it directly without string conversion
    if type_info.category == TypeCategory.BOOLEAN and isinstance(ui_value, bool):
        return ConversionResult(success=True, value=ui_value)
    if type_info.category == TypeCategory.INTEGER and isinstance(ui_value, int) and not isinstance(ui_value, bool):
        return ConversionResult(success=True, value=ui_value)
    if type_info.category == TypeCategory.FLOAT and isinstance(ui_value, (int, float)) and not isinstance(ui_value, bool):
        return ConversionResult(success=True, value=float(ui_value))

    # Convert string values
    try:
        value = _convert_by_category(str(ui_value), type_info)
        return ConversionResult(success=True, value=value)
    except ValueError as e:
        return ConversionResult(
            success=False,
            error=ConversionError(
                message=str(e),
                field="",
                value=ui_value,
            )
        )


def _convert_by_category(ui_value: str, type_info: TypeInfo) -> Any:
    """Convert value based on type category."""
    category = type_info.category

    if category == TypeCategory.INTEGER:
        return _convert_int(ui_value)
    elif category == TypeCategory.FLOAT:
        return _convert_float(ui_value)
    elif category == TypeCategory.BOOLEAN:
        return _convert_bool(ui_value)
    elif category == TypeCategory.STRING:
        return ui_value
    elif category == TypeCategory.PATH:
        return ui_value  # Path conversion happens at runtime
    elif category in (TypeCategory.ENUM, TypeCategory.LITERAL):
        return ui_value  # Already selected from valid options
    elif category == TypeCategory.LIST:
        return _convert_list(ui_value, type_info.inner_type)
    elif category == TypeCategory.DICT:
        return _convert_json(ui_value)
    elif category == TypeCategory.DATE:
        return ui_value  # Date string in ISO format
    elif category == TypeCategory.DATETIME:
        return ui_value  # Datetime string in ISO format
    elif category == TypeCategory.TIME:
        return ui_value  # Time string in ISO format
    elif category == TypeCategory.DECIMAL:
        return _convert_decimal(ui_value)
    elif category in (TypeCategory.ANY, TypeCategory.UNKNOWN):
        # Try JSON first, fall back to string
        try:
            return _convert_json(ui_value)
        except ValueError:
            return ui_value

    return ui_value


def _convert_int(value: str) -> int:
    """Convert string to integer."""
    value = value.strip()
    try:
        # Handle hex, octal, binary
        if value.startswith(("0x", "0X")):
            return int(value, 16)
        elif value.startswith(("0o", "0O")):
            return int(value, 8)
        elif value.startswith(("0b", "0B")):
            return int(value, 2)
        return int(value)
    except ValueError:
        raise ValueError(f"Invalid integer: {value!r}")


def _convert_float(value: str) -> float:
    """Convert string to float."""
    value = value.strip()
    try:
        return float(value)
    except ValueError:
        raise ValueError(f"Invalid number: {value!r}")


def _convert_bool(value: str) -> bool:
    """Convert string to boolean."""
    value = value.strip().lower()
    if value in ("true", "1", "yes", "on"):
        return True
    elif value in ("false", "0", "no", "off"):
        return False
    raise ValueError(f"Invalid boolean: {value!r}. Use true/false, 1/0, yes/no")


def _convert_list(value: str, inner_type: TypeInfo | None) -> list:
    """Convert multiline string to list."""
    lines = [line.strip() for line in value.strip().split("\n") if line.strip()]

    if inner_type:
        return [_convert_by_category(line, inner_type) for line in lines]
    return lines


def _convert_json(value: str) -> Any:
    """Convert JSON string to Python object."""
    import json
    try:
        return json.loads(value)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}")


def _convert_decimal(value: str) -> str:
    """Validate decimal string (actual Decimal conversion happens at runtime)."""
    value = value.strip()
    try:
        float(value)  # Validate it's a valid number
        return value
    except ValueError:
        raise ValueError(f"Invalid decimal: {value!r}")

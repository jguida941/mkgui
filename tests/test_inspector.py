"""Comprehensive tests for the type-to-widget inspector."""

import pytest

from mkgui.inspector import (
    ConversionError,
    ConversionResult,
    TypeCategory,
    TypeInfo,
    _convert_bool,
    _convert_by_category,
    _convert_decimal,
    _convert_float,
    _convert_int,
    _convert_json,
    _convert_list,
    _get_default_validation,
    _is_empty_value,
    _looks_like_enum,
    _parse_literal_values,
    convert_value,
    inspect_parameter,
    inspect_parameters,
    parse_type_annotation,
)
from mkgui.models import Annotation, ParamKind, ParamSpec, ParamUI, ParamValidation, WidgetType


class TestParseBasicTypes:
    """Test parsing of basic type annotations."""

    def test_int(self):
        info = parse_type_annotation("int")
        assert info.category == TypeCategory.INTEGER
        assert info.widget == WidgetType.SPIN_BOX
        assert not info.is_optional

    def test_float(self):
        info = parse_type_annotation("float")
        assert info.category == TypeCategory.FLOAT
        assert info.widget == WidgetType.DOUBLE_SPIN_BOX

    def test_bool(self):
        info = parse_type_annotation("bool")
        assert info.category == TypeCategory.BOOLEAN
        assert info.widget == WidgetType.CHECK_BOX

    def test_str(self):
        info = parse_type_annotation("str")
        assert info.category == TypeCategory.STRING
        assert info.widget == WidgetType.LINE_EDIT

    def test_path(self):
        info = parse_type_annotation("Path")
        assert info.category == TypeCategory.PATH
        assert info.widget == WidgetType.FILE_PICKER

    def test_pathlib_path(self):
        info = parse_type_annotation("pathlib.Path")
        assert info.category == TypeCategory.PATH
        assert info.widget == WidgetType.FILE_PICKER

    def test_any(self):
        info = parse_type_annotation("Any")
        assert info.category == TypeCategory.ANY
        assert info.widget == WidgetType.JSON_EDITOR

    def test_none_annotation(self):
        info = parse_type_annotation(None)
        assert info.category == TypeCategory.UNKNOWN
        assert info.widget == WidgetType.LINE_EDIT

    def test_empty_annotation(self):
        info = parse_type_annotation("")
        assert info.category == TypeCategory.UNKNOWN
        assert info.widget == WidgetType.LINE_EDIT


class TestParseDateTimeTypes:
    """Test parsing of date/time type annotations."""

    def test_date(self):
        info = parse_type_annotation("date")
        assert info.category == TypeCategory.DATE
        assert info.widget == WidgetType.DATE_EDIT

    def test_datetime_date(self):
        info = parse_type_annotation("datetime.date")
        assert info.category == TypeCategory.DATE
        assert info.widget == WidgetType.DATE_EDIT

    def test_datetime(self):
        info = parse_type_annotation("datetime")
        assert info.category == TypeCategory.DATETIME
        assert info.widget == WidgetType.DATETIME_EDIT

    def test_time(self):
        info = parse_type_annotation("time")
        assert info.category == TypeCategory.TIME
        assert info.widget == WidgetType.TIME_EDIT

    def test_decimal(self):
        info = parse_type_annotation("Decimal")
        assert info.category == TypeCategory.DECIMAL
        assert info.widget == WidgetType.LINE_EDIT


class TestParseOptionalTypes:
    """Test parsing of Optional type annotations."""

    def test_optional_int(self):
        info = parse_type_annotation("Optional[int]")
        assert info.category == TypeCategory.INTEGER
        assert info.is_optional is True
        assert info.widget == WidgetType.SPIN_BOX

    def test_optional_str(self):
        info = parse_type_annotation("Optional[str]")
        assert info.category == TypeCategory.STRING
        assert info.is_optional is True
        assert info.widget == WidgetType.LINE_EDIT

    def test_union_none_first(self):
        info = parse_type_annotation("Union[None, str]")
        assert info.category == TypeCategory.STRING
        assert info.is_optional is True

    def test_union_none_second(self):
        info = parse_type_annotation("Union[str, None]")
        assert info.category == TypeCategory.STRING
        assert info.is_optional is True

    def test_pipe_none(self):
        info = parse_type_annotation("str | None")
        assert info.category == TypeCategory.STRING
        assert info.is_optional is True

    def test_none_pipe(self):
        info = parse_type_annotation("None | int")
        assert info.category == TypeCategory.INTEGER
        assert info.is_optional is True


class TestParseLiteralTypes:
    """Test parsing of Literal type annotations."""

    def test_literal_strings(self):
        info = parse_type_annotation('Literal["a", "b", "c"]')
        assert info.category == TypeCategory.LITERAL
        assert info.widget == WidgetType.COMBO_BOX
        assert info.options == ["a", "b", "c"]

    def test_literal_single_quotes(self):
        info = parse_type_annotation("Literal['x', 'y']")
        assert info.options == ["x", "y"]

    def test_literal_mixed(self):
        info = parse_type_annotation('Literal["on", "off", 1, 2]')
        assert info.options == ["on", "off", "1", "2"]

    def test_literal_single_value(self):
        info = parse_type_annotation('Literal["only"]')
        assert info.options == ["only"]


class TestParseContainerTypes:
    """Test parsing of container type annotations."""

    def test_list_str(self):
        info = parse_type_annotation("list[str]")
        assert info.category == TypeCategory.LIST
        assert info.widget == WidgetType.PLAIN_TEXT_EDIT
        assert info.inner_type is not None
        assert info.inner_type.category == TypeCategory.STRING

    def test_list_int(self):
        info = parse_type_annotation("List[int]")
        assert info.category == TypeCategory.LIST
        assert info.inner_type.category == TypeCategory.INTEGER

    def test_tuple(self):
        info = parse_type_annotation("Tuple[str, int]")
        assert info.category == TypeCategory.LIST
        assert info.widget == WidgetType.PLAIN_TEXT_EDIT

    def test_dict(self):
        info = parse_type_annotation("dict")
        assert info.category == TypeCategory.DICT
        assert info.widget == WidgetType.JSON_EDITOR

    def test_dict_typed(self):
        info = parse_type_annotation("Dict[str, int]")
        assert info.category == TypeCategory.DICT
        assert info.widget == WidgetType.JSON_EDITOR

    def test_list_bare(self):
        info = parse_type_annotation("list")
        assert info.category == TypeCategory.LIST
        assert info.widget == WidgetType.PLAIN_TEXT_EDIT

    def test_tuple_bare(self):
        info = parse_type_annotation("tuple")
        assert info.category == TypeCategory.LIST
        assert info.widget == WidgetType.PLAIN_TEXT_EDIT

    def test_set(self):
        info = parse_type_annotation("set[str]")
        assert info.category == TypeCategory.LIST
        assert info.widget == WidgetType.PLAIN_TEXT_EDIT


class TestParseEnumTypes:
    """Test heuristic enum detection."""

    def test_pascal_case_detected_as_enum(self):
        info = parse_type_annotation("Status")
        assert info.category == TypeCategory.ENUM
        # Uses LineEdit since we don't have enum values without runtime introspection
        assert info.widget == WidgetType.LINE_EDIT

    def test_module_prefixed_enum(self):
        info = parse_type_annotation("models.Priority")
        assert info.category == TypeCategory.ENUM
        assert info.widget == WidgetType.LINE_EDIT

    def test_known_types_not_detected_as_enum(self):
        # These should NOT be detected as enums
        assert parse_type_annotation("Path").category == TypeCategory.PATH
        assert parse_type_annotation("Decimal").category == TypeCategory.DECIMAL
        assert parse_type_annotation("Any").category == TypeCategory.ANY


class TestParseAnnotatedTypes:
    """Test parsing of Annotated type annotations."""

    def test_annotated_extracts_base_type(self):
        info = parse_type_annotation("Annotated[int, SomeMetadata]")
        assert info.category == TypeCategory.INTEGER
        assert info.widget == WidgetType.SPIN_BOX

    def test_annotated_optional(self):
        info = parse_type_annotation("Annotated[Optional[str], Description]")
        assert info.category == TypeCategory.STRING
        assert info.is_optional is True

    def test_annotated_widget_override(self):
        info = parse_type_annotation("Annotated[str, {'widget': 'plain_text_edit'}]")
        assert info.widget == WidgetType.PLAIN_TEXT_EDIT

    def test_annotated_validation_override(self):
        info = parse_type_annotation("Annotated[int, {'min': 0, 'max': 10}]")
        assert info.validation.min == 0
        assert info.validation.max == 10

    def test_annotated_options_override(self):
        info = parse_type_annotation("Annotated[str, {'options': ['a', 'b']}]")
        assert info.widget == WidgetType.COMBO_BOX
        assert info.options == ["a", "b"]

    def test_annotated_string_metadata(self):
        info = parse_type_annotation("Annotated[float, 'min=1.5', 'max=9.5']")
        assert info.validation.min == 1.5
        assert info.validation.max == 9.5


class TestConvertValues:
    """Test value conversion from UI strings to Python types."""

    def test_convert_int(self):
        type_info = parse_type_annotation("int")
        result = convert_value("42", type_info)
        assert result.success is True
        assert result.value == 42

    def test_convert_int_hex(self):
        type_info = parse_type_annotation("int")
        result = convert_value("0xff", type_info)
        assert result.success is True
        assert result.value == 255

    def test_convert_int_invalid(self):
        type_info = parse_type_annotation("int")
        result = convert_value("not_a_number", type_info)
        assert result.success is False
        assert result.error is not None

    def test_convert_float(self):
        type_info = parse_type_annotation("float")
        result = convert_value("3.14", type_info)
        assert result.success is True
        assert result.value == 3.14

    def test_convert_bool_true(self):
        type_info = parse_type_annotation("bool")
        for val in ["true", "True", "1", "yes", "on"]:
            result = convert_value(val, type_info)
            assert result.success is True
            assert result.value is True

    def test_convert_bool_false(self):
        type_info = parse_type_annotation("bool")
        for val in ["false", "False", "0", "no", "off"]:
            result = convert_value(val, type_info)
            assert result.success is True
            assert result.value is False

    def test_convert_bool_invalid(self):
        type_info = parse_type_annotation("bool")
        result = convert_value("maybe", type_info)
        assert result.success is False

    def test_convert_str(self):
        type_info = parse_type_annotation("str")
        result = convert_value("hello world", type_info)
        assert result.success is True
        assert result.value == "hello world"

    def test_convert_list(self):
        type_info = parse_type_annotation("list[str]")
        result = convert_value("a\nb\nc", type_info)
        assert result.success is True
        assert result.value == ["a", "b", "c"]

    def test_convert_list_int(self):
        type_info = parse_type_annotation("list[int]")
        result = convert_value("1\n2\n3", type_info)
        assert result.success is True
        assert result.value == [1, 2, 3]

    def test_convert_dict_json(self):
        type_info = parse_type_annotation("dict")
        result = convert_value('{"key": "value"}', type_info)
        assert result.success is True
        assert result.value == {"key": "value"}

    def test_convert_optional_empty(self):
        type_info = parse_type_annotation("Optional[int]")
        result = convert_value("", type_info)
        assert result.success is True
        assert result.value is None

    def test_convert_optional_with_value(self):
        type_info = parse_type_annotation("Optional[int]")
        result = convert_value("42", type_info)
        assert result.success is True
        assert result.value == 42

    def test_convert_required_empty_fails(self):
        type_info = parse_type_annotation("int")
        result = convert_value("", type_info)
        assert result.success is False
        assert result.error.message == "Value is required"


class TestDefaultValidation:
    """Test default validation rules."""

    def test_int_has_range(self):
        info = parse_type_annotation("int")
        assert info.validation.min == -999999
        assert info.validation.max == 999999

    def test_float_has_range(self):
        info = parse_type_annotation("float")
        assert info.validation.min == -999999.0
        assert info.validation.max == 999999.0

    def test_str_no_validation(self):
        info = parse_type_annotation("str")
        assert info.validation.min is None
        assert info.validation.max is None


class TestTypingPrefixedAnnotations:
    """Test parsing of typing.* prefixed type annotations."""

    def test_typing_optional(self):
        info = parse_type_annotation("typing.Optional[int]")
        assert info.category == TypeCategory.INTEGER
        assert info.is_optional is True

    def test_typing_list(self):
        info = parse_type_annotation("typing.List[str]")
        assert info.category == TypeCategory.LIST
        assert info.inner_type.category == TypeCategory.STRING

    def test_typing_dict(self):
        info = parse_type_annotation("typing.Dict[str, int]")
        assert info.category == TypeCategory.DICT
        assert info.widget == WidgetType.JSON_EDITOR

    def test_typing_union_none(self):
        info = parse_type_annotation("typing.Union[str, None]")
        assert info.category == TypeCategory.STRING
        assert info.is_optional is True

    def test_typing_literal(self):
        info = parse_type_annotation('typing.Literal["a", "b"]')
        assert info.category == TypeCategory.LITERAL
        assert info.options == ["a", "b"]

    def test_typing_annotated(self):
        info = parse_type_annotation("typing.Annotated[int, Meta]")
        assert info.category == TypeCategory.INTEGER

    def test_typing_tuple(self):
        info = parse_type_annotation("typing.Tuple[str, int]")
        assert info.category == TypeCategory.LIST


class TestNonStringUIValues:
    """Test conversion of non-string UI widget values."""

    def test_bool_value_false(self):
        """False from checkbox should not be treated as empty."""
        type_info = parse_type_annotation("bool")
        result = convert_value(False, type_info)
        assert result.success is True
        assert result.value is False

    def test_bool_value_true(self):
        """True from checkbox should work."""
        type_info = parse_type_annotation("bool")
        result = convert_value(True, type_info)
        assert result.success is True
        assert result.value is True

    def test_int_value_zero(self):
        """0 from spinbox should not be treated as empty."""
        type_info = parse_type_annotation("int")
        result = convert_value(0, type_info)
        assert result.success is True
        assert result.value == 0

    def test_int_value_negative(self):
        """Negative int from spinbox should work."""
        type_info = parse_type_annotation("int")
        result = convert_value(-42, type_info)
        assert result.success is True
        assert result.value == -42

    def test_float_value_zero(self):
        """0.0 from double spinbox should not be treated as empty."""
        type_info = parse_type_annotation("float")
        result = convert_value(0.0, type_info)
        assert result.success is True
        assert result.value == 0.0

    def test_float_from_int(self):
        """Int value for float type should be converted."""
        type_info = parse_type_annotation("float")
        result = convert_value(42, type_info)
        assert result.success is True
        assert result.value == 42.0
        assert isinstance(result.value, float)

    def test_none_for_optional(self):
        """None should be accepted for optional types."""
        type_info = parse_type_annotation("Optional[int]")
        result = convert_value(None, type_info)
        assert result.success is True
        assert result.value is None

    def test_none_for_required_fails(self):
        """None should fail for required types."""
        type_info = parse_type_annotation("int")
        result = convert_value(None, type_info)
        assert result.success is False
        assert result.error.message == "Value is required"


class TestIsEmptyValue:
    """Test the _is_empty_value helper function."""

    def test_none_is_empty(self):
        """None should be considered empty."""
        assert _is_empty_value(None) is True

    def test_empty_string_is_empty(self):
        """Empty string should be considered empty."""
        assert _is_empty_value("") is True

    def test_false_is_not_empty(self):
        """False should NOT be considered empty."""
        assert _is_empty_value(False) is False

    def test_zero_is_not_empty(self):
        """0 should NOT be considered empty."""
        assert _is_empty_value(0) is False

    def test_zero_float_is_not_empty(self):
        """0.0 should NOT be considered empty."""
        assert _is_empty_value(0.0) is False

    def test_empty_list_is_not_empty(self):
        """Empty list should NOT be considered empty (different from None/"")."""
        assert _is_empty_value([]) is False

    def test_whitespace_string_is_not_empty(self):
        """Whitespace string should NOT be considered empty."""
        assert _is_empty_value("   ") is False


class TestLooksLikeEnum:
    """Test the _looks_like_enum heuristic function."""

    def test_pascal_case_is_enum(self):
        """PascalCase names should be detected as enum."""
        assert _looks_like_enum("Status") is True
        assert _looks_like_enum("Priority") is True
        assert _looks_like_enum("MyEnum") is True

    def test_lowercase_is_not_enum(self):
        """Lowercase names should not be detected as enum."""
        assert _looks_like_enum("status") is False
        assert _looks_like_enum("my_type") is False

    def test_known_types_not_enum(self):
        """Known non-enum types should not be detected."""
        assert _looks_like_enum("Path") is False
        assert _looks_like_enum("Decimal") is False
        assert _looks_like_enum("Any") is False
        assert _looks_like_enum("Optional") is False
        assert _looks_like_enum("Union") is False
        assert _looks_like_enum("List") is False
        assert _looks_like_enum("Dict") is False

    def test_module_prefixed_enum(self):
        """Module.Name should check the name part."""
        assert _looks_like_enum("models.Status") is True
        assert _looks_like_enum("myapp.types.Priority") is True

    def test_empty_string(self):
        """Empty string should not be enum."""
        assert _looks_like_enum("") is False

    def test_none_string(self):
        """None should not crash."""
        assert _looks_like_enum(None) is False


class TestParseLiteralValues:
    """Test the _parse_literal_values helper function."""

    def test_double_quoted_strings(self):
        """Double quoted strings should be parsed."""
        result = _parse_literal_values('"a", "b", "c"')
        assert result == ["a", "b", "c"]

    def test_single_quoted_strings(self):
        """Single quoted strings should be parsed."""
        result = _parse_literal_values("'x', 'y', 'z'")
        assert result == ["x", "y", "z"]

    def test_mixed_types(self):
        """Mixed string and non-string values should be parsed."""
        result = _parse_literal_values('"on", "off", 1, 2, True')
        assert result == ["on", "off", "1", "2", "True"]

    def test_single_value(self):
        """Single value should work."""
        result = _parse_literal_values('"only"')
        assert result == ["only"]

    def test_value_with_comma_in_string(self):
        """Comma inside quoted string should not split."""
        result = _parse_literal_values('"a,b", "c"')
        assert result == ["a,b", "c"]

    def test_empty_input(self):
        """Empty input should return empty list."""
        result = _parse_literal_values("")
        assert result == []

    def test_whitespace_handling(self):
        """Whitespace around values should be trimmed."""
        result = _parse_literal_values('  "a"  ,  "b"  ')
        assert result == ["a", "b"]


class TestGetDefaultValidation:
    """Test the _get_default_validation function."""

    def test_integer_validation(self):
        """Integer should have range validation."""
        val = _get_default_validation(TypeCategory.INTEGER)
        assert val.min == -999999
        assert val.max == 999999

    def test_float_validation(self):
        """Float should have range validation."""
        val = _get_default_validation(TypeCategory.FLOAT)
        assert val.min == -999999.0
        assert val.max == 999999.0

    def test_string_no_validation(self):
        """String should have no validation."""
        val = _get_default_validation(TypeCategory.STRING)
        assert val.min is None
        assert val.max is None
        assert val.regex is None

    def test_boolean_no_validation(self):
        """Boolean should have no validation."""
        val = _get_default_validation(TypeCategory.BOOLEAN)
        assert val.min is None


class TestConvertIntFunction:
    """Test the _convert_int helper function."""

    def test_decimal_integer(self):
        """Regular decimal integers should convert."""
        assert _convert_int("42") == 42
        assert _convert_int("-17") == -17
        assert _convert_int("0") == 0

    def test_hex_integer(self):
        """Hex integers should convert."""
        assert _convert_int("0xff") == 255
        assert _convert_int("0xFF") == 255
        assert _convert_int("0x10") == 16

    def test_octal_integer(self):
        """Octal integers should convert."""
        assert _convert_int("0o10") == 8
        assert _convert_int("0O77") == 63

    def test_binary_integer(self):
        """Binary integers should convert."""
        assert _convert_int("0b1010") == 10
        assert _convert_int("0B1111") == 15

    def test_whitespace_stripped(self):
        """Whitespace should be stripped."""
        assert _convert_int("  42  ") == 42

    def test_invalid_raises(self):
        """Invalid input should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid integer"):
            _convert_int("not_a_number")


class TestConvertFloatFunction:
    """Test the _convert_float helper function."""

    def test_simple_float(self):
        """Simple floats should convert."""
        assert _convert_float("3.14") == 3.14
        assert _convert_float("-2.5") == -2.5

    def test_scientific_notation(self):
        """Scientific notation should work."""
        assert _convert_float("1e10") == 1e10
        assert _convert_float("2.5e-3") == 2.5e-3

    def test_integer_string(self):
        """Integer strings should convert to float."""
        assert _convert_float("42") == 42.0

    def test_whitespace_stripped(self):
        """Whitespace should be stripped."""
        assert _convert_float("  3.14  ") == 3.14

    def test_invalid_raises(self):
        """Invalid input should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid number"):
            _convert_float("not_a_number")


class TestConvertBoolFunction:
    """Test the _convert_bool helper function."""

    def test_true_values(self):
        """Various true values should work."""
        for val in ["true", "True", "TRUE", "1", "yes", "YES", "on", "ON"]:
            assert _convert_bool(val) is True

    def test_false_values(self):
        """Various false values should work."""
        for val in ["false", "False", "FALSE", "0", "no", "NO", "off", "OFF"]:
            assert _convert_bool(val) is False

    def test_whitespace_stripped(self):
        """Whitespace should be stripped."""
        assert _convert_bool("  true  ") is True
        assert _convert_bool("  false  ") is False

    def test_invalid_raises(self):
        """Invalid input should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid boolean"):
            _convert_bool("maybe")
        with pytest.raises(ValueError, match="Invalid boolean"):
            _convert_bool("2")


class TestConvertDecimalFunction:
    """Test the _convert_decimal helper function."""

    def test_valid_decimal(self):
        """Valid decimal strings should pass through."""
        assert _convert_decimal("123.456") == "123.456"
        assert _convert_decimal("-99.99") == "-99.99"
        assert _convert_decimal("0") == "0"

    def test_whitespace_stripped(self):
        """Whitespace should be stripped."""
        assert _convert_decimal("  123.45  ") == "123.45"

    def test_invalid_raises(self):
        """Invalid input should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid decimal"):
            _convert_decimal("not_a_decimal")


class TestConvertJsonFunction:
    """Test the _convert_json helper function."""

    def test_valid_json_object(self):
        """Valid JSON objects should parse."""
        result = _convert_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_valid_json_array(self):
        """Valid JSON arrays should parse."""
        result = _convert_json('[1, 2, 3]')
        assert result == [1, 2, 3]

    def test_json_primitives(self):
        """JSON primitives should parse."""
        assert _convert_json("123") == 123
        assert _convert_json('"hello"') == "hello"
        assert _convert_json("true") is True
        assert _convert_json("null") is None

    def test_invalid_json_raises(self):
        """Invalid JSON should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid JSON"):
            _convert_json("{invalid}")


class TestConvertListFunction:
    """Test the _convert_list helper function."""

    def test_newline_separated(self):
        """Newline-separated values should be split."""
        result = _convert_list("a\nb\nc", None)
        assert result == ["a", "b", "c"]

    def test_empty_lines_skipped(self):
        """Empty lines should be skipped."""
        result = _convert_list("a\n\nb\n\nc", None)
        assert result == ["a", "b", "c"]

    def test_whitespace_trimmed(self):
        """Whitespace should be trimmed from each line."""
        result = _convert_list("  a  \n  b  ", None)
        assert result == ["a", "b"]

    def test_with_inner_type(self):
        """Inner type conversion should be applied."""
        inner = parse_type_annotation("int")
        result = _convert_list("1\n2\n3", inner)
        assert result == [1, 2, 3]

    def test_empty_input(self):
        """Empty input should return empty list."""
        result = _convert_list("", None)
        assert result == []


class TestConvertByCategoryFunction:
    """Test the _convert_by_category function."""

    def test_string_passthrough(self):
        """String type should pass through unchanged."""
        type_info = parse_type_annotation("str")
        result = _convert_by_category("hello", type_info)
        assert result == "hello"

    def test_path_passthrough(self):
        """Path type should pass through as string."""
        type_info = parse_type_annotation("Path")
        result = _convert_by_category("/path/to/file", type_info)
        assert result == "/path/to/file"

    def test_enum_passthrough(self):
        """Enum type should pass through unchanged."""
        type_info = parse_type_annotation("Status")
        result = _convert_by_category("active", type_info)
        assert result == "active"

    def test_literal_passthrough(self):
        """Literal type should pass through unchanged."""
        type_info = parse_type_annotation('Literal["a", "b"]')
        result = _convert_by_category("a", type_info)
        assert result == "a"

    def test_date_passthrough(self):
        """Date type should pass through as string."""
        type_info = parse_type_annotation("date")
        result = _convert_by_category("2025-01-19", type_info)
        assert result == "2025-01-19"

    def test_datetime_passthrough(self):
        """Datetime type should pass through as string."""
        type_info = parse_type_annotation("datetime")
        result = _convert_by_category("2025-01-19T12:00:00", type_info)
        assert result == "2025-01-19T12:00:00"

    def test_time_passthrough(self):
        """Time type should pass through as string."""
        type_info = parse_type_annotation("time")
        result = _convert_by_category("12:30:00", type_info)
        assert result == "12:30:00"

    def test_any_tries_json(self):
        """ANY type should try JSON first."""
        type_info = parse_type_annotation("Any")
        result = _convert_by_category('{"key": "value"}', type_info)
        assert result == {"key": "value"}

    def test_any_falls_back_to_string(self):
        """ANY type should fall back to string if not JSON."""
        type_info = parse_type_annotation("Any")
        result = _convert_by_category("plain text", type_info)
        assert result == "plain text"

    def test_unknown_tries_json(self):
        """UNKNOWN type should try JSON first."""
        type_info = parse_type_annotation("SomeUnknown")
        # Unknown types that look like enum get LINE_EDIT but still go through
        # Let's use a truly unknown type
        type_info = TypeInfo(
            category=TypeCategory.UNKNOWN,
            raw="something",
            widget=WidgetType.LINE_EDIT
        )
        result = _convert_by_category('[1, 2, 3]', type_info)
        assert result == [1, 2, 3]


class TestInspectParameter:
    """Test the inspect_parameter function."""

    def test_updates_ui_widget(self):
        """Should update parameter UI based on annotation."""
        param = ParamSpec(name="count", annotation=Annotation(raw="int"))
        result = inspect_parameter(param)

        assert result.ui.widget == WidgetType.SPIN_BOX
        assert result.validation.min == -999999
        assert result.validation.max == 999999

    def test_updates_combo_options(self):
        """Should set combo box options for Literal types."""
        param = ParamSpec(name="mode", annotation=Annotation(raw='Literal["fast", "slow"]'))
        result = inspect_parameter(param)

        assert result.ui.widget == WidgetType.COMBO_BOX
        assert result.ui.options == ["fast", "slow"]

    def test_no_annotation(self):
        """Should handle parameter without annotation."""
        param = ParamSpec(name="x", annotation=Annotation())
        result = inspect_parameter(param)

        assert result.ui.widget == WidgetType.LINE_EDIT

    def test_optional_allows_empty(self):
        """Optional types should allow empty input."""
        param = ParamSpec(name="x", required=True, annotation=Annotation(raw="Optional[int]"))
        result = inspect_parameter(param)

        assert result.required is False

    def test_varargs_widget(self):
        """*args should use multiline input."""
        param = ParamSpec(
            name="items",
            kind=ParamKind.VAR_POSITIONAL,
            annotation=Annotation(raw="int"),
        )
        result = inspect_parameter(param)

        assert result.ui.widget == WidgetType.PLAIN_TEXT_EDIT

    def test_kwargs_widget(self):
        """**kwargs should use JSON editor."""
        param = ParamSpec(
            name="options",
            kind=ParamKind.VAR_KEYWORD,
            annotation=Annotation(raw="str"),
        )
        result = inspect_parameter(param)

        assert result.ui.widget == WidgetType.JSON_EDITOR


class TestInspectParameters:
    """Test the inspect_parameters function."""

    def test_inspects_all_parameters(self):
        """Should inspect all parameters in list."""
        params = [
            ParamSpec(name="count", annotation=Annotation(raw="int")),
            ParamSpec(name="name", annotation=Annotation(raw="str")),
            ParamSpec(name="enabled", annotation=Annotation(raw="bool")),
        ]
        results = inspect_parameters(params)

        assert len(results) == 3
        assert results[0].ui.widget == WidgetType.SPIN_BOX
        assert results[1].ui.widget == WidgetType.LINE_EDIT
        assert results[2].ui.widget == WidgetType.CHECK_BOX

    def test_empty_list(self):
        """Should handle empty list."""
        results = inspect_parameters([])
        assert results == []


class TestConversionErrorDataclass:
    """Test the ConversionError dataclass."""

    def test_creation(self):
        """Should create ConversionError correctly."""
        error = ConversionError(
            message="Invalid value",
            field="count",
            value="abc"
        )
        assert error.message == "Invalid value"
        assert error.field == "count"
        assert error.value == "abc"


class TestConversionResultDataclass:
    """Test the ConversionResult dataclass."""

    def test_success_result(self):
        """Should create successful result."""
        result = ConversionResult(success=True, value=42)
        assert result.success is True
        assert result.value == 42
        assert result.error is None

    def test_failure_result(self):
        """Should create failure result."""
        error = ConversionError(message="Invalid", field="x", value="bad")
        result = ConversionResult(success=False, error=error)
        assert result.success is False
        assert result.value is None
        assert result.error.message == "Invalid"


class TestTypeInfoDataclass:
    """Test the TypeInfo dataclass."""

    def test_default_values(self):
        """Should have correct defaults."""
        info = TypeInfo(
            category=TypeCategory.STRING,
            raw="str"
        )
        assert info.inner_type is None
        assert info.options == []
        assert info.is_optional is False
        assert info.widget == WidgetType.LINE_EDIT
        assert info.validation.min is None


class TestTypeCategoryEnum:
    """Test the TypeCategory enum."""

    def test_all_categories_exist(self):
        """Should have all expected categories."""
        expected = {
            "integer", "float", "boolean", "string", "path",
            "enum", "literal", "optional", "list", "dict",
            "date", "datetime", "time", "decimal", "any", "unknown"
        }
        actual = {cat.value for cat in TypeCategory}
        assert actual == expected

    def test_string_behavior(self):
        """Should behave as string."""
        assert TypeCategory.INTEGER == "integer"
        assert "Type: " + TypeCategory.STRING == "Type: string"


class TestDateTimeConversion:
    """Test date/time value conversion expectations."""

    def test_date_iso_string_passthrough(self):
        """ISO date strings should pass through unchanged."""
        type_info = parse_type_annotation("date")
        result = convert_value("2025-01-19", type_info)
        assert result.success is True
        assert result.value == "2025-01-19"

    def test_datetime_iso_string_passthrough(self):
        """ISO datetime strings should pass through unchanged."""
        type_info = parse_type_annotation("datetime")
        result = convert_value("2025-01-19T14:30:00", type_info)
        assert result.success is True
        assert result.value == "2025-01-19T14:30:00"

    def test_time_iso_string_passthrough(self):
        """ISO time strings should pass through unchanged."""
        type_info = parse_type_annotation("time")
        result = convert_value("14:30:00", type_info)
        assert result.success is True
        assert result.value == "14:30:00"

    def test_date_empty_optional(self):
        """Optional date with empty value should return None."""
        type_info = parse_type_annotation("Optional[date]")
        result = convert_value("", type_info)
        assert result.success is True
        assert result.value is None

    def test_date_required_empty_fails(self):
        """Required date with empty value should fail."""
        type_info = parse_type_annotation("date")
        result = convert_value("", type_info)
        assert result.success is False

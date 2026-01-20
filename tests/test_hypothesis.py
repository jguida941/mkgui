"""Property-based tests using Hypothesis for pyqt6_gen."""

import json
from pathlib import Path

import pytest
from hypothesis import given, settings, assume, example
from hypothesis import strategies as st

from pyqt6_gen.inspector import (
    TypeCategory,
    TypeInfo,
    _convert_bool,
    _convert_float,
    _convert_int,
    _convert_json,
    _convert_list,
    _is_empty_value,
    _looks_like_enum,
    convert_value,
    parse_type_annotation,
)
from pyqt6_gen.models import (
    ActionKind,
    ActionSpec,
    AnalysisMode,
    AnalysisResult,
    Annotation,
    DefaultValue,
    ModuleSpec,
    ParamSpec,
    WidgetType,
    _to_dict,
)


class TestIntegerConversionProperties:
    """Property-based tests for integer conversion."""

    @given(st.integers(min_value=-999999, max_value=999999))
    def test_int_roundtrip(self, value):
        """Converting int to string and back should preserve value."""
        result = _convert_int(str(value))
        assert result == value

    @given(st.integers(min_value=0, max_value=0xFFFFFF))
    def test_hex_roundtrip(self, value):
        """Hex conversion should preserve value."""
        hex_str = hex(value)
        result = _convert_int(hex_str)
        assert result == value

    @given(st.integers(min_value=0, max_value=0o777777))
    def test_octal_roundtrip(self, value):
        """Octal conversion should preserve value."""
        octal_str = oct(value)
        result = _convert_int(octal_str)
        assert result == value

    @given(st.integers(min_value=0, max_value=0b111111111111))
    def test_binary_roundtrip(self, value):
        """Binary conversion should preserve value."""
        binary_str = bin(value)
        result = _convert_int(binary_str)
        assert result == value

    @given(st.integers())
    def test_convert_value_int_roundtrip(self, value):
        """convert_value for int type should preserve value."""
        type_info = parse_type_annotation("int")
        result = convert_value(str(value), type_info)
        assert result.success is True
        assert result.value == value


class TestFloatConversionProperties:
    """Property-based tests for float conversion."""

    @given(st.floats(allow_nan=False, allow_infinity=False))
    def test_float_roundtrip(self, value):
        """Converting float to string and back should preserve value (approximately)."""
        result = _convert_float(str(value))
        assert abs(result - value) < 1e-10 or result == value

    @given(st.floats(allow_nan=False, allow_infinity=False, min_value=-1e10, max_value=1e10))
    def test_convert_value_float_roundtrip(self, value):
        """convert_value for float type should preserve value."""
        type_info = parse_type_annotation("float")
        result = convert_value(str(value), type_info)
        assert result.success is True
        assert abs(result.value - value) < 1e-10 or result.value == value


class TestBooleanConversionProperties:
    """Property-based tests for boolean conversion."""

    @given(st.booleans())
    def test_bool_direct_passthrough(self, value):
        """Boolean values should pass through unchanged."""
        type_info = parse_type_annotation("bool")
        result = convert_value(value, type_info)
        assert result.success is True
        assert result.value is value

    @given(st.sampled_from(["true", "false", "1", "0", "yes", "no", "on", "off"]))
    def test_bool_string_conversion(self, value):
        """Valid boolean strings should convert successfully."""
        result = _convert_bool(value)
        assert isinstance(result, bool)


class TestStringConversionProperties:
    """Property-based tests for string handling."""

    @given(st.text())
    def test_string_passthrough(self, value):
        """String type should pass through any text."""
        type_info = parse_type_annotation("str")
        result = convert_value(value, type_info)
        if value == "" or value is None:
            # Empty string fails for required types
            pass
        else:
            assert result.success is True
            assert result.value == value


class TestOptionalTypeProperties:
    """Property-based tests for Optional type handling."""

    @given(st.one_of(st.none(), st.text(min_size=0, max_size=0)))
    def test_optional_accepts_empty(self, value):
        """Optional types should accept None and empty string."""
        type_info = parse_type_annotation("Optional[str]")
        result = convert_value(value, type_info)
        assert result.success is True
        assert result.value is None

    @given(st.integers())
    def test_optional_int_with_value(self, value):
        """Optional[int] should accept integer values."""
        type_info = parse_type_annotation("Optional[int]")
        result = convert_value(str(value), type_info)
        assert result.success is True
        assert result.value == value


class TestListConversionProperties:
    """Property-based tests for list conversion."""

    @given(st.lists(st.text(min_size=1, max_size=50).filter(lambda x: "\n" not in x)))
    @settings(max_examples=50)
    def test_list_roundtrip(self, values):
        """List items should be preserved through conversion."""
        assume(all(v.strip() for v in values))  # Non-empty after strip
        input_str = "\n".join(values)
        result = _convert_list(input_str, None)
        assert result == [v.strip() for v in values]

    @given(st.lists(st.integers(), min_size=1, max_size=10))
    def test_list_int_roundtrip(self, values):
        """List of integers should convert correctly."""
        inner_type = parse_type_annotation("int")
        input_str = "\n".join(str(v) for v in values)
        result = _convert_list(input_str, inner_type)
        assert result == values


class TestJsonConversionProperties:
    """Property-based tests for JSON conversion."""

    @given(st.dictionaries(
        keys=st.text(min_size=1, max_size=20).filter(lambda x: x.strip()),
        values=st.one_of(
            st.integers(),
            st.floats(allow_nan=False, allow_infinity=False),
            st.text(max_size=50),
            st.booleans(),
            st.none()
        ),
        max_size=5
    ))
    @settings(max_examples=30)
    def test_dict_json_roundtrip(self, value):
        """Dictionary should survive JSON roundtrip."""
        json_str = json.dumps(value)
        result = _convert_json(json_str)
        assert result == value

    @given(st.lists(
        st.one_of(st.integers(), st.text(max_size=20)),
        max_size=10
    ))
    def test_list_json_roundtrip(self, value):
        """List should survive JSON roundtrip."""
        json_str = json.dumps(value)
        result = _convert_json(json_str)
        assert result == value


class TestIsEmptyValueProperties:
    """Property-based tests for _is_empty_value."""

    @given(st.integers())
    def test_integers_not_empty(self, value):
        """Integers (including 0) should not be empty."""
        assert _is_empty_value(value) is False

    @given(st.floats(allow_nan=False))
    def test_floats_not_empty(self, value):
        """Floats (including 0.0) should not be empty."""
        assert _is_empty_value(value) is False

    @given(st.booleans())
    def test_booleans_not_empty(self, value):
        """Booleans (including False) should not be empty."""
        assert _is_empty_value(value) is False

    @given(st.text(min_size=1))
    def test_non_empty_strings_not_empty(self, value):
        """Non-empty strings should not be empty."""
        assert _is_empty_value(value) is False


class TestLooksLikeEnumProperties:
    """Property-based tests for _looks_like_enum heuristic."""

    @given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=20))
    def test_lowercase_not_enum(self, value):
        """Lowercase names should not be detected as enum."""
        assert _looks_like_enum(value) is False

    @given(st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=2, max_size=20))
    def test_all_uppercase_is_enum(self, value):
        """All uppercase (starting with upper) could be enum if not known type."""
        # Just verify it doesn't crash
        result = _looks_like_enum(value)
        assert isinstance(result, bool)


class TestTypeAnnotationParsingProperties:
    """Property-based tests for type annotation parsing."""

    @given(st.sampled_from(["int", "float", "bool", "str", "Path"]))
    def test_basic_types_parse(self, type_name):
        """Basic type names should parse without error."""
        info = parse_type_annotation(type_name)
        assert info.raw == type_name
        assert info.category != TypeCategory.UNKNOWN or type_name not in ["int", "float", "bool", "str"]

    @given(st.sampled_from(["int", "str", "float", "bool"]))
    def test_optional_types_parse(self, inner_type):
        """Optional[T] should parse correctly."""
        info = parse_type_annotation(f"Optional[{inner_type}]")
        assert info.is_optional is True

    @given(st.sampled_from(["int", "str", "float"]))
    def test_list_types_parse(self, inner_type):
        """list[T] should parse correctly."""
        info = parse_type_annotation(f"list[{inner_type}]")
        assert info.category == TypeCategory.LIST
        assert info.inner_type is not None


class TestDataclassToDictProperties:
    """Property-based tests for _to_dict serialization."""

    @given(st.booleans(), st.text(max_size=50), st.integers())
    def test_default_value_to_dict(self, present, repr_str, literal):
        """DefaultValue should serialize correctly."""
        dv = DefaultValue(
            present=present,
            repr=repr_str if present else None,
            literal=literal if present else None,
            is_literal=present
        )
        result = _to_dict(dv)
        assert isinstance(result, dict)
        assert result["present"] == present

    @given(st.text(max_size=30).filter(lambda x: x.isidentifier() or x == ""))
    def test_annotation_to_dict(self, raw):
        """Annotation should serialize correctly."""
        ann = Annotation(raw=raw if raw else None)
        result = _to_dict(ann)
        assert isinstance(result, dict)

    @given(st.text(min_size=1, max_size=20).filter(str.isidentifier))
    def test_param_spec_to_dict(self, name):
        """ParamSpec should serialize correctly."""
        ps = ParamSpec(name=name)
        result = _to_dict(ps)
        assert isinstance(result, dict)
        assert result["name"] == name


class TestAnalysisResultToDictProperties:
    """Property-based tests for AnalysisResult serialization."""

    @given(st.text(min_size=1, max_size=50))
    def test_analysis_result_serializable(self, project_root):
        """AnalysisResult should always be JSON serializable."""
        result = AnalysisResult(project_root=project_root)
        dict_result = result.to_dict()

        # Should not raise
        json_str = json.dumps(dict_result)
        # Should round-trip
        parsed = json.loads(json_str)
        assert parsed["project_root"] == project_root

    @given(st.lists(
        st.text(min_size=1, max_size=20).filter(str.isidentifier),
        min_size=0,
        max_size=5
    ))
    @settings(max_examples=20)
    def test_analysis_result_with_modules(self, module_names):
        """AnalysisResult with modules should serialize correctly."""
        modules = []
        for name in module_names:
            modules.append(ModuleSpec(module_id=name, display_name=name))

        result = AnalysisResult(project_root="/test", modules=modules)
        dict_result = result.to_dict()

        json_str = json.dumps(dict_result)
        parsed = json.loads(json_str)
        assert len(parsed["modules"]) == len(module_names)


class TestEnumSerializationProperties:
    """Property-based tests for enum serialization."""

    @given(st.sampled_from(list(ActionKind)))
    def test_action_kind_to_dict(self, kind):
        """ActionKind enums should serialize to string values."""
        result = _to_dict(kind)
        assert result == kind.value
        assert isinstance(result, str)

    @given(st.sampled_from(list(WidgetType)))
    def test_widget_type_to_dict(self, widget):
        """WidgetType enums should serialize to string values."""
        result = _to_dict(widget)
        assert result == widget.value

    @given(st.sampled_from(list(AnalysisMode)))
    def test_analysis_mode_to_dict(self, mode):
        """AnalysisMode enums should serialize to string values."""
        result = _to_dict(mode)
        assert result == mode.value


class TestConversionRobustness:
    """Property-based tests for conversion robustness."""

    @given(st.text(max_size=100))
    @settings(max_examples=50)
    def test_parse_type_annotation_never_crashes(self, raw):
        """parse_type_annotation should never crash on any input."""
        # Should not raise
        info = parse_type_annotation(raw)
        assert info is not None
        assert isinstance(info.category, TypeCategory)

    @given(
        st.text(max_size=50),
        st.sampled_from(["int", "str", "bool", "float", "Optional[int]", "list[str]"])
    )
    @settings(max_examples=50)
    def test_convert_value_never_crashes(self, value, type_str):
        """convert_value should never crash, only return success/failure."""
        type_info = parse_type_annotation(type_str)
        # Should not raise
        result = convert_value(value, type_info)
        assert result is not None
        assert isinstance(result.success, bool)


class TestTypeInfoInvariants:
    """Property-based tests for TypeInfo invariants."""

    @given(st.sampled_from(["int", "float", "bool", "str", "Path", "date", "datetime", "time", "Decimal"]))
    def test_basic_type_has_widget(self, type_str):
        """Basic types should have appropriate widgets."""
        info = parse_type_annotation(type_str)
        assert info.widget is not None
        assert isinstance(info.widget, WidgetType)

    @given(st.sampled_from([
        'Literal["a"]',
        'Literal["a", "b"]',
        'Literal["x", "y", "z"]',
    ]))
    def test_literal_type_has_options(self, type_str):
        """Literal types should have options populated."""
        info = parse_type_annotation(type_str)
        assert info.category == TypeCategory.LITERAL
        assert len(info.options) >= 1
        assert info.widget == WidgetType.COMBO_BOX

    @given(st.sampled_from(["int", "str", "float", "bool"]))
    def test_optional_preserves_inner_widget(self, inner_type):
        """Optional[T] should preserve inner type's widget."""
        inner_info = parse_type_annotation(inner_type)
        optional_info = parse_type_annotation(f"Optional[{inner_type}]")

        assert optional_info.widget == inner_info.widget
        assert optional_info.is_optional is True

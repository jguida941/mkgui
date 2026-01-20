"""Comprehensive tests for the models module."""

import json
from datetime import datetime

import pytest

from mkgui.models import (
    ActionKind,
    ActionSpec,
    AnalysisMode,
    AnalysisResult,
    Annotation,
    DefaultValue,
    DocSpec,
    IntrospectionStatus,
    InvocationPlan,
    ModuleSpec,
    ParamKind,
    ParamSpec,
    ParamUI,
    ParamValidation,
    ResultKind,
    ReturnSpec,
    ReturnUI,
    Warning,
    WidgetType,
    _to_dict,
)


class TestEnumValues:
    """Test all enum classes have expected values."""

    def test_analysis_mode_values(self):
        """AnalysisMode should have ast_only and introspect values."""
        assert AnalysisMode.AST_ONLY.value == "ast_only"
        assert AnalysisMode.INTROSPECT.value == "introspect"
        assert len(AnalysisMode) == 2

    def test_invocation_plan_values(self):
        """InvocationPlan should have all expected values."""
        expected = {
            "direct_call", "module_as_script", "script_path",
            "click_command", "typer_command", "console_script_entrypoint",
            "cli_generic"
        }
        actual = {plan.value for plan in InvocationPlan}
        assert actual == expected

    def test_action_kind_values(self):
        """ActionKind should have all expected values."""
        expected = {
            "function", "method", "staticmethod", "classmethod",
            "class", "entrypoint", "cli_command"
        }
        actual = {kind.value for kind in ActionKind}
        assert actual == expected

    def test_param_kind_values(self):
        """ParamKind should have all expected values."""
        expected = {
            "positional_only", "positional_or_keyword",
            "var_positional", "keyword_only", "var_keyword"
        }
        actual = {kind.value for kind in ParamKind}
        assert actual == expected

    def test_widget_type_values(self):
        """WidgetType should have all expected values."""
        expected = {
            "spin_box", "double_spin_box", "check_box", "line_edit",
            "file_picker", "combo_box", "plain_text_edit", "json_editor",
            "date_edit", "datetime_edit", "time_edit"
        }
        actual = {widget.value for widget in WidgetType}
        assert actual == expected

    def test_result_kind_values(self):
        """ResultKind should have all expected values."""
        expected = {"none", "text", "json", "table", "file", "repr"}
        actual = {kind.value for kind in ResultKind}
        assert actual == expected


class TestEnumStringBehavior:
    """Test that enums inherit str behavior correctly."""

    def test_analysis_mode_str_concatenation(self):
        """AnalysisMode should support string operations."""
        mode = AnalysisMode.AST_ONLY
        assert "Mode: " + mode == "Mode: ast_only"

    def test_action_kind_in_string_format(self):
        """ActionKind should work in f-strings."""
        kind = ActionKind.FUNCTION
        assert f"Type: {kind}" == "Type: function"

    def test_widget_type_json_serializable(self):
        """WidgetType should be JSON serializable as string."""
        widget = WidgetType.SPIN_BOX
        serialized = json.dumps({"widget": widget})
        assert '"spin_box"' in serialized


class TestDefaultValueDataclass:
    """Test DefaultValue dataclass."""

    def test_default_initialization(self):
        """DefaultValue should have correct defaults."""
        dv = DefaultValue()
        assert dv.present is False
        assert dv.repr is None
        assert dv.literal is None
        assert dv.is_literal is False

    def test_with_literal_value(self):
        """DefaultValue with literal value."""
        dv = DefaultValue(present=True, repr="42", literal=42, is_literal=True)
        assert dv.present is True
        assert dv.repr == "42"
        assert dv.literal == 42
        assert dv.is_literal is True

    def test_with_non_literal_value(self):
        """DefaultValue with non-literal (expression) value."""
        dv = DefaultValue(present=True, repr="some_func()", is_literal=False)
        assert dv.present is True
        assert dv.repr == "some_func()"
        assert dv.is_literal is False


class TestAnnotationDataclass:
    """Test Annotation dataclass."""

    def test_default_initialization(self):
        """Annotation should have correct defaults."""
        ann = Annotation()
        assert ann.raw is None
        assert ann.resolved is None

    def test_with_raw_annotation(self):
        """Annotation with raw type string."""
        ann = Annotation(raw="int")
        assert ann.raw == "int"
        assert ann.resolved is None

    def test_with_resolved_annotation(self):
        """Annotation with resolved type."""
        ann = Annotation(raw="Optional[str]", resolved="str | None")
        assert ann.raw == "Optional[str]"
        assert ann.resolved == "str | None"


class TestParamUIDataclass:
    """Test ParamUI dataclass."""

    def test_default_initialization(self):
        """ParamUI should default to LINE_EDIT with empty options."""
        ui = ParamUI()
        assert ui.widget == WidgetType.LINE_EDIT
        assert ui.options == []

    def test_with_combo_box_options(self):
        """ParamUI with combo box and options."""
        ui = ParamUI(widget=WidgetType.COMBO_BOX, options=["a", "b", "c"])
        assert ui.widget == WidgetType.COMBO_BOX
        assert ui.options == ["a", "b", "c"]


class TestParamValidationDataclass:
    """Test ParamValidation dataclass."""

    def test_default_initialization(self):
        """ParamValidation should have all None defaults."""
        pv = ParamValidation()
        assert pv.min is None
        assert pv.max is None
        assert pv.regex is None

    def test_with_numeric_constraints(self):
        """ParamValidation with min/max constraints."""
        pv = ParamValidation(min=0, max=100)
        assert pv.min == 0
        assert pv.max == 100

    def test_with_regex_constraint(self):
        """ParamValidation with regex constraint."""
        pv = ParamValidation(regex=r"^\d{3}-\d{4}$")
        assert pv.regex == r"^\d{3}-\d{4}$"


class TestParamSpecDataclass:
    """Test ParamSpec dataclass."""

    def test_minimal_initialization(self):
        """ParamSpec should work with just name."""
        ps = ParamSpec(name="arg")
        assert ps.name == "arg"
        assert ps.kind == ParamKind.POSITIONAL_OR_KEYWORD
        assert ps.required is True
        assert isinstance(ps.default, DefaultValue)
        assert isinstance(ps.annotation, Annotation)
        assert isinstance(ps.ui, ParamUI)
        assert isinstance(ps.validation, ParamValidation)

    def test_full_initialization(self):
        """ParamSpec with all fields specified."""
        ps = ParamSpec(
            name="count",
            kind=ParamKind.KEYWORD_ONLY,
            required=False,
            default=DefaultValue(present=True, repr="10", literal=10, is_literal=True),
            annotation=Annotation(raw="int"),
            ui=ParamUI(widget=WidgetType.SPIN_BOX),
            validation=ParamValidation(min=0, max=1000),
        )
        assert ps.name == "count"
        assert ps.kind == ParamKind.KEYWORD_ONLY
        assert ps.required is False
        assert ps.default.literal == 10
        assert ps.annotation.raw == "int"
        assert ps.ui.widget == WidgetType.SPIN_BOX
        assert ps.validation.max == 1000


class TestReturnUIDataclass:
    """Test ReturnUI dataclass."""

    def test_default_initialization(self):
        """ReturnUI should default to TEXT result."""
        rui = ReturnUI()
        assert rui.result_kind == ResultKind.TEXT
        assert rui.options == {}

    def test_with_json_result(self):
        """ReturnUI with JSON result kind."""
        rui = ReturnUI(result_kind=ResultKind.JSON, options={"indent": 2})
        assert rui.result_kind == ResultKind.JSON
        assert rui.options == {"indent": 2}


class TestReturnSpecDataclass:
    """Test ReturnSpec dataclass."""

    def test_default_initialization(self):
        """ReturnSpec should have default annotation and UI."""
        rs = ReturnSpec()
        assert isinstance(rs.annotation, Annotation)
        assert isinstance(rs.ui, ReturnUI)

    def test_with_annotation(self):
        """ReturnSpec with type annotation."""
        rs = ReturnSpec(annotation=Annotation(raw="dict[str, int]"))
        assert rs.annotation.raw == "dict[str, int]"


class TestDocSpecDataclass:
    """Test DocSpec dataclass."""

    def test_default_initialization(self):
        """DocSpec should have None text and plain format."""
        ds = DocSpec()
        assert ds.text is None
        assert ds.format == "plain"

    def test_with_docstring(self):
        """DocSpec with docstring text."""
        ds = DocSpec(text="This is a function.", format="rst")
        assert ds.text == "This is a function."
        assert ds.format == "rst"


class TestIntrospectionStatusDataclass:
    """Test IntrospectionStatus dataclass."""

    def test_default_initialization(self):
        """IntrospectionStatus should have all False/None defaults."""
        ins = IntrospectionStatus()
        assert ins.attempted is False
        assert ins.success is False
        assert ins.error is None
        assert ins.annotations_resolved is False

    def test_successful_introspection(self):
        """IntrospectionStatus after successful introspection."""
        ins = IntrospectionStatus(
            attempted=True,
            success=True,
            annotations_resolved=True
        )
        assert ins.attempted is True
        assert ins.success is True
        assert ins.annotations_resolved is True

    def test_failed_introspection(self):
        """IntrospectionStatus after failed introspection."""
        ins = IntrospectionStatus(
            attempted=True,
            success=False,
            error="Import error: module not found"
        )
        assert ins.attempted is True
        assert ins.success is False
        assert ins.error == "Import error: module not found"


class TestActionSpecDataclass:
    """Test ActionSpec dataclass."""

    def test_minimal_initialization(self):
        """ActionSpec with required fields only."""
        action = ActionSpec(
            action_id="test.func:abc123",
            kind=ActionKind.FUNCTION,
            qualname="test.func",
            name="func",
            module_import_path="test"
        )
        assert action.action_id == "test.func:abc123"
        assert action.kind == ActionKind.FUNCTION
        assert action.qualname == "test.func"
        assert action.name == "func"
        assert action.module_import_path == "test"
        assert isinstance(action.doc, DocSpec)
        assert action.parameters == []
        assert isinstance(action.returns, ReturnSpec)
        assert action.invocation_plan == InvocationPlan.DIRECT_CALL
        assert isinstance(action.introspection, IntrospectionStatus)
        assert action.tags == []
        assert action.side_effect_risk is False
        assert action.source_line is None

    def test_full_initialization(self):
        """ActionSpec with all fields specified."""
        action = ActionSpec(
            action_id="mymod.MyClass.method:def456",
            kind=ActionKind.CLASSMETHOD,
            qualname="mymod.MyClass.method",
            name="method",
            module_import_path="mymod.MyClass",
            doc=DocSpec(text="A class method."),
            parameters=[ParamSpec(name="cls"), ParamSpec(name="x")],
            returns=ReturnSpec(annotation=Annotation(raw="str")),
            invocation_plan=InvocationPlan.DIRECT_CALL,
            tags=["class:MyClass", "classmethod"],
            side_effect_risk=True,
            source_line=42
        )
        assert action.kind == ActionKind.CLASSMETHOD
        assert action.doc.text == "A class method."
        assert len(action.parameters) == 2
        assert action.tags == ["class:MyClass", "classmethod"]
        assert action.side_effect_risk is True
        assert action.source_line == 42


class TestModuleSpecDataclass:
    """Test ModuleSpec dataclass."""

    def test_minimal_initialization(self):
        """ModuleSpec with required fields only."""
        ms = ModuleSpec(
            module_id="mymodule",
            display_name="mymodule"
        )
        assert ms.module_id == "mymodule"
        assert ms.display_name == "mymodule"
        assert ms.file_path is None
        assert ms.import_path is None
        assert ms.actions == []
        assert ms.has_main_block is False
        assert ms.all_exports is None
        assert ms.side_effect_risk is False

    def test_full_initialization(self):
        """ModuleSpec with all fields specified."""
        action = ActionSpec(
            action_id="mod.func:123",
            kind=ActionKind.FUNCTION,
            qualname="mod.func",
            name="func",
            module_import_path="mod"
        )
        ms = ModuleSpec(
            module_id="pkg.mod",
            display_name="mod",
            file_path="/path/to/mod.py",
            import_path="pkg.mod",
            actions=[action],
            has_main_block=True,
            all_exports=["func"],
            side_effect_risk=False
        )
        assert ms.file_path == "/path/to/mod.py"
        assert ms.has_main_block is True
        assert ms.all_exports == ["func"]
        assert len(ms.actions) == 1


class TestWarningDataclass:
    """Test Warning dataclass."""

    def test_minimal_initialization(self):
        """Warning with required fields only."""
        w = Warning(code="SYNTAX_ERROR", message="Invalid syntax")
        assert w.code == "SYNTAX_ERROR"
        assert w.message == "Invalid syntax"
        assert w.file_path is None
        assert w.line is None

    def test_full_initialization(self):
        """Warning with all fields specified."""
        w = Warning(
            code="READ_ERROR",
            message="Could not read file",
            file_path="/path/to/file.py",
            line=10
        )
        assert w.file_path == "/path/to/file.py"
        assert w.line == 10


class TestAnalysisResultDataclass:
    """Test AnalysisResult dataclass."""

    def test_default_initialization(self):
        """AnalysisResult should have sensible defaults."""
        ar = AnalysisResult()
        assert ar.spec_version == "1.0"
        assert ar.generator_version == "0.1.0"
        assert ar.created_at is not None  # Should be set to current time
        assert ar.project_root == ""
        assert ar.analysis_mode == AnalysisMode.AST_ONLY
        assert ar.python_target is None
        assert ar.modules == []
        assert ar.warnings == []

    def test_created_at_is_iso_format(self):
        """created_at should be in ISO format."""
        ar = AnalysisResult()
        # Should be parseable as datetime
        datetime.fromisoformat(ar.created_at)

    def test_full_initialization(self):
        """AnalysisResult with all fields specified."""
        module = ModuleSpec(module_id="test", display_name="test")
        warning = Warning(code="TEST", message="Test warning")
        ar = AnalysisResult(
            spec_version="2.0",
            generator_version="1.0.0",
            created_at="2025-01-01T00:00:00",
            project_root="/path/to/project",
            analysis_mode=AnalysisMode.INTROSPECT,
            python_target="3.11",
            modules=[module],
            warnings=[warning]
        )
        assert ar.spec_version == "2.0"
        assert ar.generator_version == "1.0.0"
        assert ar.project_root == "/path/to/project"
        assert ar.analysis_mode == AnalysisMode.INTROSPECT
        assert ar.python_target == "3.11"
        assert len(ar.modules) == 1
        assert len(ar.warnings) == 1


class TestToDictFunction:
    """Test the _to_dict helper function."""

    def test_simple_dataclass(self):
        """_to_dict should convert simple dataclass to dict."""
        dv = DefaultValue(present=True, repr="42", literal=42, is_literal=True)
        result = _to_dict(dv)
        assert result == {
            "present": True,
            "repr": "42",
            "literal": 42,
            "is_literal": True
        }

    def test_nested_dataclass(self):
        """_to_dict should handle nested dataclasses."""
        ps = ParamSpec(
            name="x",
            annotation=Annotation(raw="int"),
            default=DefaultValue(present=True, repr="0", literal=0, is_literal=True)
        )
        result = _to_dict(ps)
        assert result["name"] == "x"
        assert result["annotation"]["raw"] == "int"
        assert result["default"]["literal"] == 0

    def test_enum_conversion(self):
        """_to_dict should convert enums to their values."""
        ui = ParamUI(widget=WidgetType.SPIN_BOX)
        result = _to_dict(ui)
        assert result["widget"] == "spin_box"

    def test_list_conversion(self):
        """_to_dict should handle lists."""
        ms = ModuleSpec(
            module_id="test",
            display_name="test",
            all_exports=["a", "b", "c"]
        )
        result = _to_dict(ms)
        assert result["all_exports"] == ["a", "b", "c"]

    def test_list_of_dataclasses(self):
        """_to_dict should handle lists of dataclasses."""
        params = [
            ParamSpec(name="a"),
            ParamSpec(name="b"),
        ]
        result = _to_dict(params)
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["name"] == "a"
        assert result[1]["name"] == "b"

    def test_dict_conversion(self):
        """_to_dict should handle dicts."""
        rui = ReturnUI(options={"indent": 2, "sort_keys": True})
        result = _to_dict(rui)
        assert result["options"] == {"indent": 2, "sort_keys": True}

    def test_none_values(self):
        """_to_dict should preserve None values."""
        ann = Annotation(raw=None, resolved=None)
        result = _to_dict(ann)
        assert result["raw"] is None
        assert result["resolved"] is None

    def test_primitive_passthrough(self):
        """_to_dict should pass through primitives unchanged."""
        assert _to_dict(42) == 42
        assert _to_dict("hello") == "hello"
        assert _to_dict(3.14) == 3.14
        assert _to_dict(True) is True
        assert _to_dict(None) is None


class TestAnalysisResultToDict:
    """Test AnalysisResult.to_dict() method."""

    def test_empty_result_to_dict(self):
        """Empty result should serialize correctly."""
        ar = AnalysisResult()
        result = ar.to_dict()
        assert isinstance(result, dict)
        assert result["spec_version"] == "1.0"
        assert result["modules"] == []
        assert result["warnings"] == []
        assert result["analysis_mode"] == "ast_only"

    def test_full_result_to_dict(self):
        """Full result with nested structures should serialize correctly."""
        action = ActionSpec(
            action_id="mod.func:abc",
            kind=ActionKind.FUNCTION,
            qualname="mod.func",
            name="func",
            module_import_path="mod",
            parameters=[
                ParamSpec(
                    name="x",
                    kind=ParamKind.POSITIONAL_OR_KEYWORD,
                    annotation=Annotation(raw="int"),
                    ui=ParamUI(widget=WidgetType.SPIN_BOX)
                )
            ]
        )
        module = ModuleSpec(
            module_id="mod",
            display_name="mod",
            actions=[action]
        )
        ar = AnalysisResult(
            project_root="/test",
            modules=[module]
        )
        result = ar.to_dict()

        # Check nested structure
        assert len(result["modules"]) == 1
        mod_dict = result["modules"][0]
        assert mod_dict["module_id"] == "mod"
        assert len(mod_dict["actions"]) == 1

        action_dict = mod_dict["actions"][0]
        assert action_dict["name"] == "func"
        assert action_dict["kind"] == "function"

        param_dict = action_dict["parameters"][0]
        assert param_dict["name"] == "x"
        assert param_dict["ui"]["widget"] == "spin_box"

    def test_to_dict_is_json_serializable(self):
        """to_dict output should be JSON serializable."""
        ar = AnalysisResult(
            project_root="/test",
            modules=[
                ModuleSpec(
                    module_id="test",
                    display_name="test",
                    actions=[
                        ActionSpec(
                            action_id="test.fn:123",
                            kind=ActionKind.ENTRYPOINT,
                            qualname="test.fn",
                            name="fn",
                            module_import_path="test"
                        )
                    ]
                )
            ]
        )
        # Should not raise
        json_str = json.dumps(ar.to_dict())
        # Should be able to parse back
        parsed = json.loads(json_str)
        assert parsed["modules"][0]["module_id"] == "test"

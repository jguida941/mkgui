"""Snapshot/regression tests using syrupy for py2gui.

These tests capture the output of analysis operations and compare against
stored snapshots. If the output changes, the test fails, alerting us to
potential regressions or intentional changes that need verification.

Run with --snapshot-update to regenerate snapshots when changes are intentional.
"""

from pathlib import Path

import pytest

from py2gui.analyzer import analyze_project
from py2gui.inspector import parse_type_annotation, inspect_parameters
from py2gui.models import Annotation, ParamSpec


class TestAnalyzerSnapshots:
    """Snapshot tests for analyzer output."""

    def test_simple_function_analysis(self, tmp_path, snapshot):
        """Snapshot test for simple function analysis."""
        code = '''
def greet(name: str, greeting: str = "Hello") -> str:
    """Greet someone by name."""
    return f"{greeting}, {name}!"
'''
        (tmp_path / "simple.py").write_text(code)
        result = analyze_project(tmp_path / "simple.py")

        # Convert to dict for snapshot comparison
        snapshot_data = {
            "module_count": len(result.modules),
            "actions": [
                {
                    "name": a.name,
                    "kind": a.kind.value,
                    "parameters": [
                        {
                            "name": p.name,
                            "kind": p.kind.value,
                            "required": p.required,
                            "annotation": p.annotation.raw,
                            "has_default": p.default.present,
                        }
                        for p in a.parameters
                    ],
                    "return_annotation": a.returns.annotation.raw,
                    "has_docstring": a.doc.text is not None,
                }
                for m in result.modules
                for a in m.actions
            ]
        }
        assert snapshot_data == snapshot

    def test_class_methods_analysis(self, tmp_path, snapshot):
        """Snapshot test for class with staticmethod and classmethod."""
        code = '''
class Calculator:
    """A simple calculator class."""

    @staticmethod
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    @classmethod
    def create(cls, initial: int = 0) -> "Calculator":
        """Create a calculator instance."""
        return cls()

    def instance_method(self):
        """This should be excluded."""
        pass
'''
        (tmp_path / "calculator.py").write_text(code)
        result = analyze_project(tmp_path / "calculator.py")

        snapshot_data = {
            "module_count": len(result.modules),
            "actions": [
                {
                    "name": a.name,
                    "kind": a.kind.value,
                    "qualname": a.qualname,
                    "param_count": len(a.parameters),
                }
                for m in result.modules
                for a in m.actions
            ]
        }
        assert snapshot_data == snapshot

    def test_cli_decorators_analysis(self, tmp_path, snapshot):
        """Snapshot test for CLI decorator detection."""
        code = '''
import click
import typer

@click.command()
def click_cmd():
    """Click command."""
    pass

@typer.command()
def typer_cmd():
    """Typer command."""
    pass

def main():
    """Entrypoint function."""
    pass
'''
        (tmp_path / "cli_commands.py").write_text(code)
        result = analyze_project(tmp_path / "cli_commands.py")

        snapshot_data = {
            "actions": [
                {
                    "name": a.name,
                    "kind": a.kind.value,
                    "invocation_plan": a.invocation_plan.value,
                }
                for m in result.modules
                for a in m.actions
            ]
        }
        assert snapshot_data == snapshot

    def test_complex_parameters_analysis(self, tmp_path, snapshot):
        """Snapshot test for various parameter kinds."""
        code = '''
def complex_func(
    pos_only, /,
    regular,
    with_default="default",
    *args,
    kw_only,
    kw_with_default=42,
    **kwargs
) -> dict:
    """Function with all parameter kinds."""
    pass
'''
        (tmp_path / "params.py").write_text(code)
        result = analyze_project(tmp_path / "params.py")

        snapshot_data = {
            "parameters": [
                {
                    "name": p.name,
                    "kind": p.kind.value,
                    "required": p.required,
                    "has_default": p.default.present,
                    "default_repr": p.default.repr,
                }
                for m in result.modules
                for a in m.actions
                for p in a.parameters
            ]
        }
        assert snapshot_data == snapshot


class TestInspectorSnapshots:
    """Snapshot tests for type inspector output."""

    def test_basic_type_parsing(self, snapshot):
        """Snapshot test for basic type annotation parsing."""
        types = ["int", "float", "bool", "str", "Path", "Any"]
        snapshot_data = {
            t: {
                "category": parse_type_annotation(t).category.value,
                "widget": parse_type_annotation(t).widget.value,
                "is_optional": parse_type_annotation(t).is_optional,
            }
            for t in types
        }
        assert snapshot_data == snapshot

    def test_optional_type_parsing(self, snapshot):
        """Snapshot test for optional type parsing."""
        types = [
            "Optional[int]",
            "Optional[str]",
            "Union[int, None]",
            "str | None",
            "None | float",
        ]
        snapshot_data = {
            t: {
                "category": parse_type_annotation(t).category.value,
                "widget": parse_type_annotation(t).widget.value,
                "is_optional": parse_type_annotation(t).is_optional,
            }
            for t in types
        }
        assert snapshot_data == snapshot

    def test_container_type_parsing(self, snapshot):
        """Snapshot test for container type parsing."""
        types = [
            "list[str]",
            "List[int]",
            "dict",
            "Dict[str, int]",
            "Tuple[str, int]",
        ]
        snapshot_data = {
            t: {
                "category": parse_type_annotation(t).category.value,
                "widget": parse_type_annotation(t).widget.value,
                "has_inner_type": parse_type_annotation(t).inner_type is not None,
            }
            for t in types
        }
        assert snapshot_data == snapshot

    def test_literal_type_parsing(self, snapshot):
        """Snapshot test for Literal type parsing."""
        types = [
            'Literal["a", "b", "c"]',
            'Literal["on", "off"]',
            "Literal[1, 2, 3]",
        ]
        snapshot_data = {
            t: {
                "category": parse_type_annotation(t).category.value,
                "widget": parse_type_annotation(t).widget.value,
                "options": parse_type_annotation(t).options,
            }
            for t in types
        }
        assert snapshot_data == snapshot

    def test_datetime_type_parsing(self, snapshot):
        """Snapshot test for datetime type parsing."""
        types = ["date", "datetime", "time", "Decimal"]
        snapshot_data = {
            t: {
                "category": parse_type_annotation(t).category.value,
                "widget": parse_type_annotation(t).widget.value,
            }
            for t in types
        }
        assert snapshot_data == snapshot


class TestInspectParametersSnapshots:
    """Snapshot tests for parameter inspection."""

    def test_mixed_parameters_inspection(self, snapshot):
        """Snapshot test for inspecting mixed parameter types."""
        params = [
            ParamSpec(name="count", annotation=Annotation(raw="int")),
            ParamSpec(name="name", annotation=Annotation(raw="str")),
            ParamSpec(name="enabled", annotation=Annotation(raw="bool")),
            ParamSpec(name="path", annotation=Annotation(raw="Path")),
            ParamSpec(name="mode", annotation=Annotation(raw='Literal["fast", "slow"]')),
            ParamSpec(name="data", annotation=Annotation(raw="dict")),
            ParamSpec(name="items", annotation=Annotation(raw="list[str]")),
            ParamSpec(name="optional_val", annotation=Annotation(raw="Optional[int]")),
        ]

        results = inspect_parameters(params)

        snapshot_data = {
            p.name: {
                "widget": p.ui.widget.value,
                "options": p.ui.options,
                "validation_min": p.validation.min,
                "validation_max": p.validation.max,
            }
            for p in results
        }
        assert snapshot_data == snapshot


class TestAnalysisResultSnapshots:
    """Snapshot tests for full analysis results."""

    def test_multi_file_project(self, tmp_path, snapshot):
        """Snapshot test for analyzing a multi-file project."""
        # Create a mini project
        pkg = tmp_path / "mypackage"
        pkg.mkdir()

        (pkg / "__init__.py").write_text('"""Package init."""\n__version__ = "1.0.0"\n')

        (pkg / "core.py").write_text('''
"""Core functionality."""

def process(data: str) -> str:
    """Process data."""
    return data.upper()

def validate(value: int, min_val: int = 0, max_val: int = 100) -> bool:
    """Validate value is in range."""
    return min_val <= value <= max_val
''')

        (pkg / "utils.py").write_text('''
"""Utility functions."""

from typing import Optional, List

def parse_csv(text: str) -> List[str]:
    """Parse CSV text."""
    return text.split(",")

def format_name(first: str, last: str, middle: Optional[str] = None) -> str:
    """Format a name."""
    return f"{first} {last}"
''')

        result = analyze_project(tmp_path)

        # Extract key information for snapshot
        snapshot_data = {
            "module_count": len(result.modules),
            "modules": sorted([
                {
                    "id": m.module_id,
                    "action_count": len(m.actions),
                    "actions": sorted([a.name for a in m.actions])
                }
                for m in result.modules
            ], key=lambda x: x["id"])
        }
        assert snapshot_data == snapshot

    def test_project_with_all_exports(self, tmp_path, snapshot):
        """Snapshot test for project using __all__."""
        code = '''
"""Module with __all__ exports."""

__all__ = ["public_func", "PublicClass"]

def public_func():
    """Exported function."""
    pass

def private_func():
    """Not exported."""
    pass

class PublicClass:
    """Exported class."""

    @staticmethod
    def method():
        """Class method."""
        pass

class PrivateClass:
    """Not exported."""

    @staticmethod
    def method():
        """Should not appear."""
        pass
'''
        (tmp_path / "exports.py").write_text(code)
        result = analyze_project(tmp_path / "exports.py")

        snapshot_data = {
            "all_exports": result.modules[0].all_exports,
            "detected_actions": sorted([a.name for a in result.modules[0].actions])
        }
        assert snapshot_data == snapshot

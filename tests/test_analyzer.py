"""Comprehensive tests for the AST analyzer."""

import tempfile
from pathlib import Path

import pytest

from mkgui.analyzer import (
    ASTAnalyzer,
    ENTRYPOINT_NAMES,
    IGNORE_DIR_PATTERNS,
    IGNORE_FILE_PATTERNS,
    _matches_pattern,
    analyze_project,
)
from mkgui.models import ActionKind, AnalysisMode, InvocationPlan, ParamKind


class TestMatchesPattern:
    """Test the _matches_pattern helper function."""

    def test_exact_match(self):
        """Exact name should match pattern."""
        assert _matches_pattern("tests", ["tests", "build"])
        assert _matches_pattern("build", ["tests", "build"])

    def test_wildcard_prefix(self):
        """Wildcard prefix should match."""
        assert _matches_pattern("test_utils.py", ["test_*.py"])
        assert _matches_pattern("test_.py", ["test_*.py"])

    def test_wildcard_suffix(self):
        """Wildcard suffix should match."""
        assert _matches_pattern("utils_test.py", ["*_test.py"])
        assert _matches_pattern("mypackage.egg-info", ["*.egg-info"])

    def test_no_match(self):
        """Non-matching names should return False."""
        assert not _matches_pattern("main.py", ["test_*.py", "*_test.py"])
        assert not _matches_pattern("src", ["tests", "build"])

    def test_empty_patterns(self):
        """Empty patterns list should return False."""
        assert not _matches_pattern("anything", [])


class TestASTAnalyzerInit:
    """Test ASTAnalyzer initialization."""

    def test_init_with_string_path(self, tmp_path: Path):
        """Should accept string path."""
        analyzer = ASTAnalyzer(str(tmp_path))
        assert analyzer.project_root == tmp_path.resolve()

    def test_init_with_path_object(self, tmp_path: Path):
        """Should accept Path object."""
        analyzer = ASTAnalyzer(tmp_path)
        assert analyzer.project_root == tmp_path.resolve()

    def test_init_default_mode(self, tmp_path: Path):
        """Default mode should be AST_ONLY."""
        analyzer = ASTAnalyzer(tmp_path)
        assert analyzer.analysis_mode == AnalysisMode.AST_ONLY

    def test_init_with_introspect_mode(self, tmp_path: Path):
        """Should accept INTROSPECT mode."""
        analyzer = ASTAnalyzer(tmp_path, analysis_mode=AnalysisMode.INTROSPECT)
        assert analyzer.analysis_mode == AnalysisMode.INTROSPECT

    def test_init_empty_warnings(self, tmp_path: Path):
        """Warnings should start empty."""
        analyzer = ASTAnalyzer(tmp_path)
        assert analyzer.warnings == []


class TestAnalyzeEmptyProject:
    """Test analyzing empty or non-Python projects."""

    def test_empty_directory(self, tmp_path: Path):
        """Empty directory should return empty result."""
        result = analyze_project(tmp_path)
        assert result.modules == []
        assert result.warnings == []

    def test_non_python_files_only(self, tmp_path: Path):
        """Directory with only non-Python files should return empty result."""
        (tmp_path / "readme.md").write_text("# README")
        (tmp_path / "data.json").write_text("{}")
        result = analyze_project(tmp_path)
        assert result.modules == []


class TestAnalyzeSingleFile:
    """Test analyzing a single Python file."""

    def test_single_function(self, tmp_path: Path):
        """Single function should be detected."""
        code = "def hello(): pass"
        (tmp_path / "test.py").write_text(code)
        result = analyze_project(tmp_path / "test.py")

        assert len(result.modules) == 1
        assert len(result.modules[0].actions) == 1
        assert result.modules[0].actions[0].name == "hello"

    def test_module_metadata(self, tmp_path: Path):
        """Module metadata should be set correctly."""
        code = "def hello(): pass"
        file_path = tmp_path / "mymodule.py"
        file_path.write_text(code)
        result = analyze_project(file_path)

        module = result.modules[0]
        # When analyzing a single file, module_id may be empty (relative to itself)
        # display_name should be the file stem
        assert module.display_name == "mymodule"
        # File path should be set and contain the filename
        assert module.file_path is not None
        assert "mymodule.py" in module.file_path

    def test_private_functions_excluded(self, tmp_path: Path):
        """Functions starting with _ should be excluded."""
        code = '''
def public_func(): pass
def _private_func(): pass
def __dunder__(): pass
'''
        (tmp_path / "test.py").write_text(code)
        result = analyze_project(tmp_path / "test.py")

        names = [a.name for a in result.modules[0].actions]
        assert "public_func" in names
        assert "_private_func" not in names
        assert "__dunder__" not in names

    def test_private_classes_excluded(self, tmp_path: Path):
        """Classes starting with _ should be excluded."""
        code = '''
class PublicClass:
    @staticmethod
    def method(): pass

class _PrivateClass:
    @staticmethod
    def method(): pass
'''
        (tmp_path / "test.py").write_text(code)
        result = analyze_project(tmp_path / "test.py")

        names = [a.name for a in result.modules[0].actions]
        assert "method" in names  # From PublicClass
        # Should only have one method (from PublicClass)
        assert len([n for n in names if n == "method"]) == 1


class TestAsyncFunctions:
    """Test handling of async functions."""

    def test_async_function_detected(self, tmp_path: Path):
        """Async functions should be detected."""
        code = '''
async def fetch_data(url: str) -> dict:
    """Fetch data from URL."""
    pass
'''
        (tmp_path / "test.py").write_text(code)
        result = analyze_project(tmp_path / "test.py")

        assert len(result.modules[0].actions) == 1
        action = result.modules[0].actions[0]
        assert action.name == "fetch_data"
        assert action.kind == ActionKind.FUNCTION

    def test_async_entrypoint(self, tmp_path: Path):
        """Async main function should be detected as entrypoint."""
        code = '''
async def main():
    pass
'''
        (tmp_path / "test.py").write_text(code)
        result = analyze_project(tmp_path / "test.py")

        action = result.modules[0].actions[0]
        assert action.kind == ActionKind.ENTRYPOINT


class TestDocstrings:
    """Test docstring extraction."""

    def test_single_line_docstring(self, tmp_path: Path):
        """Single line docstring should be extracted."""
        code = '''
def func():
    """This is a docstring."""
    pass
'''
        (tmp_path / "test.py").write_text(code)
        result = analyze_project(tmp_path / "test.py")

        action = result.modules[0].actions[0]
        assert action.doc.text == "This is a docstring."

    def test_multiline_docstring(self, tmp_path: Path):
        """Multiline docstring should be extracted."""
        code = '''
def func():
    """
    This is a longer docstring.

    It has multiple lines.
    """
    pass
'''
        (tmp_path / "test.py").write_text(code)
        result = analyze_project(tmp_path / "test.py")

        action = result.modules[0].actions[0]
        assert "longer docstring" in action.doc.text
        assert "multiple lines" in action.doc.text

    def test_no_docstring(self, tmp_path: Path):
        """Function without docstring should have None."""
        code = "def func(): pass"
        (tmp_path / "test.py").write_text(code)
        result = analyze_project(tmp_path / "test.py")

        action = result.modules[0].actions[0]
        assert action.doc.text is None


class TestReturnTypes:
    """Test return type annotation extraction."""

    def test_simple_return_type(self, tmp_path: Path):
        """Simple return type should be extracted."""
        code = "def func() -> int: pass"
        (tmp_path / "test.py").write_text(code)
        result = analyze_project(tmp_path / "test.py")

        action = result.modules[0].actions[0]
        assert action.returns.annotation.raw == "int"

    def test_complex_return_type(self, tmp_path: Path):
        """Complex return type should be extracted."""
        code = "def func() -> dict[str, list[int]]: pass"
        (tmp_path / "test.py").write_text(code)
        result = analyze_project(tmp_path / "test.py")

        action = result.modules[0].actions[0]
        assert action.returns.annotation.raw == "dict[str, list[int]]"

    def test_no_return_type(self, tmp_path: Path):
        """Function without return type should have None."""
        code = "def func(): pass"
        (tmp_path / "test.py").write_text(code)
        result = analyze_project(tmp_path / "test.py")

        action = result.modules[0].actions[0]
        assert action.returns.annotation.raw is None


class TestSideEffectDetection:
    """Test module side effect detection."""

    def test_safe_module(self, tmp_path: Path):
        """Module with only safe patterns should not have side effects."""
        code = '''
"""Module docstring."""

import os
from pathlib import Path

VERSION = "1.0.0"

def func():
    pass

class MyClass:
    pass
'''
        (tmp_path / "test.py").write_text(code)
        result = analyze_project(tmp_path / "test.py")

        assert result.modules[0].side_effect_risk is False

    def test_print_side_effect(self, tmp_path: Path):
        """Module with top-level print should have side effects."""
        code = '''
print("Loading!")

def func():
    pass
'''
        (tmp_path / "test.py").write_text(code)
        result = analyze_project(tmp_path / "test.py")

        assert result.modules[0].side_effect_risk is True

    def test_function_call_side_effect(self, tmp_path: Path):
        """Module with top-level function call should have side effects."""
        code = '''
DB = connect()

def func():
    pass
'''
        (tmp_path / "test.py").write_text(code)
        result = analyze_project(tmp_path / "test.py")

        assert result.modules[0].side_effect_risk is True

    def test_main_guard_not_side_effect(self, tmp_path: Path):
        """if __name__ == '__main__' block should not be side effect."""
        code = '''
def main():
    pass

if __name__ == "__main__":
    main()
'''
        (tmp_path / "test.py").write_text(code)
        result = analyze_project(tmp_path / "test.py")

        assert result.modules[0].side_effect_risk is False
        assert result.modules[0].has_main_block is True


class TestMainBlockDetection:
    """Test if __name__ == '__main__' detection."""

    def test_main_block_detected(self, tmp_path: Path):
        """Main block should be detected."""
        code = '''
def main():
    pass

if __name__ == "__main__":
    main()
'''
        (tmp_path / "test.py").write_text(code)
        result = analyze_project(tmp_path / "test.py")

        assert result.modules[0].has_main_block is True

    def test_no_main_block(self, tmp_path: Path):
        """Module without main block should be detected."""
        code = '''
def func():
    pass
'''
        (tmp_path / "test.py").write_text(code)
        result = analyze_project(tmp_path / "test.py")

        assert result.modules[0].has_main_block is False

    def test_only_main_block_module(self, tmp_path: Path):
        """Module with only main block (no exportable actions) should still be detected."""
        code = '''
if __name__ == "__main__":
    print("Running!")
'''
        (tmp_path / "test.py").write_text(code)
        result = analyze_project(tmp_path / "test.py")

        # Module should exist because it has main block
        assert len(result.modules) == 1
        assert result.modules[0].has_main_block is True


class TestTyperDecorators:
    """Test Typer CLI decorator detection."""

    def test_typer_command_decorator(self, tmp_path: Path):
        """@typer.command() should be detected."""
        code = '''
import typer

@typer.command()
def cli():
    pass
'''
        (tmp_path / "test.py").write_text(code)
        result = analyze_project(tmp_path / "test.py")

        action = result.modules[0].actions[0]
        assert action.kind == ActionKind.CLI_COMMAND
        assert action.invocation_plan == InvocationPlan.TYPER_COMMAND

    def test_app_command_decorator(self, tmp_path: Path):
        """@app.command() should be detected as Typer."""
        code = '''
import typer

app = typer.Typer()

@app.command()
def hello():
    pass
'''
        (tmp_path / "test.py").write_text(code)
        result = analyze_project(tmp_path / "test.py")

        action = result.modules[0].actions[0]
        assert action.kind == ActionKind.CLI_COMMAND
        assert action.invocation_plan == InvocationPlan.TYPER_COMMAND


class TestDecoratorExtraction:
    """Test decorator name extraction."""

    def test_simple_decorator(self, tmp_path: Path):
        """Simple @decorator should be in tags."""
        code = '''
def my_decorator(f):
    return f

@my_decorator
def func():
    pass
'''
        (tmp_path / "test.py").write_text(code)
        result = analyze_project(tmp_path / "test.py")

        # Find func (not my_decorator which is also a function)
        func_action = [a for a in result.modules[0].actions if a.name == "func"][0]
        assert "my_decorator" in func_action.tags

    def test_decorator_with_args(self, tmp_path: Path):
        """@decorator(args) should be in tags."""
        code = '''
@some_decorator(arg=True)
def func():
    pass
'''
        (tmp_path / "test.py").write_text(code)
        result = analyze_project(tmp_path / "test.py")

        action = result.modules[0].actions[0]
        assert "some_decorator" in action.tags

    def test_dotted_decorator(self, tmp_path: Path):
        """@module.decorator should be in tags."""
        code = '''
import click

@click.command()
def func():
    pass
'''
        (tmp_path / "test.py").write_text(code)
        result = analyze_project(tmp_path / "test.py")

        action = result.modules[0].actions[0]
        assert "click.command" in action.tags


class TestFileDiscovery:
    """Test Python file discovery in directories."""

    def test_finds_py_files(self, tmp_path: Path):
        """Should find .py files in directory."""
        (tmp_path / "a.py").write_text("def a(): pass")
        (tmp_path / "b.py").write_text("def b(): pass")
        (tmp_path / "c.txt").write_text("not python")

        result = analyze_project(tmp_path)

        module_names = [m.display_name for m in result.modules]
        assert "a" in module_names
        assert "b" in module_names
        assert len(result.modules) == 2

    def test_finds_nested_files(self, tmp_path: Path):
        """Should find .py files in subdirectories."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (tmp_path / "root.py").write_text("def root(): pass")
        (subdir / "nested.py").write_text("def nested(): pass")

        result = analyze_project(tmp_path)

        module_ids = [m.module_id for m in result.modules]
        assert "root" in module_ids
        assert "subdir.nested" in module_ids

    def test_respects_ignore_patterns(self, sample_project_dir):
        """Should ignore directories matching patterns."""
        result = analyze_project(sample_project_dir)

        module_names = [m.display_name for m in result.modules]
        assert "test_core" not in module_names
        assert "core" in module_names


class TestSyntaxErrors:
    """Test handling of files with syntax errors."""

    def test_syntax_error_warning(self, code_with_syntax_error):
        """Syntax error should generate warning, not crash."""
        result = analyze_project(code_with_syntax_error)

        assert len(result.warnings) == 1
        assert result.warnings[0].code == "SYNTAX_ERROR"
        assert "Syntax error" in result.warnings[0].message

    def test_continues_after_error(self, tmp_path: Path):
        """Should continue analyzing other files after syntax error."""
        (tmp_path / "broken.py").write_text("def broken(")
        (tmp_path / "working.py").write_text("def working(): pass")

        result = analyze_project(tmp_path)

        assert len(result.warnings) == 1
        assert len(result.modules) == 1
        assert result.modules[0].display_name == "working"


class TestPackageStructure:
    """Test package (__init__.py) handling."""

    def test_init_file_module_id(self, tmp_path: Path):
        """__init__.py should have package name as module_id."""
        pkg = tmp_path / "mypackage"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("def init_func(): pass")

        result = analyze_project(tmp_path)

        assert len(result.modules) == 1
        assert result.modules[0].module_id == "mypackage"


class TestAnalyzeProjectFunction:
    """Test the analyze_project convenience function."""

    def test_returns_analysis_result(self, tmp_path: Path):
        """Should return AnalysisResult object."""
        (tmp_path / "test.py").write_text("def func(): pass")
        result = analyze_project(tmp_path)

        assert result.project_root == str(tmp_path.resolve())
        assert result.analysis_mode == AnalysisMode.AST_ONLY

    def test_with_analysis_mode(self, tmp_path: Path):
        """Should accept analysis_mode parameter."""
        (tmp_path / "test.py").write_text("def func(): pass")
        result = analyze_project(tmp_path, analysis_mode=AnalysisMode.INTROSPECT)

        assert result.analysis_mode == AnalysisMode.INTROSPECT


class TestResultStability:
    """Test that results are deterministic and stable."""

    def test_module_ordering(self, tmp_path: Path):
        """Modules should be sorted by module_id."""
        (tmp_path / "zebra.py").write_text("def z(): pass")
        (tmp_path / "alpha.py").write_text("def a(): pass")
        (tmp_path / "beta.py").write_text("def b(): pass")

        result = analyze_project(tmp_path)

        module_ids = [m.module_id for m in result.modules]
        assert module_ids == sorted(module_ids)


class TestPositionalOnlyDefaults:
    """Test correct handling of positional-only parameter defaults."""

    def test_posonly_with_defaults(self, tmp_path: Path):
        """Positional-only args should correctly get their defaults."""
        code = '''
def func(a, b=1, /, c=2, d=3):
    """Function with positional-only defaults."""
    pass
'''
        (tmp_path / "test.py").write_text(code)
        result = analyze_project(tmp_path / "test.py")

        assert len(result.modules) == 1
        action = result.modules[0].actions[0]
        params = {p.name: p for p in action.parameters}

        # a is required (no default)
        assert params["a"].required is True
        assert params["a"].default.present is False

        # b has default=1 (positional-only)
        assert params["b"].required is False
        assert params["b"].default.present is True
        assert params["b"].default.literal == 1
        assert params["b"].kind == ParamKind.POSITIONAL_ONLY

        # c has default=2 (regular)
        assert params["c"].required is False
        assert params["c"].default.literal == 2
        assert params["c"].kind == ParamKind.POSITIONAL_OR_KEYWORD

        # d has default=3 (regular)
        assert params["d"].required is False
        assert params["d"].default.literal == 3

    def test_mixed_params(self, tmp_path: Path):
        """Test mixed positional-only, regular, kw-only, varargs."""
        code = '''
def func(x, y=10, /, z=20, *args, kw_only=30, **kwargs):
    pass
'''
        (tmp_path / "test.py").write_text(code)
        result = analyze_project(tmp_path / "test.py")

        action = result.modules[0].actions[0]
        params = {p.name: p for p in action.parameters}

        assert params["x"].required is True
        assert params["x"].kind == ParamKind.POSITIONAL_ONLY

        assert params["y"].required is False
        assert params["y"].default.literal == 10
        assert params["y"].kind == ParamKind.POSITIONAL_ONLY

        assert params["z"].required is False
        assert params["z"].default.literal == 20
        assert params["z"].kind == ParamKind.POSITIONAL_OR_KEYWORD

        assert params["args"].kind == ParamKind.VAR_POSITIONAL

        assert params["kw_only"].required is False
        assert params["kw_only"].default.literal == 30
        assert params["kw_only"].kind == ParamKind.KEYWORD_ONLY

        assert params["kwargs"].kind == ParamKind.VAR_KEYWORD


class TestCLIDecoratorPrecedence:
    """Test CLI decorator detection takes precedence over entrypoint names."""

    def test_click_main_keeps_click_plan(self, tmp_path: Path):
        """A click-decorated function named 'main' should keep CLICK_COMMAND plan."""
        code = '''
import click

@click.command()
def main():
    """CLI main function."""
    pass
'''
        (tmp_path / "test.py").write_text(code)
        result = analyze_project(tmp_path / "test.py")

        action = result.modules[0].actions[0]
        assert action.name == "main"
        assert action.kind == ActionKind.CLI_COMMAND
        assert action.invocation_plan == InvocationPlan.CLICK_COMMAND

    def test_typer_run_keeps_typer_plan(self, tmp_path: Path):
        """A typer-decorated function named 'run' should keep TYPER_COMMAND plan."""
        code = '''
import typer

@typer.command()
def run():
    """CLI run function."""
    pass
'''
        (tmp_path / "test.py").write_text(code)
        result = analyze_project(tmp_path / "test.py")

        action = result.modules[0].actions[0]
        assert action.name == "run"
        assert action.kind == ActionKind.CLI_COMMAND
        assert action.invocation_plan == InvocationPlan.TYPER_COMMAND

    def test_bare_command_decorator_uses_generic(self, tmp_path: Path):
        """Bare @command decorator should use CLI_GENERIC (unknown framework)."""
        code = '''
from click import command

@command
def cli():
    pass
'''
        (tmp_path / "test.py").write_text(code)
        result = analyze_project(tmp_path / "test.py")

        action = result.modules[0].actions[0]
        assert action.kind == ActionKind.CLI_COMMAND
        assert action.invocation_plan == InvocationPlan.CLI_GENERIC


class TestArgparseDetection:
    """Test argparse detection for any function name."""

    def test_argparse_in_non_entrypoint_name(self, tmp_path: Path):
        """argparse usage should be detected even for non-entrypoint function names."""
        code = '''
import argparse

def process_files():
    parser = argparse.ArgumentParser()
    parser.add_argument("files")
    args = parser.parse_args()
'''
        (tmp_path / "test.py").write_text(code)
        result = analyze_project(tmp_path / "test.py")

        action = result.modules[0].actions[0]
        assert action.name == "process_files"
        assert action.kind == ActionKind.ENTRYPOINT
        assert action.invocation_plan == InvocationPlan.CLI_GENERIC

    def test_entrypoint_name_without_argparse(self, tmp_path: Path):
        """Entrypoint name without argparse should be ENTRYPOINT with DIRECT_CALL."""
        code = '''
def main(config: dict):
    """Regular main function."""
    return config
'''
        (tmp_path / "test.py").write_text(code)
        result = analyze_project(tmp_path / "test.py")

        action = result.modules[0].actions[0]
        assert action.name == "main"
        assert action.kind == ActionKind.ENTRYPOINT
        assert action.invocation_plan == InvocationPlan.DIRECT_CALL


class TestAllExportsFiltering:
    """Test __all__ filtering with class methods."""

    def test_all_keeps_class_methods_when_class_exported(self, tmp_path: Path):
        """Class methods should be included when their parent class is in __all__."""
        code = '''
__all__ = ["ExportedClass"]

class ExportedClass:
    @staticmethod
    def static_method():
        pass

    @classmethod
    def class_method(cls):
        pass

class HiddenClass:
    @staticmethod
    def hidden_static():
        pass
'''
        (tmp_path / "test.py").write_text(code)
        result = analyze_project(tmp_path / "test.py")

        action_names = [a.name for a in result.modules[0].actions]
        assert "static_method" in action_names
        assert "class_method" in action_names
        assert "hidden_static" not in action_names

    def test_all_class_method_not_matched_by_same_name_function(self, tmp_path: Path):
        """Class method shouldn't be included just because __all__ has same name."""
        code = '''
__all__ = ["static_method"]  # Function name, not class name

def static_method():
    """This function is exported."""
    pass

class NotExported:
    @staticmethod
    def static_method():
        """This class method should NOT be exported."""
        pass
'''
        (tmp_path / "test.py").write_text(code)
        result = analyze_project(tmp_path / "test.py")

        # Should only have the function, not the class method
        actions = result.modules[0].actions
        assert len(actions) == 1
        assert actions[0].name == "static_method"
        assert actions[0].kind == ActionKind.FUNCTION


class TestIgnorePatterns:
    """Test wildcard ignore patterns."""

    def test_egg_info_directory_ignored(self, tmp_path: Path):
        """*.egg-info directories should be ignored."""
        egg_dir = tmp_path / "mypackage.egg-info"
        egg_dir.mkdir()
        (egg_dir / "info.py").write_text("def should_be_ignored(): pass")
        (tmp_path / "main.py").write_text("def should_be_included(): pass")

        result = analyze_project(tmp_path)

        module_names = [m.display_name for m in result.modules]
        assert "main" in module_names
        assert "info" not in module_names

    def test_test_prefix_files_ignored(self, tmp_path: Path):
        """test_*.py files should be ignored during directory scan."""
        (tmp_path / "test_utils.py").write_text("def test_something(): pass")
        (tmp_path / "main.py").write_text("def main(): pass")

        result = analyze_project(tmp_path)

        module_names = [m.display_name for m in result.modules]
        assert "main" in module_names
        assert "test_utils" not in module_names

    def test_explicit_file_not_ignored(self, tmp_path: Path):
        """Explicitly specified files should NOT be ignored."""
        test_file = tmp_path / "test_explicit.py"
        test_file.write_text("def test_func(): pass")

        # When explicitly pointing to the file, it should be analyzed
        result = analyze_project(test_file)

        assert len(result.modules) == 1
        assert result.modules[0].actions[0].name == "test_func"


class TestActionIDStability:
    """Test action IDs are based on signature, not line numbers."""

    def test_action_id_stable_across_line_changes(self, tmp_path: Path):
        """Action ID should be the same regardless of line number."""
        code1 = '''
def func(a: int, b: str = "default") -> bool:
    pass
'''
        code2 = '''
# Added comment


def func(a: int, b: str = "default") -> bool:
    pass
'''
        (tmp_path / "test.py").write_text(code1)
        result1 = analyze_project(tmp_path / "test.py")
        id1 = result1.modules[0].actions[0].action_id

        (tmp_path / "test.py").write_text(code2)
        result2 = analyze_project(tmp_path / "test.py")
        id2 = result2.modules[0].actions[0].action_id

        assert id1 == id2

    def test_action_id_changes_with_signature(self, tmp_path: Path):
        """Action ID should change when signature changes."""
        code1 = "def func(a: int): pass"
        code2 = "def func(a: int, b: str): pass"

        (tmp_path / "test.py").write_text(code1)
        result1 = analyze_project(tmp_path / "test.py")
        id1 = result1.modules[0].actions[0].action_id

        (tmp_path / "test.py").write_text(code2)
        result2 = analyze_project(tmp_path / "test.py")
        id2 = result2.modules[0].actions[0].action_id

        assert id1 != id2

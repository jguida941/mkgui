"""Comprehensive tests for the generator module."""

import json
from pathlib import Path

import pytest

from py2gui.generator import (
    GeneratorConfig,
    GeneratorResult,
    ScaffoldMode,
    SourceMode,
    _compute_spec_hash,
    _copy_source_files,
    _write_launcher,
    _write_overrides_template,
    _write_spec_json,
    generate_project,
)
from py2gui.models import (
    ActionKind,
    ActionSpec,
    AnalysisResult,
    Annotation,
    DefaultValue,
    DocSpec,
    InvocationPlan,
    ModuleSpec,
    ParamKind,
    ParamSpec,
    ParamUI,
    ParamValidation,
    WidgetType,
)


class TestGeneratorConfig:
    """Tests for GeneratorConfig dataclass."""

    def test_default_values(self, tmp_path):
        """Should have sensible defaults."""
        config = GeneratorConfig(
            output_dir=tmp_path / "output",
            source_path=tmp_path / "src",
        )
        assert config.scaffold_mode == ScaffoldMode.THIN
        assert config.source_mode == SourceMode.IMPORT
        assert config.create_overrides is True
        assert config.runtime_package == "py2gui_runtime"

    def test_custom_values(self, tmp_path):
        """Should accept custom values."""
        config = GeneratorConfig(
            output_dir=tmp_path / "out",
            source_path=tmp_path / "src",
            scaffold_mode=ScaffoldMode.STANDALONE,
            source_mode=SourceMode.COPY,
            create_overrides=False,
            runtime_package="custom_runtime",
        )
        assert config.scaffold_mode == ScaffoldMode.STANDALONE
        assert config.source_mode == SourceMode.COPY
        assert config.create_overrides is False
        assert config.runtime_package == "custom_runtime"


class TestGeneratorResult:
    """Tests for GeneratorResult dataclass."""

    def test_success_property_no_errors(self, tmp_path):
        """Should be successful when no errors."""
        result = GeneratorResult(
            output_dir=tmp_path,
            spec_path=tmp_path / "spec.json",
            launcher_path=tmp_path / "main.py",
        )
        assert result.success is True

    def test_success_property_with_errors(self, tmp_path):
        """Should not be successful when errors exist."""
        result = GeneratorResult(
            output_dir=tmp_path,
            spec_path=tmp_path / "spec.json",
            launcher_path=tmp_path / "main.py",
            errors=["Something went wrong"],
        )
        assert result.success is False


class TestWriteSpecJson:
    """Tests for _write_spec_json function."""

    def test_writes_valid_json(self, tmp_path):
        """Should write valid JSON file."""
        analysis = AnalysisResult(project_root="/test")
        spec_path = tmp_path / "spec.json"

        _write_spec_json(analysis, spec_path)

        assert spec_path.exists()
        data = json.loads(spec_path.read_text())
        assert "spec_version" in data
        assert "modules" in data

    def test_includes_spec_hash(self, tmp_path):
        """Should include spec_source_hash."""
        analysis = AnalysisResult(project_root="/test")
        spec_path = tmp_path / "spec.json"

        _write_spec_json(analysis, spec_path)

        data = json.loads(spec_path.read_text())
        assert "spec_source_hash" in data
        assert len(data["spec_source_hash"]) == 16  # Truncated SHA256

    def test_trailing_newline(self, tmp_path):
        """Should end with newline."""
        analysis = AnalysisResult(project_root="/test")
        spec_path = tmp_path / "spec.json"

        _write_spec_json(analysis, spec_path)

        content = spec_path.read_text()
        assert content.endswith("\n")

    def test_serializes_modules_and_actions(self, tmp_path):
        """Should serialize modules and actions correctly."""
        action = ActionSpec(
            action_id="mod.func:abc123",
            kind=ActionKind.FUNCTION,
            qualname="mod.func",
            name="func",
            module_import_path="mod",
            doc=DocSpec(text="Test docstring"),
            parameters=[
                ParamSpec(
                    name="x",
                    kind=ParamKind.POSITIONAL_OR_KEYWORD,
                    annotation=Annotation(raw="int"),
                )
            ],
        )
        module = ModuleSpec(
            module_id="mod",
            display_name="mod",
            actions=[action],
        )
        analysis = AnalysisResult(
            project_root="/test",
            modules=[module],
        )
        spec_path = tmp_path / "spec.json"

        _write_spec_json(analysis, spec_path)

        data = json.loads(spec_path.read_text())
        assert len(data["modules"]) == 1
        assert data["modules"][0]["module_id"] == "mod"
        assert len(data["modules"][0]["actions"]) == 1
        assert data["modules"][0]["actions"][0]["name"] == "func"


class TestComputeSpecHash:
    """Tests for _compute_spec_hash function."""

    def test_consistent_hash(self):
        """Same input should produce same hash."""
        spec = {"modules": [], "project_root": "/test"}
        hash1 = _compute_spec_hash(spec)
        hash2 = _compute_spec_hash(spec)
        assert hash1 == hash2

    def test_different_content_different_hash(self):
        """Different input should produce different hash."""
        spec1 = {"modules": [], "project_root": "/test1"}
        spec2 = {"modules": [], "project_root": "/test2"}
        hash1 = _compute_spec_hash(spec1)
        hash2 = _compute_spec_hash(spec2)
        assert hash1 != hash2

    def test_ignores_created_at(self):
        """Should ignore created_at for hashing."""
        spec1 = {"modules": [], "created_at": "2024-01-01T00:00:00"}
        spec2 = {"modules": [], "created_at": "2024-12-31T23:59:59"}
        hash1 = _compute_spec_hash(spec1)
        hash2 = _compute_spec_hash(spec2)
        assert hash1 == hash2

    def test_returns_16_chars(self):
        """Should return 16-character hash."""
        spec = {"modules": []}
        result = _compute_spec_hash(spec)
        assert len(result) == 16


class TestWriteLauncher:
    """Tests for _write_launcher function."""

    def test_creates_executable_file(self, tmp_path):
        """Should create executable Python file."""
        analysis = AnalysisResult(project_root="/test")
        config = GeneratorConfig(
            output_dir=tmp_path,
            source_path=tmp_path / "src",
        )
        launcher_path = tmp_path / "main.py"

        _write_launcher(analysis, config, launcher_path)

        assert launcher_path.exists()
        # Check executable bit on Unix
        assert launcher_path.stat().st_mode & 0o111

    def test_contains_shebang(self, tmp_path):
        """Should start with shebang."""
        analysis = AnalysisResult(project_root="/test")
        config = GeneratorConfig(
            output_dir=tmp_path,
            source_path=tmp_path / "src",
        )
        launcher_path = tmp_path / "main.py"

        _write_launcher(analysis, config, launcher_path)

        content = launcher_path.read_text()
        assert content.startswith("#!/usr/bin/env python3")

    def test_contains_main_function(self, tmp_path):
        """Should contain main function."""
        analysis = AnalysisResult(project_root="/test")
        config = GeneratorConfig(
            output_dir=tmp_path,
            source_path=tmp_path / "src",
        )
        launcher_path = tmp_path / "main.py"

        _write_launcher(analysis, config, launcher_path)

        content = launcher_path.read_text()
        assert "def main():" in content
        assert 'if __name__ == "__main__":' in content

    def test_import_mode_includes_source_path(self, tmp_path):
        """Should include source path in import mode."""
        source_path = tmp_path / "my_project"
        source_path.mkdir()
        analysis = AnalysisResult(project_root=str(source_path))
        config = GeneratorConfig(
            output_dir=tmp_path / "output",
            source_path=source_path,
            source_mode=SourceMode.IMPORT,
        )
        launcher_path = tmp_path / "output" / "main.py"
        launcher_path.parent.mkdir(parents=True, exist_ok=True)

        _write_launcher(analysis, config, launcher_path)

        content = launcher_path.read_text()
        assert "my_project" in content

    def test_copy_mode_uses_original_src(self, tmp_path):
        """Should reference original_src in copy mode."""
        analysis = AnalysisResult(project_root="/test")
        config = GeneratorConfig(
            output_dir=tmp_path,
            source_path=tmp_path / "src",
            source_mode=SourceMode.COPY,
        )
        launcher_path = tmp_path / "main.py"

        _write_launcher(analysis, config, launcher_path)

        content = launcher_path.read_text()
        assert "original_src" in content

    def test_includes_runtime_package(self, tmp_path):
        """Should include runtime package import."""
        analysis = AnalysisResult(project_root="/test")
        config = GeneratorConfig(
            output_dir=tmp_path,
            source_path=tmp_path / "src",
            runtime_package="my_runtime",
        )
        launcher_path = tmp_path / "main.py"

        _write_launcher(analysis, config, launcher_path)

        content = launcher_path.read_text()
        assert "from my_runtime import run_app" in content

    def test_path_escaping_for_special_chars(self, tmp_path):
        """Should properly escape paths with special characters.

        This tests the fix for Windows paths containing sequences like
        \\Users (which would be interpreted as \\U unicode escape).
        """
        # Create a directory with a name that would cause issues if not escaped
        # Simulating C:\\Users\\test which contains \\U
        source_path = tmp_path / "Users" / "test_project"
        source_path.mkdir(parents=True)
        analysis = AnalysisResult(project_root=str(source_path))
        config = GeneratorConfig(
            output_dir=tmp_path / "output",
            source_path=source_path,
            source_mode=SourceMode.IMPORT,
        )
        launcher_path = tmp_path / "output" / "main.py"
        launcher_path.parent.mkdir(parents=True, exist_ok=True)

        _write_launcher(analysis, config, launcher_path)

        content = launcher_path.read_text()
        # The path should be properly escaped (using repr())
        # This ensures the generated code is valid Python syntax
        # Compile the generated code to verify it's syntactically valid
        compile(content, launcher_path, "exec")


class TestWriteOverridesTemplate:
    """Tests for _write_overrides_template function."""

    def test_creates_yaml_file(self, tmp_path):
        """Should create YAML file."""
        analysis = AnalysisResult(project_root="/test")
        overrides_path = tmp_path / "overrides.yml"

        _write_overrides_template(analysis, overrides_path)

        assert overrides_path.exists()
        content = overrides_path.read_text()
        assert content.startswith("#")  # Comments

    def test_includes_schema_version(self, tmp_path):
        """Should include override schema version."""
        analysis = AnalysisResult(project_root="/test")
        overrides_path = tmp_path / "overrides.yml"

        _write_overrides_template(analysis, overrides_path)

        content = overrides_path.read_text()
        assert 'override_schema_version: "1.0"' in content

    def test_includes_module_examples(self, tmp_path):
        """Should include module override examples."""
        module = ModuleSpec(
            module_id="mymodule",
            display_name="My Module",
            actions=[],
        )
        analysis = AnalysisResult(
            project_root="/test",
            modules=[module],
        )
        overrides_path = tmp_path / "overrides.yml"

        _write_overrides_template(analysis, overrides_path)

        content = overrides_path.read_text()
        assert "mymodule:" in content

    def test_includes_action_examples(self, tmp_path):
        """Should include action override examples."""
        action = ActionSpec(
            action_id="mod.func:abc",
            kind=ActionKind.FUNCTION,
            qualname="mod.func",
            name="my_function",
            module_import_path="mod",
        )
        module = ModuleSpec(
            module_id="mod",
            display_name="mod",
            actions=[action],
        )
        analysis = AnalysisResult(
            project_root="/test",
            modules=[module],
        )
        overrides_path = tmp_path / "overrides.yml"

        _write_overrides_template(analysis, overrides_path)

        content = overrides_path.read_text()
        assert "my_function:" in content

    def test_includes_parameter_examples(self, tmp_path):
        """Should include parameter override examples."""
        param = ParamSpec(
            name="count",
            ui=ParamUI(widget=WidgetType.SPIN_BOX),
            validation=ParamValidation(min=0, max=100),
        )
        action = ActionSpec(
            action_id="mod.func:abc",
            kind=ActionKind.FUNCTION,
            qualname="mod.func",
            name="func",
            module_import_path="mod",
            parameters=[param],
        )
        module = ModuleSpec(
            module_id="mod",
            display_name="mod",
            actions=[action],
        )
        analysis = AnalysisResult(
            project_root="/test",
            modules=[module],
        )
        overrides_path = tmp_path / "overrides.yml"

        _write_overrides_template(analysis, overrides_path)

        content = overrides_path.read_text()
        assert "count:" in content
        assert "spin_box" in content
        assert "min: 0" in content
        assert "max: 100" in content


class TestCopySourceFiles:
    """Tests for _copy_source_files function."""

    def test_copies_single_file(self, tmp_path):
        """Should copy single file."""
        src_file = tmp_path / "source.py"
        src_file.write_text("print('hello')")
        dest_dir = tmp_path / "dest"

        copied = _copy_source_files(src_file, dest_dir)

        assert len(copied) == 1
        assert (dest_dir / "source.py").exists()
        assert (dest_dir / "source.py").read_text() == "print('hello')"

    def test_copies_directory(self, tmp_path):
        """Should copy directory contents."""
        src_dir = tmp_path / "source"
        src_dir.mkdir()
        (src_dir / "module.py").write_text("# module")
        sub_dir = src_dir / "subpackage"
        sub_dir.mkdir()
        (sub_dir / "__init__.py").write_text("# init")

        dest_dir = tmp_path / "dest"

        copied = _copy_source_files(src_dir, dest_dir)

        assert len(copied) == 2
        assert (dest_dir / "module.py").exists()
        assert (dest_dir / "subpackage" / "__init__.py").exists()

    def test_excludes_pycache(self, tmp_path):
        """Should exclude __pycache__ directories."""
        src_dir = tmp_path / "source"
        src_dir.mkdir()
        (src_dir / "module.py").write_text("# module")
        pycache = src_dir / "__pycache__"
        pycache.mkdir()
        (pycache / "module.cpython-39.pyc").write_bytes(b"bytecode")

        dest_dir = tmp_path / "dest"

        copied = _copy_source_files(src_dir, dest_dir)

        assert len(copied) == 1
        assert not (dest_dir / "__pycache__").exists()

    def test_excludes_venv(self, tmp_path):
        """Should exclude venv directories."""
        src_dir = tmp_path / "source"
        src_dir.mkdir()
        (src_dir / "module.py").write_text("# module")
        venv = src_dir / "venv"
        venv.mkdir()
        (venv / "pyvenv.cfg").write_text("home = /usr/bin")

        dest_dir = tmp_path / "dest"

        copied = _copy_source_files(src_dir, dest_dir)

        assert len(copied) == 1
        assert not (dest_dir / "venv").exists()

    def test_excludes_git(self, tmp_path):
        """Should exclude .git directory."""
        src_dir = tmp_path / "source"
        src_dir.mkdir()
        (src_dir / "module.py").write_text("# module")
        git = src_dir / ".git"
        git.mkdir()
        (git / "config").write_text("[core]")

        dest_dir = tmp_path / "dest"

        copied = _copy_source_files(src_dir, dest_dir)

        assert len(copied) == 1
        assert not (dest_dir / ".git").exists()

    def test_excludes_egg_info(self, tmp_path):
        """Should exclude .egg-info directories."""
        src_dir = tmp_path / "source"
        src_dir.mkdir()
        (src_dir / "module.py").write_text("# module")
        egg = src_dir / "mypackage.egg-info"
        egg.mkdir()
        (egg / "PKG-INFO").write_text("Name: mypackage")

        dest_dir = tmp_path / "dest"

        copied = _copy_source_files(src_dir, dest_dir)

        assert len(copied) == 1
        assert not (dest_dir / "mypackage.egg-info").exists()

    def test_returns_relative_paths(self, tmp_path):
        """Should return paths relative to dest dir."""
        src_dir = tmp_path / "source"
        src_dir.mkdir()
        sub = src_dir / "pkg"
        sub.mkdir()
        (sub / "mod.py").write_text("# mod")

        dest_dir = tmp_path / "dest"

        copied = _copy_source_files(src_dir, dest_dir)

        assert copied[0] == Path("pkg/mod.py")

    def test_excludes_tests_directory(self, tmp_path):
        """Should exclude tests directory (aligned with analyzer)."""
        src_dir = tmp_path / "source"
        src_dir.mkdir()
        (src_dir / "module.py").write_text("# module")
        tests = src_dir / "tests"
        tests.mkdir()
        (tests / "test_module.py").write_text("# test")

        dest_dir = tmp_path / "dest"

        copied = _copy_source_files(src_dir, dest_dir)

        assert len(copied) == 1
        assert not (dest_dir / "tests").exists()

    def test_excludes_test_files(self, tmp_path):
        """Should exclude test_*.py files (aligned with analyzer)."""
        src_dir = tmp_path / "source"
        src_dir.mkdir()
        (src_dir / "module.py").write_text("# module")
        (src_dir / "test_module.py").write_text("# test")
        (src_dir / "module_test.py").write_text("# test")

        dest_dir = tmp_path / "dest"

        copied = _copy_source_files(src_dir, dest_dir)

        assert len(copied) == 1
        assert (dest_dir / "module.py").exists()
        assert not (dest_dir / "test_module.py").exists()
        assert not (dest_dir / "module_test.py").exists()

    def test_excludes_conftest(self, tmp_path):
        """Should exclude conftest.py files."""
        src_dir = tmp_path / "source"
        src_dir.mkdir()
        (src_dir / "module.py").write_text("# module")
        (src_dir / "conftest.py").write_text("# conftest")

        dest_dir = tmp_path / "dest"

        copied = _copy_source_files(src_dir, dest_dir)

        assert len(copied) == 1
        assert not (dest_dir / "conftest.py").exists()


class TestGenerateProject:
    """Tests for generate_project function."""

    def test_creates_output_directory(self, tmp_path):
        """Should create output directory."""
        output_dir = tmp_path / "new_dir" / "nested"
        analysis = AnalysisResult(project_root="/test")
        config = GeneratorConfig(
            output_dir=output_dir,
            source_path=tmp_path,
        )

        generate_project(analysis, config)

        assert output_dir.exists()

    def test_creates_spec_json(self, tmp_path):
        """Should create spec.json."""
        analysis = AnalysisResult(project_root="/test")
        config = GeneratorConfig(
            output_dir=tmp_path / "output",
            source_path=tmp_path,
        )

        result = generate_project(analysis, config)

        assert result.spec_path.exists()
        assert result.spec_path.name == "spec.json"

    def test_creates_main_py(self, tmp_path):
        """Should create main.py."""
        analysis = AnalysisResult(project_root="/test")
        config = GeneratorConfig(
            output_dir=tmp_path / "output",
            source_path=tmp_path,
        )

        result = generate_project(analysis, config)

        assert result.launcher_path.exists()
        assert result.launcher_path.name == "main.py"

    def test_creates_overrides_yml(self, tmp_path):
        """Should create overrides.yml when enabled."""
        analysis = AnalysisResult(project_root="/test")
        config = GeneratorConfig(
            output_dir=tmp_path / "output",
            source_path=tmp_path,
            create_overrides=True,
        )

        result = generate_project(analysis, config)

        assert result.overrides_path is not None
        assert result.overrides_path.exists()
        assert result.overrides_path.name == "overrides.yml"

    def test_skips_overrides_when_disabled(self, tmp_path):
        """Should not create overrides.yml when disabled."""
        analysis = AnalysisResult(project_root="/test")
        config = GeneratorConfig(
            output_dir=tmp_path / "output",
            source_path=tmp_path,
            create_overrides=False,
        )

        result = generate_project(analysis, config)

        assert result.overrides_path is None

    def test_copies_source_in_copy_mode(self, tmp_path):
        """Should copy source files in copy mode."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "module.py").write_text("# code")

        analysis = AnalysisResult(project_root=str(src))
        config = GeneratorConfig(
            output_dir=tmp_path / "output",
            source_path=src,
            source_mode=SourceMode.COPY,
        )

        result = generate_project(analysis, config)

        assert len(result.copied_sources) > 0
        assert (tmp_path / "output" / "original_src" / "module.py").exists()

    def test_no_copy_in_import_mode(self, tmp_path):
        """Should not copy files in import mode."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "module.py").write_text("# code")

        analysis = AnalysisResult(project_root=str(src))
        config = GeneratorConfig(
            output_dir=tmp_path / "output",
            source_path=src,
            source_mode=SourceMode.IMPORT,
        )

        result = generate_project(analysis, config)

        assert len(result.copied_sources) == 0
        assert not (tmp_path / "output" / "original_src").exists()

    def test_success_is_true_on_success(self, tmp_path):
        """Should have success=True when no errors."""
        analysis = AnalysisResult(project_root="/test")
        config = GeneratorConfig(
            output_dir=tmp_path / "output",
            source_path=tmp_path,
        )

        result = generate_project(analysis, config)

        assert result.success is True
        assert len(result.errors) == 0


class TestGenerateProjectIntegration:
    """Integration tests for full generation workflow."""

    def test_full_workflow_thin_mode(self, tmp_path):
        """Test complete thin mode generation."""
        # Create a sample source
        src = tmp_path / "sample"
        src.mkdir()
        (src / "calculator.py").write_text('''
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

def multiply(x: float, y: float) -> float:
    """Multiply two numbers."""
    return x * y
''')

        # Build analysis result
        action1 = ActionSpec(
            action_id="calculator.add:abc",
            kind=ActionKind.FUNCTION,
            qualname="calculator.add",
            name="add",
            module_import_path="calculator",
            doc=DocSpec(text="Add two numbers."),
            parameters=[
                ParamSpec(name="a", annotation=Annotation(raw="int")),
                ParamSpec(name="b", annotation=Annotation(raw="int")),
            ],
        )
        action2 = ActionSpec(
            action_id="calculator.multiply:def",
            kind=ActionKind.FUNCTION,
            qualname="calculator.multiply",
            name="multiply",
            module_import_path="calculator",
        )
        module = ModuleSpec(
            module_id="calculator",
            display_name="calculator",
            file_path=str(src / "calculator.py"),
            actions=[action1, action2],
        )
        analysis = AnalysisResult(
            project_root=str(src),
            modules=[module],
        )

        # Generate
        config = GeneratorConfig(
            output_dir=tmp_path / "output",
            source_path=src,
            scaffold_mode=ScaffoldMode.THIN,
            source_mode=SourceMode.IMPORT,
        )

        result = generate_project(analysis, config)

        # Verify
        assert result.success
        assert result.spec_path.exists()
        assert result.launcher_path.exists()
        assert result.overrides_path.exists()

        # Verify spec.json content
        spec_data = json.loads(result.spec_path.read_text())
        assert spec_data["spec_version"] == "1.0"
        assert len(spec_data["modules"]) == 1
        assert len(spec_data["modules"][0]["actions"]) == 2

    def test_full_workflow_copy_mode(self, tmp_path):
        """Test complete copy mode generation."""
        # Create source
        src = tmp_path / "mylib"
        src.mkdir()
        (src / "__init__.py").write_text("# init")
        (src / "core.py").write_text("def main(): pass")

        analysis = AnalysisResult(
            project_root=str(src),
            modules=[
                ModuleSpec(
                    module_id="mylib.core",
                    display_name="core",
                    actions=[],
                )
            ],
        )

        config = GeneratorConfig(
            output_dir=tmp_path / "output",
            source_path=src,
            source_mode=SourceMode.COPY,
        )

        result = generate_project(analysis, config)

        assert result.success
        assert len(result.copied_sources) == 2
        assert (tmp_path / "output" / "original_src" / "__init__.py").exists()
        assert (tmp_path / "output" / "original_src" / "core.py").exists()

        # Launcher should reference original_src
        launcher_content = result.launcher_path.read_text()
        assert "original_src" in launcher_content

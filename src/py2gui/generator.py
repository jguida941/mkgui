"""Generator for spec.json and thin launcher output.

This module generates the output artifacts from an AnalysisResult:
- spec.json: The full analysis result for the runtime UI engine
- main.py: A thin launcher that loads spec.json and starts the GUI
- overrides.yml: Optional UI/config overrides template
- Source copying: Vendor mode copies source files to output
"""

import fnmatch
import hashlib
import json
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .analyzer import IGNORE_DIR_PATTERNS, IGNORE_FILE_PATTERNS
from .models import AnalysisResult


class ScaffoldMode(str, Enum):
    """Output scaffold modes."""
    THIN = "thin"
    STANDALONE = "standalone"


class SourceMode(str, Enum):
    """How to handle source files."""
    IMPORT = "import"  # Import from original location
    COPY = "copy"      # Copy/vendor source into output


@dataclass
class GeneratorConfig:
    """Configuration for the generator."""
    output_dir: Path
    source_path: Path
    scaffold_mode: ScaffoldMode = ScaffoldMode.THIN
    source_mode: SourceMode = SourceMode.IMPORT
    create_overrides: bool = True
    runtime_package: str = "py2gui_runtime"


@dataclass
class GeneratorResult:
    """Result of generation."""
    output_dir: Path
    spec_path: Path
    launcher_path: Path
    overrides_path: Path | None = None
    copied_sources: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """Whether generation completed without errors."""
        return len(self.errors) == 0


def generate_project(
    analysis: AnalysisResult,
    config: GeneratorConfig,
) -> GeneratorResult:
    """Generate a GUI project from analysis results.

    Args:
        analysis: The analysis result from analyze_project()
        config: Generator configuration

    Returns:
        GeneratorResult with paths to generated files
    """
    output_dir = config.output_dir
    errors: list[str] = []
    copied_sources: list[Path] = []

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate spec.json
    spec_path = output_dir / "spec.json"
    try:
        _write_spec_json(analysis, spec_path)
    except Exception as e:
        errors.append(f"Failed to write spec.json: {e}")

    # Generate main.py launcher
    launcher_path = output_dir / "main.py"
    try:
        _write_launcher(analysis, config, launcher_path)
    except Exception as e:
        errors.append(f"Failed to write main.py: {e}")

    # Generate overrides.yml template
    overrides_path = None
    if config.create_overrides:
        overrides_path = output_dir / "overrides.yml"
        try:
            _write_overrides_template(analysis, overrides_path)
        except Exception as e:
            errors.append(f"Failed to write overrides.yml: {e}")

    # Copy source files if vendor mode
    if config.source_mode == SourceMode.COPY:
        try:
            copied_sources = _copy_source_files(
                config.source_path,
                output_dir / "original_src",
            )
        except Exception as e:
            errors.append(f"Failed to copy source files: {e}")

    return GeneratorResult(
        output_dir=output_dir,
        spec_path=spec_path,
        launcher_path=launcher_path,
        overrides_path=overrides_path,
        copied_sources=copied_sources,
        errors=errors,
    )


def _write_spec_json(analysis: AnalysisResult, path: Path) -> None:
    """Write the analysis result as spec.json."""
    spec_dict = analysis.to_dict()

    # Add spec source hash for deterministic regen checks
    spec_dict["spec_source_hash"] = _compute_spec_hash(spec_dict)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(spec_dict, f, indent=2, ensure_ascii=False)
        f.write("\n")  # Trailing newline


def _compute_spec_hash(spec_dict: dict[str, Any]) -> str:
    """Compute a hash of the spec for change detection."""
    # Remove volatile fields before hashing
    hash_dict = {k: v for k, v in spec_dict.items() if k not in ("created_at", "spec_source_hash")}
    content = json.dumps(hash_dict, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _write_launcher(
    analysis: AnalysisResult,
    config: GeneratorConfig,
    path: Path,
) -> None:
    """Write the thin main.py launcher."""
    # Determine import paths
    if config.source_mode == SourceMode.COPY:
        source_path_comment = "# Source: vendored in ./original_src/"
        sys_path_setup = '''
import sys
from pathlib import Path

# Add vendored source to path
_src_dir = Path(__file__).parent / "original_src"
if _src_dir.exists():
    sys.path.insert(0, str(_src_dir))
'''
    else:
        source_path_comment = f"# Source: {config.source_path.absolute()}"
        source_abs = config.source_path.absolute()
        if source_abs.is_file():
            source_dir = source_abs.parent
        else:
            source_dir = source_abs
        # Use repr() for safe path escaping on all platforms (handles \U, \t, etc.)
        source_dir_repr = repr(str(source_dir))
        sys_path_setup = f'''
import sys
from pathlib import Path

# Add original source to path
_src_dir = Path({source_dir_repr})
if _src_dir.exists():
    sys.path.insert(0, str(_src_dir))
'''

    launcher_content = f'''#!/usr/bin/env python3
"""PyQt6 GUI wrapper launcher.

Generated by pyqt6-wrap {analysis.generator_version}
{source_path_comment}
"""
{sys_path_setup}
import json

# Load spec.json
_spec_path = Path(__file__).parent / "spec.json"
with open(_spec_path, "r", encoding="utf-8") as f:
    SPEC = json.load(f)


def main():
    """Launch the GUI application."""
    try:
        from {config.runtime_package} import run_app
        run_app(SPEC)
    except ImportError:
        print("Error: Runtime package '{config.runtime_package}' not installed.")
        print("Install with: pip install {config.runtime_package}")
        print()
        print("Spec loaded successfully. Actions detected:")
        for module in SPEC.get("modules", []):
            print(f"  Module: {{module.get('display_name', module.get('module_id'))}}")
            for action in module.get("actions", []):
                print(f"    - {{action.get('name')}} ({{action.get('kind')}})")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

    with open(path, "w", encoding="utf-8") as f:
        f.write(launcher_content)

    # Make executable on Unix
    path.chmod(path.stat().st_mode | 0o111)


def _write_overrides_template(analysis: AnalysisResult, path: Path) -> None:
    """Write the overrides.yml template."""
    # Build template with comments showing available options
    lines = [
        "# UI and configuration overrides for pyqt6-wrap",
        "# Uncomment and modify sections as needed",
        "#",
        f"# Generated for project: {analysis.project_root}",
        f"# Spec version: {analysis.spec_version}",
        "",
        "# Override schema version (for compatibility checking)",
        "override_schema_version: \"1.0\"",
        "",
        "# Global UI settings",
        "# ui:",
        "#   theme: dark  # light or dark",
        "#   window_title: \"My Application\"",
        "#   window_size: [1024, 768]",
        "",
        "# Module display overrides",
        "# modules:",
    ]

    # Add example overrides for each module
    for module in analysis.modules:
        lines.append(f"#   {module.module_id}:")
        lines.append(f"#     display_name: \"{module.display_name}\"")
        lines.append("#     hidden: false")
        lines.append("#     actions:")

        for action in module.actions:
            lines.append(f"#       {action.name}:")
            lines.append("#         hidden: false")
            lines.append("#         display_name: null  # Override display name")

            if action.parameters:
                lines.append("#         parameters:")
                for param in action.parameters:
                    lines.append(f"#           {param.name}:")
                    lines.append(f"#             widget: {param.ui.widget.value}")
                    if param.validation.min is not None:
                        lines.append(f"#             min: {param.validation.min}")
                    if param.validation.max is not None:
                        lines.append(f"#             max: {param.validation.max}")
        lines.append("")

    lines.extend([
        "# Type widget overrides (global)",
        "# type_widgets:",
        "#   int: spin_box",
        "#   float: double_spin_box",
        "#   str: line_edit",
        "#   bool: check_box",
        "#   Path: file_picker",
        "",
        "# Execution settings",
        "# execution:",
        "#   runner: subprocess  # subprocess or in_process",
        "#   timeout: 300  # seconds",
        "#   working_dir: null  # Use project root if null",
        "",
    ])

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _copy_source_files(source_path: Path, dest_dir: Path) -> list[Path]:
    """Copy source files to the output directory.

    Args:
        source_path: Path to source file or directory
        dest_dir: Destination directory for copied files

    Returns:
        List of copied file paths (relative to dest_dir)
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []

    if source_path.is_file():
        # Single file - copy directly
        dest_file = dest_dir / source_path.name
        shutil.copy2(source_path, dest_file)
        copied.append(Path(source_path.name))
    else:
        # Directory - copy tree, using same ignore patterns as analyzer
        # Add a few more patterns not in analyzer (version control, caches)
        extra_dir_patterns = [".hg", ".svn", ".ruff_cache"]
        all_dir_patterns = IGNORE_DIR_PATTERNS + extra_dir_patterns

        for item in source_path.rglob("*"):
            # Skip excluded directory patterns
            skip = False
            for part in item.parts:
                if any(fnmatch.fnmatch(part, pat) for pat in all_dir_patterns):
                    skip = True
                    break
            if skip:
                continue

            if item.is_file():
                # Skip files matching ignore patterns (test files, conftest, etc.)
                filename = item.name
                if any(fnmatch.fnmatch(filename, pat) for pat in IGNORE_FILE_PATTERNS):
                    continue

                rel_path = item.relative_to(source_path)
                dest_file = dest_dir / rel_path
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest_file)
                copied.append(rel_path)

    return copied

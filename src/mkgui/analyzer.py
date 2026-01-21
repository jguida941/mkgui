"""AST-only code analyzer for Python source files.

Analyzes Python code without importing it, extracting:
- Functions and their signatures
- Classes and their methods
- Entrypoints (main blocks, CLI decorators, argparse usage)
- Type annotations and defaults
"""

import ast
import json
import fnmatch
import hashlib
import subprocess
import sys
import textwrap
from pathlib import Path

try:
    import tomllib as toml
except ModuleNotFoundError:
    try:
        import tomli as toml
    except ModuleNotFoundError:
        toml = None

from . import __version__
from .inspector import inspect_parameters
from .models import (
    ActionKind,
    ActionSpec,
    AnalysisMode,
    AnalysisResult,
    Annotation,
    DefaultValue,
    DocSpec,
    InvocationPlan,
    ModuleSpec,
    ParamKind,
    ParamSpec,
    ReturnSpec,
    Warning,
)

# Directory patterns to ignore (supports wildcards via fnmatch)
IGNORE_DIR_PATTERNS = [
    "tests", "test", "__pycache__", "venv", ".venv", "env",
    "build", "dist", ".git", ".tox", ".nox", ".mypy_cache",
    ".pytest_cache", "node_modules", ".eggs", "*.egg-info",
]

# File patterns to ignore (supports wildcards via fnmatch)
IGNORE_FILE_PATTERNS = [
    "setup.py", "conftest.py", "test_*.py", "*_test.py",
]

# Treat a top-level "src" directory without __init__.py as a source root.
SOURCE_ROOT_DIRS = {"src"}

# Entrypoint function names (used only when no CLI decorator is present)
ENTRYPOINT_NAMES = {"main", "run", "cli", "start", "execute"}

# CLI framework decorators - fully qualified names only
# Bare names like @command could be anything, so they get CLI_GENERIC
CLI_CLICK_DECORATORS = {"click.command", "click.group"}
CLI_TYPER_DECORATORS = {"typer.command", "app.command", "typer.Typer"}
# Bare decorators that indicate CLI but unknown framework
CLI_BARE_DECORATORS = {"command", "group", "Typer"}

INTROSPECT_TIMEOUT_SEC = 5


def _matches_pattern(name: str, patterns: list[str]) -> bool:
    """Check if name matches any of the fnmatch patterns."""
    return any(fnmatch.fnmatch(name, pattern) for pattern in patterns)


def _is_json_serializable(value: object) -> bool:
    """Check if a value can be serialized to JSON."""
    try:
        json.dumps(value)
    except (TypeError, OverflowError):
        return False
    return True


class ASTAnalyzer:
    """Analyzes Python source files using AST only (no imports)."""

    def __init__(self, project_root: str | Path, analysis_mode: AnalysisMode = AnalysisMode.AST_ONLY):
        self.project_root = Path(project_root).resolve()
        self.analysis_mode = analysis_mode
        self.warnings: list[Warning] = []

    def analyze(self) -> AnalysisResult:
        """Analyze the project and return the AnalysisResult."""
        modules: list[ModuleSpec] = []

        if self.project_root.is_file():
            # Single file analysis
            # Note: Ignore patterns are NOT applied to explicitly specified files.
            # If a user runs `mkgui analyze tests/foo.py`, they want that file analyzed.
            # Ignore patterns only apply during directory scanning.
            if self.project_root.suffix == ".py":
                module = self._analyze_file(self.project_root)
                if module:
                    modules.append(module)
        else:
            # Directory analysis
            for py_file in self._find_python_files():
                module = self._analyze_file(py_file)
                if module:
                    modules.append(module)

        # Sort modules by name for stable ordering
        modules.sort(key=lambda m: m.module_id)

        self._apply_console_script_entrypoints(modules)
        if self.analysis_mode == AnalysisMode.INTROSPECT:
            self._introspect_actions(modules)

        return AnalysisResult(
            project_root=str(self.project_root),
            analysis_mode=self.analysis_mode,
            modules=modules,
            warnings=self.warnings,
            generator_version=__version__,
        )

    def _find_python_files(self) -> list[Path]:
        """Find all Python files to analyze, respecting ignore patterns."""
        files = []
        for path in self.project_root.rglob("*.py"):
            if self._should_ignore(path):
                continue
            files.append(path)
        return sorted(files)

    def _should_ignore(self, path: Path) -> bool:
        """Check if a path should be ignored using fnmatch patterns."""
        parts = path.relative_to(self.project_root).parts

        # Check directory patterns
        for part in parts[:-1]:
            if part.startswith("."):
                return True
            if _matches_pattern(part, IGNORE_DIR_PATTERNS):
                return True

        # Check file patterns
        filename = path.name
        if filename.startswith("."):
            return True
        if _matches_pattern(filename, IGNORE_FILE_PATTERNS):
            return True

        return False

    def _find_pyproject(self) -> Path | None:
        """Locate pyproject.toml relative to the analysis root."""
        if self.project_root.is_file():
            candidate = self.project_root.parent / "pyproject.toml"
        else:
            candidate = self.project_root / "pyproject.toml"
        if candidate.exists():
            return candidate
        return None

    def _normalize_entrypoint_map(
        self,
        value: object,
        file_path: Path,
        label: str,
    ) -> dict[str, str]:
        """Normalize a TOML entrypoint table into a string-to-string mapping."""
        if value is None:
            return {}
        if not isinstance(value, dict):
            self.warnings.append(Warning(
                code="PYPROJECT_INVALID",
                message=f"{label} must be a table",
                file_path=str(file_path),
            ))
            return {}
        result: dict[str, str] = {}
        for key, target in value.items():
            if isinstance(key, str) and isinstance(target, str):
                result[key] = target
        return result

    def _parse_entrypoint_target(self, target: str) -> str | None:
        """Parse an entrypoint target into a module.qualname string."""
        if ":" not in target:
            return None
        module, attr = target.split(":", 1)
        module = module.strip()
        attr = attr.strip().split()[0]
        if not module or not attr:
            return None
        return f"{module}.{attr}"

    def _load_console_script_targets(self) -> dict[str, str]:
        """Load console_scripts targets from pyproject.toml."""
        pyproject_path = self._find_pyproject()
        if not pyproject_path:
            return {}
        if toml is None:
            self.warnings.append(Warning(
                code="PYPROJECT_UNAVAILABLE",
                message="tomllib/tomli not installed; console_scripts not parsed",
                file_path=str(pyproject_path),
            ))
            return {}
        try:
            with open(pyproject_path, "rb") as f:
                data = toml.load(f)
        except Exception as e:
            self.warnings.append(Warning(
                code="PYPROJECT_PARSE_ERROR",
                message=f"Failed to parse pyproject.toml: {e}",
                file_path=str(pyproject_path),
            ))
            return {}

        project = data.get("project")
        if not isinstance(project, dict):
            return {}

        scripts = self._normalize_entrypoint_map(
            project.get("scripts"),
            pyproject_path,
            "project.scripts",
        )

        entry_points = project.get("entry-points")
        if entry_points is None:
            entry_points = project.get("entry_points")
        console_scripts = {}
        if isinstance(entry_points, dict):
            console_scripts = self._normalize_entrypoint_map(
                entry_points.get("console_scripts"),
                pyproject_path,
                "project.entry-points.console_scripts",
            )

        targets: dict[str, str] = {}
        for name, target in {**scripts, **console_scripts}.items():
            qualname = self._parse_entrypoint_target(target)
            if qualname:
                targets[name] = qualname

        return targets

    def _apply_console_script_entrypoints(self, modules: list[ModuleSpec]) -> None:
        """Apply console_scripts invocation plans to matching actions."""
        targets = self._load_console_script_targets()
        if not targets:
            return

        target_to_names: dict[str, list[str]] = {}
        for name, qualname in targets.items():
            target_to_names.setdefault(qualname, []).append(name)

        for module in modules:
            for action in module.actions:
                names = target_to_names.get(action.qualname)
                if not names:
                    continue
                if action.invocation_plan == InvocationPlan.DIRECT_CALL:
                    action.invocation_plan = InvocationPlan.CONSOLE_SCRIPT_ENTRYPOINT
                for script_name in names:
                    tag = f"console_script:{script_name}"
                    if tag not in action.tags:
                        action.tags.append(tag)

    def _introspect_actions(self, modules: list[ModuleSpec]) -> None:
        """Run runtime introspection in a subprocess and update action metadata."""
        payload_actions: list[dict[str, str]] = []
        for module in modules:
            for action in module.actions:
                attr_path = action.qualname
                prefix = f"{module.module_id}."
                if action.qualname.startswith(prefix):
                    attr_path = action.qualname[len(prefix):]
                payload_actions.append({
                    "action_id": action.action_id,
                    "module_id": module.module_id,
                    "attr_path": attr_path,
                })

        if not payload_actions:
            return

        results, error = self._run_introspection(payload_actions)
        if error:
            for module in modules:
                for action in module.actions:
                    action.introspection.attempted = True
                    action.introspection.success = False
                    action.introspection.error = error
            return

        for module in modules:
            for action in module.actions:
                action.introspection.attempted = True
                info = results.get(action.action_id)
                if not info:
                    action.introspection.success = False
                    action.introspection.error = "Introspection returned no data"
                    continue
                if not info.get("success"):
                    action.introspection.success = False
                    action.introspection.error = info.get("error")
                    continue

                action.introspection.success = True
                resolved = False
                params_info = {p["name"]: p.get("annotation") for p in info.get("parameters", [])}
                for param in action.parameters:
                    annotation = params_info.get(param.name)
                    if annotation:
                        param.annotation.resolved = annotation
                        resolved = True

                return_annotation = info.get("return_annotation")
                if return_annotation:
                    action.returns.annotation.resolved = return_annotation
                    resolved = True

                action.introspection.annotations_resolved = resolved

    def _run_introspection(
        self,
        actions: list[dict[str, str]],
    ) -> tuple[dict[str, dict[str, object]], str | None]:
        """Run introspection subprocess and return parsed results or error."""
        if not sys.executable:
            return {}, "Python executable not available for introspection"

        payload = {
            "project_root": str(self.project_root),
            "project_root_is_file": self.project_root.is_file(),
            "actions": actions,
        }

        script = textwrap.dedent(
            """
            import importlib
            import inspect
            import json
            import sys
            from pathlib import Path

            def format_annotation(annotation):
                if annotation is inspect._empty:
                    return None
                try:
                    return inspect.formatannotation(annotation)
                except Exception:
                    return repr(annotation)

            def main():
                payload = json.load(sys.stdin)
                project_root = payload.get("project_root")
                is_file = payload.get("project_root_is_file")
                if is_file:
                    sys.path.insert(0, str(Path(project_root).parent))
                else:
                    sys.path.insert(0, project_root)

                results = {}
                for action in payload.get("actions", []):
                    action_id = action.get("action_id")
                    module_id = action.get("module_id")
                    attr_path = action.get("attr_path") or ""
                    try:
                        module = importlib.import_module(module_id)
                        obj = module
                        for part in attr_path.split("."):
                            if part:
                                obj = getattr(obj, part)
                        sig = inspect.signature(obj)
                        params = []
                        for name, param in sig.parameters.items():
                            params.append({
                                "name": name,
                                "annotation": format_annotation(param.annotation),
                            })
                        results[action_id] = {
                            "success": True,
                            "parameters": params,
                            "return_annotation": format_annotation(sig.return_annotation),
                        }
                    except Exception as exc:
                        results[action_id] = {
                            "success": False,
                            "error": f\"{type(exc).__name__}: {exc}\",
                        }
                json.dump(results, sys.stdout)

            if __name__ == "__main__":
                main()
            """
        )

        try:
            completed = subprocess.run(
                [sys.executable, "-c", script],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                timeout=INTROSPECT_TIMEOUT_SEC,
            )
        except subprocess.TimeoutExpired:
            return {}, f"Introspection timed out after {INTROSPECT_TIMEOUT_SEC}s"
        except Exception as e:
            return {}, f"Introspection failed to start: {e}"

        if completed.returncode != 0:
            stderr = completed.stderr.strip()
            return {}, stderr or "Introspection subprocess failed"

        try:
            data = json.loads(completed.stdout or "{}")
        except json.JSONDecodeError as e:
            return {}, f"Invalid introspection output: {e}"

        return data, None

    def _analyze_file(self, file_path: Path) -> ModuleSpec | None:
        """Analyze a single Python file."""
        try:
            source = file_path.read_text(encoding="utf-8")
        except Exception as e:
            self.warnings.append(Warning(
                code="READ_ERROR",
                message=f"Could not read file: {e}",
                file_path=str(file_path),
            ))
            return None

        module_source_hash = hashlib.sha256(source.encode()).hexdigest()[:16]

        try:
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError as e:
            self.warnings.append(Warning(
                code="SYNTAX_ERROR",
                message=f"Syntax error: {e}",
                file_path=str(file_path),
                line=e.lineno,
            ))
            return None

        # Calculate module ID and import path
        if self.project_root.is_file():
            rel_path = Path(file_path.name)
        else:
            try:
                rel_path = file_path.relative_to(self.project_root)
            except ValueError:
                rel_path = file_path

        if not self.project_root.is_file() and rel_path.parts:
            top_level = rel_path.parts[0]
            if top_level in SOURCE_ROOT_DIRS:
                top_path = self.project_root / top_level
                if top_path.is_dir() and not (top_path / "__init__.py").exists():
                    if rel_path.is_absolute():
                        rel_path = rel_path.relative_to(top_path)
                    else:
                        rel_path = Path(*rel_path.parts[1:]) if len(rel_path.parts) > 1 else Path(rel_path.name)

        module_id = str(rel_path).replace("/", ".").replace("\\", ".")[:-3]
        if module_id.endswith(".__init__"):
            module_id = module_id[:-9]

        # Extract module-level info
        all_exports = self._extract_all(tree)
        has_main_block = self._has_main_block(tree)
        side_effect_risk = self._detect_side_effects(tree)
        input_lines = self._find_input_calls(tree)
        for line in input_lines:
            self.warnings.append(Warning(
                code="INPUT_USAGE",
                message="input() detected; GUI execution will not provide stdin",
                file_path=str(file_path),
                line=line,
            ))

        enum_options = self._collect_enum_definitions(tree)
        dataclass_names = self._collect_dataclass_names(tree)

        # Extract actions (functions, classes, entrypoints)
        actions = self._extract_actions(tree, module_id, enum_options, dataclass_names)

        # If __all__ is defined, filter to only exported names
        # For class methods, keep them if their parent class is in __all__
        if all_exports is not None:
            actions = [a for a in actions if self._is_exported(a, all_exports)]

        if not actions and not has_main_block:
            return None

        return ModuleSpec(
            module_id=module_id,
            display_name=file_path.stem,
            file_path=str(file_path),
            import_path=module_id,
            module_source_hash=module_source_hash,
            actions=actions,
            has_main_block=has_main_block,
            all_exports=all_exports,
            side_effect_risk=side_effect_risk,
        )

    def _is_enum_class(self, node: ast.ClassDef) -> bool:
        """Check if a class inherits from Enum/IntEnum/StrEnum."""
        for base in node.bases:
            if isinstance(base, ast.Name):
                name = base.id
            elif isinstance(base, ast.Attribute):
                name = base.attr
            else:
                continue
            if name.endswith("Enum"):
                return True
        return False

    def _collect_enum_definitions(self, tree: ast.Module) -> dict[str, list[str]]:
        """Collect enum class members defined at module scope."""
        enums: dict[str, list[str]] = {}
        for node in ast.iter_child_nodes(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if not self._is_enum_class(node):
                continue
            members: list[str] = []
            for item in node.body:
                if not isinstance(item, ast.Assign):
                    continue
                if not item.targets:
                    continue
                target = item.targets[0]
                if not isinstance(target, ast.Name):
                    continue
                name = target.id
                if name.startswith("_"):
                    continue
                value: object | None
                try:
                    value = ast.literal_eval(item.value)
                except (ValueError, TypeError, SyntaxError):
                    value = None
                if value is None:
                    members.append(name)
                else:
                    members.append(str(value))
            if members:
                enums[node.name] = members
        return enums

    def _is_dataclass(self, node: ast.ClassDef) -> bool:
        """Check if a class uses the dataclass decorator."""
        decorators = self._get_decorator_names(node)
        return "dataclass" in decorators or "dataclasses.dataclass" in decorators

    def _collect_dataclass_names(self, tree: ast.Module) -> set[str]:
        """Collect dataclass type names defined at module scope."""
        names: set[str] = set()
        for node in ast.iter_child_nodes(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if self._is_dataclass(node):
                names.add(node.name)
        return names

    def _extract_all(self, tree: ast.Module) -> list[str] | None:
        """Extract __all__ if defined."""
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "__all__":
                        if isinstance(node.value, (ast.List, ast.Tuple)):
                            return [
                                elt.value for elt in node.value.elts
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                            ]
        return None

    def _has_main_block(self, tree: ast.Module) -> bool:
        """Check if the module has an if __name__ == '__main__' block."""
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.If):
                if self._is_main_check(node.test):
                    return True
        return False

    def _is_main_check(self, node: ast.expr) -> bool:
        """Check if this is a __name__ == '__main__' comparison."""
        if isinstance(node, ast.Compare):
            if (isinstance(node.left, ast.Name) and node.left.id == "__name__"
                    and len(node.comparators) == 1
                    and isinstance(node.comparators[0], ast.Constant)
                    and node.comparators[0].value == "__main__"):
                return True
        return False

    def _detect_side_effects(self, tree: ast.Module) -> bool:
        """Detect if module has top-level side effects beyond safe patterns."""
        safe_node_types = (
            ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef,
            ast.ClassDef, ast.Expr,  # docstrings
        )

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, safe_node_types):
                # Check if Expr is just a docstring
                if isinstance(node, ast.Expr):
                    if not isinstance(node.value, ast.Constant):
                        return True
                continue

            # Assignments to simple names with literals are safe
            if isinstance(node, ast.Assign):
                if all(isinstance(t, ast.Name) for t in node.targets):
                    if isinstance(node.value, ast.Constant):
                        continue
                    # Check for simple __all__ assignment
                    if any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
                        continue
                return True

            # AnnAssign for type annotations
            if isinstance(node, ast.AnnAssign):
                if node.value is None or isinstance(node.value, ast.Constant):
                    continue
                return True

            # If block (check for __main__ guard)
            if isinstance(node, ast.If):
                if self._is_main_check(node.test):
                    continue
                return True

            # Anything else is potentially a side effect
            return True

        return False

    def _find_input_calls(self, tree: ast.AST) -> list[int]:
        """Find input() call sites for warnings."""
        lines: list[int] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "input":
                    if node.lineno is not None:
                        lines.append(node.lineno)
        return lines

    def _extract_actions(
        self,
        tree: ast.Module,
        module_id: str,
        enum_options: dict[str, list[str]],
        dataclass_names: set[str],
    ) -> list[ActionSpec]:
        """Extract all callable actions from the module."""
        actions: list[ActionSpec] = []

        for node in ast.iter_child_nodes(tree):
            # Functions
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("_") and node.name != "__init__":
                    continue
                action = self._analyze_function(node, module_id, enum_options, dataclass_names)
                if action:
                    actions.append(action)

            # Classes
            elif isinstance(node, ast.ClassDef):
                if node.name.startswith("_"):
                    continue
                class_actions = self._analyze_class(node, module_id, enum_options, dataclass_names)
                actions.extend(class_actions)

        return actions

    def _analyze_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        module_id: str,
        enum_options: dict[str, list[str]],
        dataclass_names: set[str],
    ) -> ActionSpec | None:
        """Analyze a function definition."""
        name = node.name
        qualname = f"{module_id}.{name}"
        decorators = self._get_decorator_names(node)

        # Determine kind and invocation plan
        # Priority: CLI decorators > argparse usage > entrypoint names > regular function
        kind = ActionKind.FUNCTION
        invocation_plan = InvocationPlan.DIRECT_CALL
        has_cli_decorator = False

        # 1. Check for CLI decorators (highest priority)
        for dec in decorators:
            if dec in CLI_CLICK_DECORATORS:
                kind = ActionKind.CLI_COMMAND
                has_cli_decorator = True
                invocation_plan = InvocationPlan.CLICK_COMMAND
                break
            elif dec in CLI_TYPER_DECORATORS:
                kind = ActionKind.CLI_COMMAND
                has_cli_decorator = True
                invocation_plan = InvocationPlan.TYPER_COMMAND
                break
            elif dec in CLI_BARE_DECORATORS:
                # Bare decorators like @command could be any CLI framework
                # Use CLI_GENERIC since we can't determine without import context
                kind = ActionKind.CLI_COMMAND
                has_cli_decorator = True
                invocation_plan = InvocationPlan.CLI_GENERIC
                break

        # 2. Check for argparse usage (any function, not just entrypoint names)
        if not has_cli_decorator and self._uses_argparse(node):
            kind = ActionKind.ENTRYPOINT
            invocation_plan = InvocationPlan.CLI_GENERIC

        # 3. Check for entrypoint names (only if no CLI decorator or argparse)
        if not has_cli_decorator and kind == ActionKind.FUNCTION:
            if name in ENTRYPOINT_NAMES:
                kind = ActionKind.ENTRYPOINT

        # Extract parameters
        parameters = inspect_parameters(
            self._extract_parameters(node.args),
            enum_options=enum_options,
            dataclass_names=dataclass_names,
        )

        # Extract return type
        returns = ReturnSpec()
        if node.returns:
            returns.annotation.raw = ast.unparse(node.returns)

        # Extract docstring
        doc = DocSpec()
        docstring = ast.get_docstring(node)
        if docstring:
            doc.text = docstring

        # Create stable action ID from signature hash
        action_id = self._make_action_id(qualname, node.args)

        return ActionSpec(
            action_id=action_id,
            kind=kind,
            qualname=qualname,
            name=name,
            module_import_path=module_id,
            doc=doc,
            parameters=parameters,
            returns=returns,
            invocation_plan=invocation_plan,
            tags=list(decorators),
            source_line=node.lineno,
        )

    def _analyze_class(
        self,
        node: ast.ClassDef,
        module_id: str,
        enum_options: dict[str, list[str]],
        dataclass_names: set[str],
    ) -> list[ActionSpec]:
        """Analyze a class definition, extracting staticmethods and classmethods."""
        actions: list[ActionSpec] = []
        class_name = node.name

        for item in node.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            # Skip private methods (except __init__ for future use)
            if item.name.startswith("_"):
                continue

            # Check for staticmethod/classmethod decorators
            decorators = self._get_decorator_names(item)
            if "staticmethod" in decorators:
                kind = ActionKind.STATICMETHOD
            elif "classmethod" in decorators:
                kind = ActionKind.CLASSMETHOD
            else:
                # v1: Skip regular instance methods
                continue

            qualname = f"{module_id}.{class_name}.{item.name}"

            # Extract parameters (skip 'cls' for classmethod)
            params = self._extract_parameters(item.args)
            if kind == ActionKind.CLASSMETHOD and params:
                params = params[1:]  # Remove 'cls' parameter
            params = inspect_parameters(
                params,
                enum_options=enum_options,
                dataclass_names=dataclass_names,
            )

            # Extract return type
            returns = ReturnSpec()
            if item.returns:
                returns.annotation.raw = ast.unparse(item.returns)

            # Extract docstring
            doc = DocSpec()
            docstring = ast.get_docstring(item)
            if docstring:
                doc.text = docstring

            # Create stable action ID from signature hash
            action_id = self._make_action_id(qualname, item.args)

            actions.append(ActionSpec(
                action_id=action_id,
                kind=kind,
                qualname=qualname,
                name=item.name,
                module_import_path=f"{module_id}.{class_name}",
                doc=doc,
                parameters=params,
                returns=returns,
                invocation_plan=InvocationPlan.DIRECT_CALL,
                tags=[f"class:{class_name}"] + list(decorators),
                source_line=item.lineno,
            ))

        return actions

    def _extract_parameters(self, args: ast.arguments) -> list[ParamSpec]:
        """Extract parameter specifications from function arguments.

        Python's defaults list is shared between posonlyargs and args.
        For def f(a, b=1, /, c=2, d=3): defaults=[1, 2, 3]
        The defaults apply right-to-left across posonlyargs + args combined.
        """
        params: list[ParamSpec] = []

        # Combined positional args (posonlyargs + args)
        all_positional = list(args.posonlyargs) + list(args.args)
        num_positional = len(all_positional)
        num_defaults = len(args.defaults)

        # Defaults apply to the LAST num_defaults positional args
        first_default_index = num_positional - num_defaults

        # Process positional-only args
        for i, arg in enumerate(args.posonlyargs):
            param = self._make_param(arg, ParamKind.POSITIONAL_ONLY)

            # Check for default
            if i >= first_default_index:
                default_idx = i - first_default_index
                param.required = False
                param.default = self._extract_default(args.defaults[default_idx])

            params.append(param)

        # Process regular args
        posonly_count = len(args.posonlyargs)
        for i, arg in enumerate(args.args):
            param = self._make_param(arg, ParamKind.POSITIONAL_OR_KEYWORD)

            # Check for default (index in combined list is posonly_count + i)
            combined_idx = posonly_count + i
            if combined_idx >= first_default_index:
                default_idx = combined_idx - first_default_index
                param.required = False
                param.default = self._extract_default(args.defaults[default_idx])

            params.append(param)

        # *args
        if args.vararg:
            param = self._make_param(args.vararg, ParamKind.VAR_POSITIONAL)
            param.required = False
            params.append(param)

        # Keyword-only args
        for i, arg in enumerate(args.kwonlyargs):
            param = self._make_param(arg, ParamKind.KEYWORD_ONLY)

            # kw_defaults can have None entries for args without defaults
            if i < len(args.kw_defaults) and args.kw_defaults[i] is not None:
                param.required = False
                param.default = self._extract_default(args.kw_defaults[i])

            params.append(param)

        # **kwargs
        if args.kwarg:
            param = self._make_param(args.kwarg, ParamKind.VAR_KEYWORD)
            param.required = False
            params.append(param)

        return params

    def _make_param(self, arg: ast.arg, kind: ParamKind) -> ParamSpec:
        """Create a ParamSpec from an ast.arg."""
        annotation = Annotation()
        if arg.annotation:
            annotation.raw = ast.unparse(arg.annotation)

        return ParamSpec(
            name=arg.arg,
            kind=kind,
            annotation=annotation,
        )

    def _extract_default(self, node: ast.expr) -> DefaultValue:
        """Extract default value from an AST node."""
        repr_str = ast.unparse(node)

        # Try to evaluate as literal
        try:
            literal_value = ast.literal_eval(node)
            if _is_json_serializable(literal_value):
                return DefaultValue(
                    present=True,
                    repr=repr_str,
                    literal=literal_value,
                    is_literal=True,
                )
            return DefaultValue(
                present=True,
                repr=repr_str,
                is_literal=False,
            )
        except (ValueError, TypeError, SyntaxError):
            return DefaultValue(
                present=True,
                repr=repr_str,
                is_literal=False,
            )

    def _get_decorator_names(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> set[str]:
        """Get the names of all decorators on a node."""
        names = set()
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name):
                names.add(dec.id)
            elif isinstance(dec, ast.Attribute):
                names.add(ast.unparse(dec))
            elif isinstance(dec, ast.Call):
                if isinstance(dec.func, ast.Name):
                    names.add(dec.func.id)
                elif isinstance(dec.func, ast.Attribute):
                    names.add(ast.unparse(dec.func))
        return names

    def _uses_argparse(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        """Check if a function uses argparse."""
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Attribute):
                    if child.func.attr == "ArgumentParser":
                        return True
                elif isinstance(child.func, ast.Name):
                    if child.func.id == "ArgumentParser":
                        return True
        return False

    def _is_exported(self, action: ActionSpec, all_exports: list[str]) -> bool:
        """Check if an action should be included based on __all__.

        For functions: check if action.name is in __all__.
        For class methods: ONLY check if parent class is in __all__ (never action.name).
        """
        # For class methods, ONLY check parent class (class methods have "class:ClassName" tag)
        is_class_method = action.kind in (ActionKind.STATICMETHOD, ActionKind.CLASSMETHOD)
        if is_class_method:
            for tag in action.tags:
                if tag.startswith("class:"):
                    class_name = tag[6:]  # Remove "class:" prefix
                    return class_name in all_exports
            return False  # Class method without class tag shouldn't happen, but be safe

        # For functions/entrypoints, check action.name directly
        return action.name in all_exports

    def _make_action_id(self, qualname: str, args: ast.arguments) -> str:
        """Create a stable action ID from qualname and signature hash.

        Uses the signature structure (param names, kinds, annotations) rather than
        line numbers for stability across refactors.
        """
        # Build signature string from parameters
        sig_parts = []

        for arg in args.posonlyargs:
            ann = ast.unparse(arg.annotation) if arg.annotation else ""
            sig_parts.append(f"/{arg.arg}:{ann}")

        for arg in args.args:
            ann = ast.unparse(arg.annotation) if arg.annotation else ""
            sig_parts.append(f"{arg.arg}:{ann}")

        if args.vararg:
            ann = ast.unparse(args.vararg.annotation) if args.vararg.annotation else ""
            sig_parts.append(f"*{args.vararg.arg}:{ann}")

        for arg in args.kwonlyargs:
            ann = ast.unparse(arg.annotation) if arg.annotation else ""
            sig_parts.append(f"kw:{arg.arg}:{ann}")

        if args.kwarg:
            ann = ast.unparse(args.kwarg.annotation) if args.kwarg.annotation else ""
            sig_parts.append(f"**{args.kwarg.arg}:{ann}")

        sig_str = ",".join(sig_parts)
        key = f"{qualname}({sig_str})"
        hash_suffix = hashlib.md5(key.encode()).hexdigest()[:8]
        return f"{qualname}:{hash_suffix}"


def analyze_project(path: str | Path, analysis_mode: AnalysisMode = AnalysisMode.AST_ONLY) -> AnalysisResult:
    """Convenience function to analyze a project."""
    analyzer = ASTAnalyzer(path, analysis_mode=analysis_mode)
    return analyzer.analyze()

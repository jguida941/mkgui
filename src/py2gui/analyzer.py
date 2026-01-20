"""AST-only code analyzer for Python source files.

Analyzes Python code without importing it, extracting:
- Functions and their signatures
- Classes and their methods
- Entrypoints (main blocks, CLI decorators, argparse usage)
- Type annotations and defaults
"""

import ast
import fnmatch
import hashlib
from pathlib import Path

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

# Entrypoint function names (used only when no CLI decorator is present)
ENTRYPOINT_NAMES = {"main", "run", "cli", "start", "execute"}

# CLI framework decorators - fully qualified names only
# Bare names like @command could be anything, so they get CLI_GENERIC
CLI_CLICK_DECORATORS = {"click.command", "click.group"}
CLI_TYPER_DECORATORS = {"typer.command", "app.command", "typer.Typer"}
# Bare decorators that indicate CLI but unknown framework
CLI_BARE_DECORATORS = {"command", "group", "Typer"}


def _matches_pattern(name: str, patterns: list[str]) -> bool:
    """Check if name matches any of the fnmatch patterns."""
    return any(fnmatch.fnmatch(name, pattern) for pattern in patterns)


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
            # If a user runs `pyqt6-wrap tests/foo.py`, they want that file analyzed.
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

        return AnalysisResult(
            project_root=str(self.project_root),
            analysis_mode=self.analysis_mode,
            modules=modules,
            warnings=self.warnings,
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
        try:
            rel_path = file_path.relative_to(self.project_root)
        except ValueError:
            rel_path = file_path

        module_id = str(rel_path).replace("/", ".").replace("\\", ".")[:-3]
        if module_id.endswith(".__init__"):
            module_id = module_id[:-9]

        # Extract module-level info
        all_exports = self._extract_all(tree)
        has_main_block = self._has_main_block(tree)
        side_effect_risk = self._detect_side_effects(tree)

        # Extract actions (functions, classes, entrypoints)
        actions = self._extract_actions(tree, module_id)

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
            actions=actions,
            has_main_block=has_main_block,
            all_exports=all_exports,
            side_effect_risk=side_effect_risk,
        )

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

    def _extract_actions(self, tree: ast.Module, module_id: str) -> list[ActionSpec]:
        """Extract all callable actions from the module."""
        actions: list[ActionSpec] = []

        for node in ast.iter_child_nodes(tree):
            # Functions
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("_") and node.name != "__init__":
                    continue
                action = self._analyze_function(node, module_id)
                if action:
                    actions.append(action)

            # Classes
            elif isinstance(node, ast.ClassDef):
                if node.name.startswith("_"):
                    continue
                class_actions = self._analyze_class(node, module_id)
                actions.extend(class_actions)

        return actions

    def _analyze_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, module_id: str
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
        parameters = self._extract_parameters(node.args)

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

    def _analyze_class(self, node: ast.ClassDef, module_id: str) -> list[ActionSpec]:
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
            return DefaultValue(
                present=True,
                repr=repr_str,
                literal=literal_value,
                is_literal=True,
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

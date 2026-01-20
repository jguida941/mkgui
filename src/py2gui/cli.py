"""CLI interface for py2gui - Python to GUI generator."""

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from . import __version__
from .analyzer import analyze_project
from .generator import GeneratorConfig, ScaffoldMode, SourceMode, generate_project
from .models import ActionKind, AnalysisMode

app = typer.Typer(
    name="py2gui",
    help="Transform Python code into PyQt6 GUI applications.",
    no_args_is_help=True,
)

console = Console()


def _parse_analysis_mode(mode_str: str) -> AnalysisMode:
    """Parse and validate analysis mode string, with fallback warning."""
    if mode_str == "ast-only":
        return AnalysisMode.AST_ONLY
    elif mode_str == "introspect":
        console.print(
            "[yellow]Warning:[/yellow] 'introspect' mode not yet implemented, "
            "falling back to 'ast-only'"
        )
        return AnalysisMode.AST_ONLY
    else:
        console.print(f"[red]Error:[/red] Invalid analysis mode: {mode_str}")
        raise typer.Exit(1)


@app.command("wrap")
def wrap_command(
    source: Path = typer.Argument(
        ...,
        help="Path to Python file or directory to wrap.",
        exists=True,
    ),
    output: Path = typer.Option(
        None,
        "--output", "-o",
        help="Output directory for generated GUI project.",
    ),
    copy_source: bool = typer.Option(
        False,
        "--copy-source",
        help="Copy source files into output (vendor mode).",
    ),
    analysis_mode: str = typer.Option(
        "ast-only",
        "--analysis-mode",
        help="Analysis mode: 'ast-only' or 'introspect'.",
    ),
    scaffold_mode: str = typer.Option(
        "thin",
        "--scaffold-mode",
        help="Output mode: 'thin' (spec.json + launcher) or 'standalone'.",
    ),
    analyze_only: bool = typer.Option(
        False,
        "--analyze-only",
        help="Only analyze and show results, don't generate output.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output analysis result as JSON (with --analyze-only).",
    ),
) -> None:
    """Wrap existing Python code in a PyQt6 GUI."""
    # Validate and parse analysis mode
    mode = _parse_analysis_mode(analysis_mode)

    # Validate scaffold mode
    if scaffold_mode not in ("thin", "standalone"):
        console.print(f"[red]Error:[/red] Invalid scaffold mode: {scaffold_mode}")
        raise typer.Exit(1)

    # Warn about standalone mode not being implemented and force thin mode
    if scaffold_mode == "standalone":
        console.print(
            "[yellow]Warning:[/yellow] 'standalone' scaffold mode is not yet implemented. "
            "Using 'thin' mode instead."
        )
        scaffold_mode = "thin"  # Force thin until standalone is implemented

    # Run analysis
    console.print(f"[blue]Analyzing:[/blue] {source}")
    result = analyze_project(source, analysis_mode=mode)

    if analyze_only:
        if json_output:
            # Output as JSON
            print(json.dumps(result.to_dict(), indent=2))
        else:
            # Pretty print results
            _print_analysis_result(result)
        return

    # Generate output
    if output is None:
        output = Path(f"{source.stem}_gui")

    # Map scaffold mode
    scaffold = ScaffoldMode.THIN if scaffold_mode == "thin" else ScaffoldMode.STANDALONE

    # Create generator config
    config = GeneratorConfig(
        output_dir=output,
        source_path=source,
        scaffold_mode=scaffold,
        source_mode=SourceMode.COPY if copy_source else SourceMode.IMPORT,
        create_overrides=True,
    )

    console.print(f"[blue]Generating:[/blue] {output}")
    gen_result = generate_project(result, config)

    if gen_result.errors:
        console.print("[red]Errors occurred during generation:[/red]")
        for error in gen_result.errors:
            console.print(f"  - {error}")
        raise typer.Exit(1)

    # Report success
    console.print(f"\n[green]Generated successfully![/green]")
    console.print(f"  Spec: {gen_result.spec_path}")
    console.print(f"  Launcher: {gen_result.launcher_path}")
    if gen_result.overrides_path:
        console.print(f"  Overrides: {gen_result.overrides_path}")
    if gen_result.copied_sources:
        console.print(f"  Copied {len(gen_result.copied_sources)} source file(s)")

    console.print(f"\n[dim]Run with: python {gen_result.launcher_path}[/dim]")


@app.command("analyze")
def analyze_command(
    source: Path = typer.Argument(
        ...,
        help="Path to Python file or directory to analyze.",
        exists=True,
    ),
    analysis_mode: str = typer.Option(
        "ast-only",
        "--analysis-mode",
        help="Analysis mode: 'ast-only' or 'introspect'.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output as JSON instead of formatted text.",
    ),
    output_file: Path = typer.Option(
        None,
        "--output", "-o",
        help="Write JSON output to file instead of stdout.",
    ),
) -> None:
    """Analyze Python code and show detected actions (dry run)."""
    # Validate and parse analysis mode
    mode = _parse_analysis_mode(analysis_mode)

    result = analyze_project(source, analysis_mode=mode)

    if json_output or output_file:
        json_str = json.dumps(result.to_dict(), indent=2)
        if output_file:
            output_file.write_text(json_str)
            console.print(f"[green]Analysis written to:[/green] {output_file}")
        else:
            print(json_str)
    else:
        _print_analysis_result(result)


def _print_analysis_result(result) -> None:
    """Pretty print analysis results."""
    # Header
    console.print(Panel.fit(
        f"[bold]Analysis Result[/bold]\n"
        f"Mode: {result.analysis_mode.value}\n"
        f"Project: {result.project_root}",
        title="py2gui",
    ))

    if not result.modules:
        console.print("\n[yellow]No modules with public actions found.[/yellow]")
        return

    # Build tree of modules and actions
    tree = Tree("[bold]Detected Actions[/bold]")

    for module in result.modules:
        module_label = f"[cyan]{module.display_name}[/cyan]"
        if module.has_main_block:
            module_label += " [dim](has __main__)[/dim]"
        if module.side_effect_risk:
            module_label += " [yellow]⚠ side effects[/yellow]"

        module_branch = tree.add(module_label)

        for action in module.actions:
            # Build action label
            kind_color = {
                ActionKind.FUNCTION: "green",
                ActionKind.ENTRYPOINT: "magenta",
                ActionKind.CLI_COMMAND: "blue",
                ActionKind.STATICMETHOD: "cyan",
                ActionKind.CLASSMETHOD: "cyan",
            }.get(action.kind, "white")

            label = f"[{kind_color}]{action.name}[/{kind_color}]()"

            # Add parameter summary
            if action.parameters:
                param_names = [p.name for p in action.parameters[:3]]
                if len(action.parameters) > 3:
                    param_names.append("...")
                label += f" [dim]({', '.join(param_names)})[/dim]"

            # Add kind badge
            label += f" [{kind_color}][{action.kind.value}][/{kind_color}]"

            # Add invocation plan if not default
            if action.invocation_plan.value != "direct_call":
                label += f" [dim]→ {action.invocation_plan.value}[/dim]"

            action_node = module_branch.add(label)

            # Show docstring if present
            if action.doc.text:
                first_line = action.doc.text.split("\n")[0][:60]
                action_node.add(f"[dim]{first_line}[/dim]")

    console.print(tree)

    # Summary table
    console.print()
    table = Table(title="Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", style="green")

    total_actions = sum(len(m.actions) for m in result.modules)
    table.add_row("Modules", str(len(result.modules)))
    table.add_row("Total Actions", str(total_actions))

    # Count by kind
    kind_counts: dict[str, int] = {}
    for module in result.modules:
        for action in module.actions:
            kind_counts[action.kind.value] = kind_counts.get(action.kind.value, 0) + 1

    for kind, count in sorted(kind_counts.items()):
        table.add_row(f"  {kind}", str(count))

    console.print(table)

    # Warnings
    if result.warnings:
        console.print()
        console.print("[yellow]Warnings:[/yellow]")
        for warning in result.warnings:
            loc = f"{warning.file_path}:{warning.line}" if warning.line else warning.file_path
            console.print(f"  [{warning.code}] {loc}: {warning.message}")


@app.command("version")
def version_command() -> None:
    """Show version information."""
    console.print(f"py2gui version {__version__}")


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()

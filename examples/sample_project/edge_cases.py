"""Edge case test file for analyzer fixes."""

import argparse
from pathlib import Path

import click


# Test 1: Positional-only parameters with defaults
def posonly_defaults(a, b=1, /, c=2, d=3):
    """Function with positional-only args that have defaults.

    Expected: a is required, b/c/d have defaults.
    Bug was: defaults_offset was wrong, b wouldn't get its default.
    """
    pass


def mixed_params(x, y=10, /, z=20, *, kw_only=30, **kwargs):
    """Mixed positional-only, regular, keyword-only, and **kwargs.

    Expected: x required, y/z/kw_only have defaults, kwargs is var_keyword.
    """
    pass


# Test 2: Click-decorated function named 'main' should keep CLI_COMMAND kind
@click.command()
@click.option("--name", default="World")
def main(name: str = "World") -> None:
    """This is a click command named 'main'.

    Expected: kind=cli_command, invocation_plan=click_command
    Bug was: name 'main' overrode CLI decorator detection.
    """
    click.echo(f"Hello, {name}!")


# Test 3: argparse in non-entrypoint-named function
def process_files(files: list[Path]) -> None:
    """Function using argparse but not named 'main', 'run', etc.

    Expected: kind=entrypoint, invocation_plan=cli_generic
    Bug was: argparse only detected for ENTRYPOINT_NAMES.
    """
    parser = argparse.ArgumentParser(description="Process files")
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args()
    for f in args.files:
        print(f"Processing {f}")


# Test 4: Regular function named 'run' without argparse/click
def run(config: dict) -> bool:
    """Regular entrypoint function.

    Expected: kind=entrypoint, invocation_plan=direct_call
    """
    return True


# Test 5: Function with complex signature for ID stability
def complex_signature(
    pos_only: int,
    /,
    regular: str,
    *args: tuple,
    kw_only: bool = False,
    **kwargs: dict,
) -> list[str]:
    """Function with complex signature.

    The action_id should be stable based on signature, not line number.
    """
    return []

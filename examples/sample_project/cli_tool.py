"""Sample CLI tool using click for testing CLI detection."""

import click


@click.group()
def cli():
    """Sample CLI application."""
    pass


@cli.command()
@click.argument("name")
@click.option("--greeting", "-g", default="Hello", help="Greeting to use")
def greet(name: str, greeting: str = "Hello") -> None:
    """Greet someone by name.

    Args:
        name: The name to greet
        greeting: The greeting to use
    """
    click.echo(f"{greeting}, {name}!")


@cli.command()
@click.option("--count", "-c", default=5, type=int, help="Number of items")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
def process(count: int = 5, verbose: bool = False) -> None:
    """Process some items.

    Args:
        count: Number of items to process
        verbose: Enable verbose logging
    """
    for i in range(count):
        if verbose:
            click.echo(f"Processing item {i + 1}")


if __name__ == "__main__":
    cli()

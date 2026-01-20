"""Shared pytest fixtures for py2gui tests."""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory for testing."""
    return tmp_path


@pytest.fixture
def sample_python_file(tmp_path: Path) -> Path:
    """Create a sample Python file for testing."""
    code = '''
"""Sample module for testing."""

def greet(name: str, greeting: str = "Hello") -> str:
    """Greet someone by name."""
    return f"{greeting}, {name}!"

def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

class Calculator:
    """Simple calculator class."""

    @staticmethod
    def multiply(x: int, y: int) -> int:
        """Multiply two numbers."""
        return x * y

    @classmethod
    def from_value(cls, value: int) -> "Calculator":
        """Create a calculator with an initial value."""
        return cls()
'''
    file_path = tmp_path / "sample.py"
    file_path.write_text(code)
    return file_path


@pytest.fixture
def sample_cli_file(tmp_path: Path) -> Path:
    """Create a sample CLI Python file for testing."""
    code = '''
"""Sample CLI module."""

import click

@click.command()
@click.argument("name")
@click.option("--count", default=1, help="Number of greetings.")
def hello(name: str, count: int) -> None:
    """Say hello."""
    for _ in range(count):
        print(f"Hello, {name}!")

if __name__ == "__main__":
    hello()
'''
    file_path = tmp_path / "cli_sample.py"
    file_path.write_text(code)
    return file_path


@pytest.fixture
def sample_project_dir(tmp_path: Path) -> Path:
    """Create a sample project directory structure for testing."""
    # Main module
    src_dir = tmp_path / "src"
    src_dir.mkdir()

    (src_dir / "__init__.py").write_text('"""Source package."""\n__version__ = "1.0.0"\n')

    (src_dir / "core.py").write_text('''
"""Core module."""

def process(data: str) -> str:
    """Process data."""
    return data.upper()

def validate(value: int, *, min_val: int = 0, max_val: int = 100) -> bool:
    """Validate a value is in range."""
    return min_val <= value <= max_val
''')

    (src_dir / "utils.py").write_text('''
"""Utility functions."""

from typing import Optional, List

def parse_csv(text: str) -> List[str]:
    """Parse CSV text into list."""
    return [item.strip() for item in text.split(",")]

def format_name(first: str, last: str, middle: Optional[str] = None) -> str:
    """Format a full name."""
    if middle:
        return f"{first} {middle} {last}"
    return f"{first} {last}"
''')

    # Test directory (should be ignored)
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "test_core.py").write_text("def test_process(): pass")

    return tmp_path


@pytest.fixture
def code_with_all_exports(tmp_path: Path) -> Path:
    """Create a file with __all__ exports."""
    code = '''
"""Module with explicit exports."""

__all__ = ["public_func", "PublicClass"]

def public_func():
    """This is exported."""
    pass

def _private_func():
    """This is private."""
    pass

def hidden_func():
    """This is not in __all__."""
    pass

class PublicClass:
    """Exported class."""

    @staticmethod
    def public_method():
        """This should be included."""
        pass

class HiddenClass:
    """Not in __all__."""

    @staticmethod
    def hidden_method():
        """This should be excluded."""
        pass
'''
    file_path = tmp_path / "exports.py"
    file_path.write_text(code)
    return file_path


@pytest.fixture
def code_with_side_effects(tmp_path: Path) -> Path:
    """Create a file with side effects."""
    code = '''
"""Module with side effects."""

print("Loading module!")  # Side effect

DATABASE = connect_to_db()  # Side effect

def safe_func():
    """This is safe."""
    pass
'''
    file_path = tmp_path / "side_effects.py"
    file_path.write_text(code)
    return file_path


@pytest.fixture
def code_with_syntax_error(tmp_path: Path) -> Path:
    """Create a file with a syntax error."""
    code = '''
def broken(
    """Missing closing paren and invalid syntax"""
    pass
'''
    file_path = tmp_path / "broken.py"
    file_path.write_text(code)
    return file_path

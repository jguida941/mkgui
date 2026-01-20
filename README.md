# mkgui

Generate PyQt6 GUI scaffolding from Python code.

## Index

- [Why](#why)
- [How It Works](#how-it-works)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Commands](#commands)
- [Generated Output](#generated-output)
- [Type-to-Widget Mapping](#type-to-widget-mapping)
- [Example](#example)

## Why

You have Python code. Functions, CLI tools, libraries. You want a GUI for it without rewriting everything or learning a GUI framework.

mkgui analyzes your code and generates the scaffolding to wrap it in a PyQt6 interface. Your original code stays untouched. The GUI just calls into it.

## How It Works

1. **AST Analysis** - Parses your Python files without importing them (no side effects)
2. **Detection** - Finds public functions, type hints, CLI decorators, entrypoints
3. **Mapping** - Converts Python types to appropriate GUI widgets (int to spinbox, bool to checkbox, etc.)
4. **Generation** - Creates spec.json describing your code plus a thin launcher

The generated spec.json is a structured description of your code's API. A runtime GUI engine reads this spec and builds the interface dynamically.

## Installation

```bash
pip install -e .
```

## Quick Start

```bash
# See what mkgui detects in your code
mkgui analyze ./my_project/

# Generate GUI scaffolding
mkgui wrap ./my_project/

# Generate with vendored source (copies files into output)
mkgui wrap ./my_project/ --copy-source
```

## Commands

### analyze

Dry run. Shows detected actions without generating anything.

```bash
mkgui analyze ./my_code/
mkgui analyze ./my_code/ --json
mkgui analyze ./my_code/ --json --output analysis.json
```

### wrap

Generate the GUI scaffolding.

```bash
mkgui wrap ./my_code/
mkgui wrap ./my_code/ --output ./my_gui/
mkgui wrap ./my_code/ --copy-source
```

### version

```bash
mkgui version
```

## Generated Output

```
my_gui/
├── main.py           # Thin launcher
├── spec.json         # Your code's API description
├── overrides.yml     # UI customization template
└── original_src/     # Only with --copy-source
```

**spec.json** - Structured description of modules, functions, parameters, types, defaults

**main.py** - Entry point that loads the spec and launches the GUI

**overrides.yml** - Customize widgets, validation, display names per parameter

## Type-to-Widget Mapping

| Python Type | Widget |
|-------------|--------|
| int | Spin box |
| float | Double spin box |
| bool | Checkbox |
| str | Line edit |
| Path | File picker |
| Enum, Literal | Combo box |
| list | Multi-line text |
| Optional[T] | Widget for T, allows empty |
| dict, Any | JSON editor |

## Example

```python
# calculator.py
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

def greet(name: str, greeting: str = "Hello") -> str:
    """Greet someone."""
    return f"{greeting}, {name}!"
```

```bash
$ mkgui analyze ./calculator.py

Detected Actions
└── calculator
    ├── add() (a, b) [function]
    │   └── Add two numbers.
    └── greet() (name, greeting, ...) [function]
        └── Greet someone.
```

```bash
$ mkgui wrap ./calculator.py --output ./calc_gui/

Generated successfully!
  Spec: calc_gui/spec.json
  Launcher: calc_gui/main.py
  Overrides: calc_gui/overrides.yml
```

## Requirements

- Python 3.10+

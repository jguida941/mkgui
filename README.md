# PyQt6 Boilerplate Generator

A smart CLI tool that scaffolds PyQt6 applications through multiple modes: interactive wizard, code analysis, and spec files.

## Installation

```bash
cd pyqt6_boilerplate_gen
pip install -e .
```

## Quick Start

```bash
# Interactive wizard (recommended for first-time users)
pyqt6-gen new

# Or with a project name
pyqt6-gen new my-awesome-app
```

---

## Three Ways to Generate Projects

### 1. Interactive Wizard (`new`)

The wizard guides you through every choice with descriptions:

```bash
pyqt6-gen new
```

**Steps:**
1. **Project name** - Name for your app (e.g., `my-app`)
2. **Output directory** - Where to create the project
3. **App type** - What kind of app you're building:
   - `utility` - Single-purpose tools (calculator, converter)
   - `crud` - Data apps with forms/tables (todo list, contacts)
   - `editor` - Text/document editing (notepad, markdown editor)
   - `media` - Audio/video/images (music player, image viewer)
   - `dashboard` - Charts and monitoring (stock tracker, system monitor)
4. **Window layout** - How the UI is organized:
   - `single` - One main window
   - `tabbed` - Multiple tabs
   - `docked` - Resizable panels (like an IDE)
   - `mdi` - Child windows inside main window
   - `tray` - System tray app
5. **Storage** - How data is persisted:
   - `none` - No persistence
   - `qsettings` - Simple key-value config
   - `sqlite` - Full database
   - `json` - JSON files
6. **Components** - UI elements to include:
   - Menu bar, Toolbar, Status bar
7. **Features** - Optional extras:
   - Settings dialog, Dark theme, About dialog, Logging
8. **Architecture** - Code organization:
   - `simple` - Everything in main_window.py
   - `model_view` - Separate models/ and views/ directories
   - `mvp` - Full Model-View-Presenter pattern

### 2. Analyze Existing Code (`analyze`)

Point at your existing Python code and get a matching PyQt6 scaffold:

```bash
# Analyze a directory
pyqt6-gen analyze ./my_existing_code/

# Analyze a single file
pyqt6-gen analyze ./my_script.py

# Specify output directory
pyqt6-gen analyze ./my_code/ --output ./my-pyqt-app
```

**What it detects:**

| Your Code Has | Scaffold Gets |
|---------------|---------------|
| `sqlite3`, `sqlalchemy` imports | CRUD app + SQLite storage |
| `pandas`, `numpy` imports | Dashboard app + table views |
| `@dataclass` or Pydantic models | Auto-generated forms |
| `requests`, `httpx` imports | API-driven app structure |
| `PIL`, `opencv` imports | Media app layout |
| `matplotlib`, `plotly` imports | Dashboard with charts |
| `json.load/dump` calls | JSON file storage |

**Example:**
```bash
$ pyqt6-gen analyze ./my_contacts_app/

╭─────────────── Analysis Results ───────────────╮
│   Found 3 Python files                         │
│   Detected patterns:                           │
│   • Database: sqlite3                          │
│   • Dataclasses: Contact (4 fields)            │
│   • JSON file operations                       │
│                                                │
│   Recommended: CRUD App with SQLite            │
╰────────────────────────────────────────────────╯

? Accept this scaffold? [Y/n/customize]
```

### 3. Spec File (`from-spec`)

Define your app in YAML/JSON for reproducible generation:

```bash
# Generate example spec file
pyqt6-gen init-spec

# Edit it, then generate
pyqt6-gen from-spec pyqt6-spec.yaml
```

**Example spec file (`pyqt6-spec.yaml`):**

```yaml
project:
  name: my-contact-app
  author: Your Name
  description: A contact management application

app_type: crud        # utility, crud, editor, media, dashboard

window:
  layout: single      # single, tabbed, docked, mdi, tray

storage: sqlite       # none, qsettings, sqlite, json

components:
  - menu_bar
  - status_bar
  - toolbar

features:
  - settings_dialog
  - dark_theme
  - about_dialog
  - logging_setup

architecture: model_view   # simple, model_view, mvp

# Optional: auto-generate database tables from models
models:
  Contact:
    - first_name: str
    - last_name: str
    - email: str
    - phone: str
```

---

## Generated Project Structure

### Simple Utility App
```
my-utility/
├── pyproject.toml
├── requirements.txt
├── src/my_utility/
│   ├── __init__.py
│   ├── main.py              # Entry point
│   ├── app.py               # QApplication setup
│   └── ui/
│       ├── main_window.py   # Your main window
│       ├── menubar.py       # Menu definitions
│       └── dialogs/
│           └── about_dialog.py
└── tests/
```

### Full CRUD App with Database
```
my-crud-app/
├── pyproject.toml
├── requirements.txt
├── src/my_crud_app/
│   ├── __init__.py
│   ├── main.py
│   ├── app.py
│   ├── ui/
│   │   ├── main_window.py
│   │   ├── menubar.py
│   │   ├── toolbar.py
│   │   ├── statusbar.py
│   │   ├── theme_manager.py
│   │   └── dialogs/
│   │       ├── settings_dialog.py
│   │       └── about_dialog.py
│   ├── models/
│   │   ├── __init__.py
│   │   └── database.py      # SQLite setup
│   ├── views/
│   │   ├── __init__.py
│   │   └── table_view.py    # CRUD table widget
│   └── resources/
│       └── styles/
│           ├── dark.qss
│           └── light.qss
└── tests/
```

---

## Running Your Generated App

```bash
cd my-app
pip install -e .
python -m my_app.main
```

Or use the installed command:
```bash
my-app   # Uses the script defined in pyproject.toml
```

---

## Customizing the Generated Code

### Adding Your Logic

The scaffold has placeholder comments where you add your code:

```python
# In menubar.py
def _on_save(window: QMainWindow) -> None:
    """Handle save file action."""
    if hasattr(window, 'show_status_message'):
        window.show_status_message("File saved")
    pass  # <-- Add your save logic here
```

### Using the CRUD Table View

```python
# In your main_window.py
from .views.table_view import DataTableView

class MainWindow(QMainWindow):
    def _setup_ui(self):
        # Create table view for a database table
        self.table = DataTableView()
        self.table.set_table("contacts")  # Load from 'contacts' table
        self.setCentralWidget(self.table)
```

### Switching Themes

```python
# Theme is managed automatically, but you can switch manually:
window.theme_manager.set_theme("dark")   # or "light"
window.theme_manager.toggle_theme()      # switch between them
```

### Using Settings

```python
from PyQt6.QtCore import QSettings

settings = QSettings("YourCompany", "YourApp")

# Save a setting
settings.setValue("window/geometry", self.saveGeometry())

# Load a setting
geometry = settings.value("window/geometry")
if geometry:
    self.restoreGeometry(geometry)
```

---

## CLI Reference

```bash
# Show all commands
pyqt6-gen --help

# Show version
pyqt6-gen --version

# Interactive wizard
pyqt6-gen new [PROJECT_NAME] [--output PATH]

# Analyze existing code
pyqt6-gen analyze PATH [--output PATH]

# Generate from spec file
pyqt6-gen from-spec SPEC_FILE [--output PATH]

# Create example spec file
pyqt6-gen init-spec [--output PATH]

# List available options
pyqt6-gen list
```

---

## Examples

### Example 1: Quick Utility App

```bash
pyqt6-gen new calculator --output ./calculator
cd calculator
pip install -e .
python -m calculator.main
```

### Example 2: CRUD App from Spec

```yaml
# contacts-spec.yaml
project:
  name: contacts-manager
app_type: crud
storage: sqlite
components: [menu_bar, toolbar, status_bar]
features: [settings_dialog, dark_theme]
architecture: model_view
```

```bash
pyqt6-gen from-spec contacts-spec.yaml
```

### Example 3: Analyze and Scaffold

```bash
# You have existing code with sqlite3 and dataclasses
pyqt6-gen analyze ./my_existing_project/ --output ./my_pyqt_app
```

---

## Tips

1. **Start with `pyqt6-gen list`** to see all available options
2. **Use spec files** for team projects (commit to git for reproducibility)
3. **The analyze mode** is great for wrapping existing CLI tools in a GUI
4. **Dark theme** includes full QSS stylesheets you can customize
5. **Model-View architecture** is recommended for any app with data

---

## Requirements

- Python 3.10+
- PyQt6 (installed automatically when you pip install your generated project)

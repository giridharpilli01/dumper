# AI Context Dumper

An AI context aggregation desktop application and command-line utility. It scans codebases according to CSV manifest rules, enforces hard filesystem safety boundaries (5 MiB ceiling, symlink rejection), and generates either a single compact TXT context dump or a staged directory export.

---

## Table of Contents
1. [Prerequisites](#1-prerequisites)
2. [Step-by-Step Quick Start (Clone & Launch)](#2-step-by-step-quick-start-clone--launch)
   - [Windows (PowerShell)](#windows-powershell)
   - [Windows (Command Prompt / CMD)](#windows-command-prompt--cmd)
   - [macOS](#macos)
   - [Linux (Ubuntu / Debian / Fedora / Arch)](#linux-ubuntu--debian--fedora--arch)
3. [Manual Setup (Without Launcher Scripts)](#3-manual-setup-without-launcher-scripts)
4. [Headless / CLI Mode](#4-headless--cli-mode)
5. [How to Use the Application](#5-how-to-use-the-application)
   - [Manifest Selection & Rules](#manifest-selection--rules)
   - [Explorer Interactions](#explorer-interactions)
   - [Output Modes](#output-modes)
6. [Updating the Application](#6-updating-the-application)
7. [Running the Test Suite](#7-running-the-test-suite)
8. [Troubleshooting & Common Fixes](#8-troubleshooting--common-fixes)
9. [Architecture & File Structure](#9-architecture--file-structure)

---

## 1. Prerequisites

Before cloning, verify that **Git** and **Python >= 3.9** are installed on your machine.

### Check Git
```bash
git --version
```

### Check Python (must be 3.9 or newer)
* **Windows**:
  ```cmd
  py --version
  ```
  *(or `python --version`)*
* **macOS / Linux**:
  ```bash
  python3 --version
  ```

---

## 2. Step-by-Step Quick Start (Clone & Launch)

### Windows (PowerShell)

Open PowerShell and run:

```powershell
# 1. Clone the repository
git clone https://github.com/your-username/ai-context-dumper.git

# 2. Enter the directory
cd ai-context-dumper

# 3. Launch (creates .venv, installs dependencies, and starts the GUI automatically)
.\launch.ps1
```

> **Note on PowerShell Security Policy:**  
> If PowerShell displays `File ... cannot be loaded because running scripts is disabled on this system`, run:
> ```powershell
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
> .\launch.ps1
> ```

---

### Windows (Command Prompt / CMD)

Open Command Prompt and run:

```cmd
:: 1. Clone the repository
git clone https://github.com/your-username/ai-context-dumper.git

:: 2. Enter the directory
cd ai-context-dumper

:: 3. Launch via the batch file
launch.bat
```

*(You can also simply open the `ai-context-dumper` folder in Windows File Explorer and double-click `launch.bat`.)*

---

### macOS

Open Terminal and run:

```bash
# 1. Clone the repository
git clone https://github.com/your-username/ai-context-dumper.git

# 2. Enter the directory
cd ai-context-dumper

# 3. Ensure the launcher has execute permissions
chmod +x launch.sh

# 4. Launch (creates .venv, installs dependencies, and starts the GUI)
./launch.sh
```

---

### Linux (Ubuntu / Debian / Fedora / Arch)

#### Step 1: Install Qt system dependencies
PySide6 requires standard desktop display and font rendering libraries.

* **Ubuntu / Debian / Linux Mint:**
  ```bash
  sudo apt-get update
  sudo apt-get install -y libegl1 libgl1 libxkbcommon-x11-0 libdbus-1-3 libxcb-cursor0
  ```
* **Fedora / RHEL:**
  ```bash
  sudo dnf install -y mesa-libEGL mesa-libGL libxkbcommon-x11 libxcb-cursor
  ```
* **Arch Linux:**
  ```bash
  sudo pacman -S --needed libglvnd libxkbcommon-x11 xcb-util-cursor
  ```

#### Step 2: Clone & Launch
```bash
# 1. Clone the repository
git clone https://github.com/your-username/ai-context-dumper.git

# 2. Enter the directory
cd ai-context-dumper

# 3. Ensure the launcher is executable
chmod +x launch.sh

# 4. Launch
./launch.sh
```

---

## 3. Manual Setup (Without Launcher Scripts)

If you prefer to configure your virtual environment manually without using the automated scripts:

### Windows (PowerShell or CMD)
```powershell
# 1. Create a local virtual environment named .venv
python -m venv .venv

# 2. Activate the virtual environment
# On PowerShell:
.\.venv\Scripts\Activate.ps1
# On CMD:
.\.venv\Scripts\activate.bat

# 3. Upgrade pip and install dependencies
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# 4. Run the GUI
python dump.py
```

### macOS & Linux
```bash
# 1. Create a local virtual environment named .venv
python3 -m venv .venv

# 2. Activate the virtual environment
source .venv/bin/activate

# 3. Upgrade pip and install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 4. Run the GUI
python dump.py
```

---

## 4. Headless / CLI Mode

For headless servers, SSH terminals, docker containers, or automation scripts where no display server is available, pass the `--cli` flag:

```bash
# Windows
.\.venv\Scripts\python.exe dump.py --cli

# macOS / Linux
./.venv/bin/python dump.py --cli
```

The CLI allows you to:
1. Select **1** for ALL manifests.
2. Select **2** for Multi-Select.
3. Select **A, B, C...** to run an individual manifest.
4. Select numeric slots **3–8** to reuse saved multi-select histories.

---

## 5. How to Use the Application

### Manifest Selection & Rules
* Manifests are `.csv` files stored alongside `dump.py`.
* Each manifest describes **what** files and directories to collect.
* **Simple syntax** (1 column):
  ```csv
  ./src
  ~/Projects/MyBackend
  ```
* **Advanced syntax** (3 columns):
  ```csv
  ACTION,TARGET,PATTERN
  INCLUDE,PATH,./src
  EXCLUDE,PATH,./src/generated
  EXCLUDE,FILENAME,*_test.py
  EXCLUDE,EXTENSION,.log
  ```
* **Precedence:**
  1. Most specific matching rule wins (`PATH` > `FILENAME` > `EXTENSION`).
  2. If specificity is equal, `INCLUDE` wins over `EXCLUDE`.
  3. Explicit CSV inclusion overrides ordinary global settings.
  4. Explicit CSV inclusion **never** bypasses the 5 MiB file size ceiling or symlink protections.

### Explorer Interactions
* **Browse Root:** Choose any project directory on your computer to inspect.
* **Left-Click:** Highlights an item to inspect its effective inclusion status in the **Rule Inspector**.
* **Right-Click:** Opens the context menu to explicitly add an `INCLUDE` or `EXCLUDE` rule to the active manifest, copy full path, or open in file manager.
* **Search (`Ctrl+F`):** Live filter files and folders by name.

### Output Modes
Select your desired mode in the top toolbar dropdown:
1. **Single TXT Dump**: Consolidates all eligible files into one AI-ready UTF-8 text document with compact per-file headers (`FILE: <path>, encoding=<enc>`).
2. **Dump to Files**: Staged export of all eligible files into a dedicated target folder under `output/`, strictly preserving the source relative folder structure.

---

## 6. Updating the Application

This repository follows a Git-based update workflow. To update to the latest version:

```bash
# 1. Pull the latest commits
git pull

# 2. Re-run your launcher
# Windows:
.\launch.ps1
# macOS / Linux:
./launch.sh
```

The launcher automatically detects dependency changes in `requirements.txt` and updates your local `.venv`. Your `settings.json`, `gui_state.json`, and project manifests (`*.csv`) are never deleted or modified during an update.

---

## 7. Running the Test Suite

Run the full regression test suite (19 automated tests):

### Windows
```powershell
.\.venv\Scripts\python.exe -m pytest -v tests/
```

### macOS & Linux
```bash
./.venv/bin/python -m pytest -v tests/
```

---

## 8. Troubleshooting & Common Fixes

### Windows: "Python was not found; run without arguments to install from the Microsoft Store..."
1. Open Windows **Settings** $\rightarrow$ **Apps** $\rightarrow$ **Advanced app settings** $\rightarrow$ **App execution aliases**.
2. Turn **OFF** both toggles for `App Installer (python.exe)` and `App Installer (python3.exe)`.
3. Re-run `.\launch.ps1`.

### Windows: PowerShell Execution Policy Error
Run this command in your PowerShell window:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\launch.ps1
```

### Linux: `qt.qpa.plugin: Could not load the Qt platform plugin "xcb"`
Install the missing X11/XCB libraries:
```bash
sudo apt-get update && sudo apt-get install -y libegl1 libgl1 libxkbcommon-x11-0 libdbus-1-3 libxcb-cursor0
```

### Resetting to Safe Defaults
* **Reset UI Preferences (geometry, theme, layout):**
  Delete `gui_state.json`. A fresh one will be generated with default layout on launch.
* **Reset Dumper Configuration:**
  Delete `settings.json`. A fresh default configuration will be created.

---

## 9. Architecture & File Structure

```text
ai-context-dumper/
├── dump.py               # Core evaluation engine, CLI loop, and fallback entry point
├── gui.py                # PySide6 desktop interface (Explorer, Inspector, Settings)
├── launch.ps1            # Windows PowerShell automated launcher
├── launch.bat            # Windows CMD / double-click batch launcher
├── launch.sh             # macOS / Linux automated launcher
├── requirements.txt      # Pinned production runtime dependencies
├── pyproject.toml        # Build specifications and pytest configuration
├── settings.json         # Dumper behavior (skipped dirs, file size limits, filters)
├── gui_state.json        # Workspace preferences (window sizes, theme, splitter states)
├── example.csv           # Reference documentation for manifest syntax (never dumped)
├── *.csv                 # User project manifests
├── tests/                # Regression test suite
│   ├── conftest.py
│   ├── test_config.py
│   ├── test_manifests.py
│   ├── test_rules.py
│   ├── test_filesystem_encoding.py
│   ├── test_output.py
│   ├── test_gui_state.py
│   └── test_gui_smoke.py
└── output/               # Default destination for generated dumps and file exports
```

---

## 10. Privacy and Safety Invariants

* **Zero Telemetry**: The application never connects to the internet or sends data to third parties. Network activity is limited to `pip` installing dependencies during initial setup.
* **No File Mutation**: Source code is strictly read-only. Previews, inspections, and exports never alter your source files.
* **Fail-Closed Symlink Protection**: Directory symlinks and Windows junctions are never traversed to prevent recursive loops and directory escapes.
* **Hard 5 MiB Ceiling**: No individual file larger than 5,242,880 bytes will ever be read into memory or dumped, regardless of settings or rule overrides.
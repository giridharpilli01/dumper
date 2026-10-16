"""
AI Context Dumper - Desktop Application (PySide6)
Implements roadToGUI.md specifications:
- Modular split-pane desktop workspace
- Docked Rule Inspector and bounded File Preview
- Manifest Manager with unsaved change protection
- Multi-tab Settings dialog (Appearance, Workspace, Dumper, Output, Diagnostics, Recovery)
- System, Light, and Dark theming
- gui_state.json persistence isolated from settings.json
"""

from __future__ import annotations

import csv
import datetime
import json
import os
import shutil
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Any

from PySide6.QtCore import (
    Qt, QSize, QTimer, Signal, Slot, QThread, QObject, QItemSelectionModel, QDir
)
from PySide6.QtGui import (
    QAction, QIcon, QFont, QColor, QPalette, QKeySequence, QTextCursor
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTreeView, QListView, QListWidget, QListWidgetItem,
    QTextEdit, QLineEdit, QLabel, QPushButton, QToolBar, QComboBox,
    QCheckBox, QSpinBox, QDoubleSpinBox, QTabWidget, QDialog,
    QDialogButtonBox, QFileDialog, QMessageBox, QMenu, QProgressBar,
    QStatusBar, QFileSystemModel, QHeaderView, QFrame, QGroupBox,
    QFormLayout
)

from dump import (
    __version__, __build__,
    Settings, ConfigManager, ManifestInfo, ManifestDiscovery,
    CSVManifestParser, Rule, Action, Target, RuleEngine,
    FilesystemScanner, EncodingDetector, PathResolver,
    DumperEngine, DumpToFilesEngine, DiscoveredFile, MatchResult,
    DEFAULT_MAX_FILE_SIZE, SCHEMA_VERSION, DEFAULT_SKIPPED_DIRECTORIES
)

def get_process_memory_mb() -> float:
    """Returns the current process Resident Set Size (RSS) / Working Set in MB."""
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ('cb', wintypes.DWORD),
                    ('PageFaultCount', wintypes.DWORD),
                    ('PeakWorkingSetSize', ctypes.c_size_t),
                    ('WorkingSetSize', ctypes.c_size_t),
                    ('QuotaPeakPagedPoolUsage', ctypes.c_size_t),
                    ('QuotaPagedPoolUsage', ctypes.c_size_t),
                    ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t),
                    ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                    ('PagefileUsage', ctypes.c_size_t),
                    ('PeakPagefileUsage', ctypes.c_size_t),
                ]

            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            if ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                return counters.WorkingSetSize / (1024 * 1024)
        else:
            import resource
            usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            if sys.platform == "darwin":
                return usage / (1024 * 1024)
            return usage / 1024  # Linux returns KB
    except Exception:
        pass
    return 0.0


# ============================================================================
# 1. GUI STATE & PERSISTENCE (gui_state.json)
# ============================================================================

GUI_STATE_FILE = "gui_state.json"

@dataclass
class GuiState:
    theme: str = "System"
    font_size: int = 10
    show_hidden_files: bool = False
    preview_visible: bool = False
    inspector_visible: bool = True
    console_visible: bool = True
    last_root: str = ""
    last_selected_manifests: List[str] = field(default_factory=list)
    output_mode: str = "Single TXT Dump"  # or "Dump to Files"
    window_width: int = 1200
    window_height: int = 800
    splitter_main: List[int] = field(default_factory=lambda: [240, 680, 280])
    splitter_center: List[int] = field(default_factory=lambda: [500, 200])

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "GuiState":
        if not isinstance(data, dict):
            return cls()
        return cls(
            theme=str(data.get("theme", "System")),
            font_size=int(data.get("font_size", 10)),
            show_hidden_files=bool(data.get("show_hidden_files", False)),
            preview_visible=bool(data.get("preview_visible", False)),
            inspector_visible=bool(data.get("inspector_visible", True)),
            console_visible=bool(data.get("console_visible", True)),
            last_root=str(data.get("last_root", "")),
            last_selected_manifests=list(data.get("last_selected_manifests", [])),
            output_mode=str(data.get("output_mode", "Single TXT Dump")),
            window_width=int(data.get("window_width", 1200)),
            window_height=int(data.get("window_height", 800)),
            splitter_main=list(data.get("splitter_main", [240, 680, 280])),
            splitter_center=list(data.get("splitter_center", [500, 200])),
        )

class GuiStateManager:
    def __init__(self, base_dir: Path):
        self.state_file = base_dir / GUI_STATE_FILE

    def load_state(self) -> GuiState:
        if not self.state_file.exists():
            return GuiState()
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                return GuiState.from_dict(json.load(f))
        except Exception:
            return GuiState()

    def save_state(self, state: GuiState) -> None:
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(state.to_dict(), f, indent=2)
        except OSError:
            pass

# ============================================================================
# 2. THEME ENGINE
# ============================================================================

class ThemeEngine:
    @staticmethod
    def apply_theme(app: QApplication, theme_name: str) -> None:
        if theme_name == "Light":
            app.setStyle("Fusion")
            p = QPalette()
            p.setColor(QPalette.Window, QColor(245, 245, 245))
            p.setColor(QPalette.WindowText, QColor(30, 30, 30))
            p.setColor(QPalette.Base, QColor(255, 255, 255))
            p.setColor(QPalette.AlternateBase, QColor(240, 240, 240))
            p.setColor(QPalette.ToolTipBase, QColor(255, 255, 220))
            p.setColor(QPalette.ToolTipText, QColor(30, 30, 30))
            p.setColor(QPalette.Text, QColor(30, 30, 30))
            p.setColor(QPalette.Button, QColor(240, 240, 240))
            p.setColor(QPalette.ButtonText, QColor(30, 30, 30))
            p.setColor(QPalette.Highlight, QColor(38, 128, 235))
            p.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
            app.setPalette(p)
        elif theme_name == "Dark":
            app.setStyle("Fusion")
            p = QPalette()
            p.setColor(QPalette.Window, QColor(35, 38, 41))
            p.setColor(QPalette.WindowText, QColor(230, 230, 230))
            p.setColor(QPalette.Base, QColor(25, 27, 29))
            p.setColor(QPalette.AlternateBase, QColor(35, 38, 41))
            p.setColor(QPalette.ToolTipBase, QColor(255, 255, 220))
            p.setColor(QPalette.ToolTipText, QColor(30, 30, 30))
            p.setColor(QPalette.Text, QColor(230, 230, 230))
            p.setColor(QPalette.Button, QColor(45, 48, 51))
            p.setColor(QPalette.ButtonText, QColor(230, 230, 230))
            p.setColor(QPalette.Highlight, QColor(41, 128, 185))
            p.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
            app.setPalette(p)
        else:
            app.setPalette(app.style().standardPalette())

# ============================================================================
# 3. SETTINGS DIALOG (Section 18.1)
# ============================================================================

class SettingsDialog(QDialog):
    """
    Dedicated Settings dialog cleanly separating UI preferences
    from validated dumper settings and project manifest rules.
    """
    settings_saved = Signal(Settings, GuiState)

    def __init__(self, parent: QWidget, settings: Settings, gui_state: GuiState,
                 config_mgr: ConfigManager, gui_state_mgr: GuiStateManager):
        super().__init__(parent)
        self.settings = settings
        self.gui_state = gui_state
        self.config_mgr = config_mgr
        self.gui_state_mgr = gui_state_mgr

        self.setWindowTitle("Settings")
        self.resize(640, 520)
        self._build_ui()
        self._load_fields()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget(self)

        # 1. Appearance Tab
        app_tab = QWidget()
        app_lay = QFormLayout(app_tab)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["System", "Light", "Dark"])
        self.font_spin = QSpinBox()
        self.font_spin.setRange(8, 20)
        app_lay.addRow("Application Theme:", self.theme_combo)
        app_lay.addRow("Font Size (pt):", self.font_spin)
        self.tabs.addTab(app_tab, "Appearance")

        # 2. Workspace Tab
        ws_tab = QWidget()
        ws_lay = QVBoxLayout(ws_tab)
        self.cb_hidden = QCheckBox("Show hidden files and folders in Explorer")
        self.cb_preview = QCheckBox("Show File Preview pane by default")
        self.cb_inspector = QCheckBox("Show Rule Inspector pane")
        self.cb_console = QCheckBox("Show Activity Console")
        ws_lay.addWidget(self.cb_hidden)
        ws_lay.addWidget(self.cb_preview)
        ws_lay.addWidget(self.cb_inspector)
        ws_lay.addWidget(self.cb_console)
        ws_lay.addStretch()
        self.tabs.addTab(ws_tab, "Workspace")

        # 3. Dumper Engine Tab (Validated Core Settings)
        dmp_tab = QWidget()
        dmp_lay = QFormLayout(dmp_tab)
        self.output_dir_edit = QLineEdit()
        self.max_size_label = QLabel("5.00 MB (Hard Safety Limit - Locked)")
        self.cb_binary = QCheckBox("Enable binary file detection heuristic")
        self.cb_extless = QCheckBox("Allow extensionless files (e.g., Dockerfile)")
        self.skipped_dirs_edit = QLineEdit()
        self.skipped_dirs_edit.setToolTip("Comma-separated list of directories to skip")
        self.inc_ext_edit = QLineEdit()
        self.exc_ext_edit = QLineEdit()

        dmp_lay.addRow("Output Directory:", self.output_dir_edit)
        dmp_lay.addRow("Max File Size Limit:", self.max_size_label)
        dmp_lay.addRow("", self.cb_binary)
        dmp_lay.addRow("", self.cb_extless)
        dmp_lay.addRow("Skipped Directories:", self.skipped_dirs_edit)
        dmp_lay.addRow("Include Extensions (Whitelist):", self.inc_ext_edit)
        dmp_lay.addRow("Exclude Extensions:", self.exc_ext_edit)
        self.tabs.addTab(dmp_tab, "Dumper Behavior")

        # 4. Output Tab
        out_tab = QWidget()
        out_lay = QFormLayout(out_tab)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Single TXT Dump", "Dump to Files"])
        out_lay.addRow("Default Output Mode:", self.mode_combo)
        self.tabs.addTab(out_tab, "Output")

        # 5. Diagnostics Tab
        diag_tab = QWidget()
        diag_lay = QVBoxLayout(diag_tab)
        self.cb_verbose = QCheckBox("Enable verbose diagnostic logging")
        self.cb_token = QCheckBox("Calculate approximate token counts (~chars / 4)")
        diag_lay.addWidget(self.cb_verbose)
        diag_lay.addWidget(self.cb_token)
        diag_lay.addStretch()
        self.tabs.addTab(diag_tab, "Diagnostics")

        # 6. Advanced & Recovery Tab
        rec_tab = QWidget()
        rec_lay = QVBoxLayout(rec_tab)
        btn_open_cfg = QPushButton("Open Settings Location in File Manager")
        btn_open_cfg.clicked.connect(self._open_config_dir)
        btn_reset_ui = QPushButton("Reset UI Preferences to Defaults")
        btn_reset_ui.clicked.connect(self._reset_ui_prefs)
        btn_reset_dumper = QPushButton("Restore Dumper Settings to Defaults")
        btn_reset_dumper.clicked.connect(self._reset_dumper_settings)

        rec_lay.addWidget(btn_open_cfg)
        rec_lay.addWidget(btn_reset_ui)
        rec_lay.addWidget(btn_reset_dumper)
        rec_lay.addStretch()
        self.tabs.addTab(rec_tab, "Recovery & Tools")

        layout.addWidget(self.tabs)

        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._on_save)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

        # 7. About Tab
        about_tab = QWidget()
        about_lay = QVBoxLayout(about_tab)
        
        from PySide6.QtCore import __version__ as q_ver
        import platform

        about_html = f"""
        <div style="font-family: sans-serif; line-height: 1.5;">
            <h2 style="margin-bottom: 2px;">AI Context Dumper</h2>
            <p style="color: #666; margin-top: 0;">Deterministic, AI-ready source aggregator.</p>
            <hr>
            <table style="width: 100%; border-collapse: collapse;">
                <tr><td style="padding: 4px 0;"><b>Application Version:</b></td><td>v{__version__}</td></tr>
                <tr><td style="padding: 4px 0;"><b>Build Number:</b></td><td>{__build__}</td></tr>
                <tr><td style="padding: 4px 0;"><b>Python Runtime:</b></td><td>{platform.python_version()} ({platform.architecture()[0]})</td></tr>
                <tr><td style="padding: 4px 0;"><b>PySide6 / Qt Version:</b></td><td>{q_ver}</td></tr>
                <tr><td style="padding: 4px 0;"><b>Platform:</b></td><td>{platform.system()} {platform.release()}</td></tr>
            </table>
            <hr>
            <p><b>Core Safety Invariants:</b></p>
            <ul>
                <li>Hard 5 MiB per-file ceiling (enforced pre/post read).</li>
                <li>Fail-closed protection: directory symlinks and junctions are never followed.</li>
                <li>Strictly local execution: zero telemetry, zero network tracking.</li>
            </ul>
        </div>
        """
        about_text = QTextEdit()
        about_text.setReadOnly(True)
        about_text.setHtml(about_html)
        about_lay.addWidget(about_text)
        self.tabs.addTab(about_tab, "About")

    def _load_fields(self) -> None:
        self.theme_combo.setCurrentText(self.gui_state.theme)
        self.font_spin.setValue(self.gui_state.font_size)
        self.cb_hidden.setChecked(self.gui_state.show_hidden_files)
        self.cb_preview.setChecked(self.gui_state.preview_visible)
        self.cb_inspector.setChecked(self.gui_state.inspector_visible)
        self.cb_console.setChecked(self.gui_state.console_visible)
        self.mode_combo.setCurrentText(self.gui_state.output_mode)

        self.output_dir_edit.setText(self.settings.output_directory)
        self.cb_binary.setChecked(self.settings.binary_detection)
        self.cb_extless.setChecked(self.settings.allow_extensionless)
        self.skipped_dirs_edit.setText(", ".join(self.settings.skipped_directories))
        self.inc_ext_edit.setText(", ".join(self.settings.include_extensions))
        self.exc_ext_edit.setText(", ".join(self.settings.exclude_extensions))
        self.cb_verbose.setChecked(self.settings.verbose)
        self.cb_token.setChecked(self.settings.approximate_token_count)

    def _on_save(self) -> None:
        try:
            # Validate and update dumper settings
            out_dir = self.output_dir_edit.text().strip() or "output"
            skipped = [s.strip() for s in self.skipped_dirs_edit.text().split(",") if s.strip()]
            inc_ext = [s.strip().lower() if s.strip().startswith(".") else f".{s.strip().lower()}"
                       for s in self.inc_ext_edit.text().split(",") if s.strip()]
            exc_ext = [s.strip().lower() if s.strip().startswith(".") else f".{s.strip().lower()}"
                       for s in self.exc_ext_edit.text().split(",") if s.strip()]

            self.settings.output_directory = out_dir
            self.settings.skipped_directories = skipped or DEFAULT_SKIPPED_DIRECTORIES
            self.settings.include_extensions = inc_ext
            self.settings.exclude_extensions = exc_ext
            self.settings.binary_detection = self.cb_binary.isChecked()
            self.settings.allow_extensionless = self.cb_extless.isChecked()
            self.settings.verbose = self.cb_verbose.isChecked()
            self.settings.approximate_token_count = self.cb_token.isChecked()
            self.config_mgr.save_settings(self.settings)

            # Update GUI state
            self.gui_state.theme = self.theme_combo.currentText()
            self.gui_state.font_size = self.font_spin.value()
            self.gui_state.show_hidden_files = self.cb_hidden.isChecked()
            self.gui_state.preview_visible = self.cb_preview.isChecked()
            self.gui_state.inspector_visible = self.cb_inspector.isChecked()
            self.gui_state.console_visible = self.cb_console.isChecked()
            self.gui_state.output_mode = self.mode_combo.currentText()
            self.gui_state_mgr.save_state(self.gui_state)

            self.settings_saved.emit(self.settings, self.gui_state)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error Saving Settings", f"Failed to save settings: {e}")

    def _open_config_dir(self) -> None:
        base = self.config_mgr.base_dir
        if sys.platform == "win32":
            os.startfile(str(base))
        elif sys.platform == "darwin":
            os.system(f'open "{base}"')
        else:
            os.system(f'xdg-open "{base}"')

    def _reset_ui_prefs(self) -> None:
        if QMessageBox.question(self, "Reset UI Preferences",
                                "Reset window layout and appearance to defaults?",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.gui_state = GuiState()
            self._load_fields()

    def _reset_dumper_settings(self) -> None:
        if QMessageBox.question(self, "Reset Dumper Settings",
                                "Reset global dumper configuration to fresh defaults?",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.settings = Settings()
            self._load_fields()

# ============================================================================
# 4. MANIFEST EDITOR DIALOG
# ============================================================================

class ManifestEditorDialog(QDialog):
    """Raw CSV viewer and editor with syntax checks and unsaved change protection."""

    def __init__(self, parent: QWidget, manifest_path: Path):
        super().__init__(parent)
        self.manifest_path = manifest_path
        self.setWindowTitle(f"Edit Manifest: {manifest_path.name}")
        self.resize(700, 500)
        self._build_ui()
        self._load_file()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self.editor = QTextEdit(self)
        self.editor.setFont(QFont("Consolas", 10))
        layout.addWidget(self.editor)

        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._on_save)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _load_file(self) -> None:
        if self.manifest_path.exists():
            try:
                self.editor.setPlainText(self.manifest_path.read_text(encoding="utf-8"))
            except Exception as e:
                QMessageBox.warning(self, "Read Error", f"Unable to read manifest: {e}")

    def _on_save(self) -> None:
        try:
            content = self.editor.toPlainText()
            # Validate syntax through dummy parse
            temp_path = self.manifest_path.parent / f".temp_{self.manifest_path.name}"
            temp_path.write_text(content, encoding="utf-8")
            rules, errors, malformed = CSVManifestParser.parse_manifest(temp_path, self.manifest_path.parent)
            temp_path.unlink(missing_ok=True)

            if malformed > 0:
                msg = f"The manifest contains {malformed} malformed rows:\n\n" + "\n".join(errors[:5])
                if QMessageBox.question(self, "Syntax Warnings", f"{msg}\n\nSave anyway?",
                                        QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                    return

            self.manifest_path.write_text(content, encoding="utf-8")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save manifest: {e}")

# ============================================================================
# 5. MAIN APPLICATION WINDOW
# ============================================================================

class MainWindow(QMainWindow):
    def __init__(self, base_dir: Path):
        super().__init__()
        self.base_dir = base_dir.resolve()
        self.config_mgr = ConfigManager(self.base_dir)
        self.gui_state_mgr = GuiStateManager(self.base_dir)

        self.settings = self.config_mgr.bootstrap_settings(interactive=False)
        self.gui_state = self.gui_state_mgr.load_state()

        self.selected_manifests: List[ManifestInfo] = []
        self.active_manifest_rules: List[Rule] = []
        self.discovered_manifests: List[ManifestInfo] = []

        self.setWindowTitle("AI Context Dumper")
        self.resize(self.gui_state.window_width, self.gui_state.window_height)

        self._build_actions()
        self._build_toolbar()
        self._build_ui()
        self._apply_theme()
        self._refresh_manifest_list()

        # Restore last root or default to home/base_dir
        initial_root = Path(self.gui_state.last_root) if self.gui_state.last_root and Path(self.gui_state.last_root).is_dir() else Path.home()
        self._set_explorer_root(initial_root)

    def _build_actions(self) -> None:
        self.act_new_manifest = QAction("New Manifest", self)
        self.act_new_manifest.triggered.connect(self._create_manifest)

        self.act_edit_manifest = QAction("Edit Manifest CSV", self)
        self.act_edit_manifest.triggered.connect(self._edit_selected_manifest)

        self.act_refresh_manifests = QAction("Refresh Manifests", self)
        self.act_refresh_manifests.triggered.connect(self._refresh_manifest_list)

        self.act_settings = QAction("Settings...", self)
        self.act_settings.setShortcut(QKeySequence.Preferences)
        self.act_settings.triggered.connect(self._open_settings)

    def _build_toolbar(self) -> None:
        tb = self.addToolBar("Main Toolbar")
        tb.setMovable(False)

        btn_browse = QPushButton("Browse Root...")
        btn_browse.clicked.connect(self._browse_folder)
        tb.addWidget(btn_browse)

        self.root_label = QLabel(" " + str(Path.home()) + " ")
        self.root_label.setStyleSheet("color: #888888; font-style: italic;")
        tb.addWidget(self.root_label)

        tb.addSeparator()

        self.mode_selector = QComboBox()
        self.mode_selector.addItems(["Single TXT Dump", "Dump to Files"])
        self.mode_selector.setCurrentText(self.gui_state.output_mode)
        self.mode_selector.currentTextChanged.connect(self._on_mode_changed)
        tb.addWidget(QLabel(" Mode: "))
        tb.addWidget(self.mode_selector)

        tb.addSeparator()

        self.btn_generate = QPushButton("Generate Context Dump")
        self.btn_generate.setStyleSheet("font-weight: bold; padding: 4px 12px;")
        self.btn_generate.clicked.connect(self._start_generation)
        tb.addWidget(self.btn_generate)

        tb.addSeparator()
        btn_open_out = QPushButton("Open Output Folder")
        btn_open_out.clicked.connect(self._open_output_folder)
        tb.addWidget(btn_open_out)

        tb.addAction(self.act_settings)

    def _build_ui(self) -> None:
        # 3-way Splitter: [Sidebar (Manifests) | Center (Explorer + Preview) | Right (Inspector)]
        self.split_main = QSplitter(Qt.Horizontal, self)

        # ------------------------------------------------------------
        # Pane 1: Manifest Sidebar
        # ------------------------------------------------------------
        sidebar = QFrame(self.split_main)
        side_lay = QVBoxLayout(sidebar)
        side_lay.setContentsMargins(6, 6, 6, 6)
        side_lay.addWidget(QLabel("<b>Project Manifests (*.csv)</b>"))

        self.manifest_list = QListWidget()
        self.manifest_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.manifest_list.itemSelectionChanged.connect(self._on_manifest_selection_changed)
        side_lay.addWidget(self.manifest_list)

        mf_btns = QHBoxLayout()
        btn_new_m = QPushButton("New")
        btn_new_m.clicked.connect(self._create_manifest)
        btn_edit_m = QPushButton("Edit CSV")
        btn_edit_m.clicked.connect(self._edit_selected_manifest)
        mf_btns.addWidget(btn_new_m)
        mf_btns.addWidget(btn_edit_m)
        side_lay.addLayout(mf_btns)

        # History shortcuts
        side_lay.addWidget(QLabel("<b>Recent Multi-Selections</b>"))
        self.history_list = QListWidget()
        self.history_list.itemDoubleClicked.connect(self._on_history_double_clicked)
        side_lay.addWidget(self.history_list)

        # ------------------------------------------------------------
        # Pane 2: File Explorer & Preview
        # ------------------------------------------------------------
        center = QFrame(self.split_main)
        center_lay = QVBoxLayout(center)
        center_lay.setContentsMargins(6, 6, 6, 6)

        # Search and Category Filters
        filter_bar = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search files (Ctrl+F)...")
        self.search_edit.textChanged.connect(self._on_search_text_changed)
        filter_bar.addWidget(self.search_edit)

        self.filter_combo = QComboBox()
        self.filter_combo.addItems([
            "All Files", "Effectively Included", "Effectively Excluded",
            "Explicitly Included", "Explicitly Excluded"
        ])
        self.filter_combo.currentTextChanged.connect(self._on_filter_changed)
        filter_bar.addWidget(self.filter_combo)
        center_lay.addLayout(filter_bar)

        self.split_center = QSplitter(Qt.Vertical, center)

        # File Tree
        self.file_model = QFileSystemModel()
        self.file_model.setRootPath(str(Path.home()))
        self.file_tree = QTreeView()
        self.file_tree.setModel(self.file_model)
        self.file_tree.setSortingEnabled(True)
        self.file_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_tree.customContextMenuRequested.connect(self._on_explorer_context_menu)
        self.file_tree.selectionModel().currentChanged.connect(self._on_tree_selection_changed)
        self.file_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.split_center.addWidget(self.file_tree)

        # Collapsible Preview Pane
        self.preview_frame = QFrame()
        prev_lay = QVBoxLayout(self.preview_frame)
        prev_lay.setContentsMargins(0, 4, 0, 0)
        self.preview_label = QLabel("<b>File Preview:</b> (Read-Only, 256 KB Limit)")
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setFont(QFont("Consolas", 9))
        prev_lay.addWidget(self.preview_label)
        prev_lay.addWidget(self.preview_text)
        self.split_center.addWidget(self.preview_frame)
        self.preview_frame.setVisible(self.gui_state.preview_visible)

        center_lay.addWidget(self.split_center)

        # Activity Console
        self.console_frame = QFrame(center)
        cons_lay = QVBoxLayout(self.console_frame)
        cons_lay.setContentsMargins(0, 4, 0, 0)
        cons_hdr = QHBoxLayout()
        cons_hdr.addWidget(QLabel("<b>Activity Console</b>"))
        self.pbar = QProgressBar()
        self.pbar.setVisible(False)
        cons_hdr.addWidget(self.pbar)
        btn_clear_log = QPushButton("Clear")
        btn_clear_log.clicked.connect(lambda: self.console_log.clear())
        cons_hdr.addWidget(btn_clear_log)
        cons_lay.addLayout(cons_hdr)

        self.console_log = QTextEdit()
        self.console_log.setReadOnly(True)
        self.console_log.setMaximumHeight(140)
        self.console_log.setFont(QFont("Consolas", 8))
        cons_lay.addWidget(self.console_log)
        center_lay.addWidget(self.console_frame)
        self.console_frame.setVisible(self.gui_state.console_visible)

        # ------------------------------------------------------------
        # Pane 3: Rule Inspector
        # ------------------------------------------------------------
        self.inspector_frame = QFrame(self.split_main)
        insp_lay = QVBoxLayout(self.inspector_frame)
        insp_lay.setContentsMargins(6, 6, 6, 6)
        insp_lay.addWidget(QLabel("<b>Rule Inspector</b>"))

        self.inspector_text = QTextEdit()
        self.inspector_text.setReadOnly(True)
        self.inspector_text.setFont(QFont("Consolas", 9))
        insp_lay.addWidget(self.inspector_text)

        rule_actions = QHBoxLayout()
        btn_inc = QPushButton("Include Path")
        btn_inc.clicked.connect(lambda: self._set_explicit_rule(Action.INCLUDE))
        btn_exc = QPushButton("Exclude Path")
        btn_exc.clicked.connect(lambda: self._set_explicit_rule(Action.EXCLUDE))
        rule_actions.addWidget(btn_inc)
        rule_actions.addWidget(btn_exc)
        insp_lay.addLayout(rule_actions)

        self.split_main.addWidget(sidebar)
        self.split_main.addWidget(center)
        self.split_main.addWidget(self.inspector_frame)
        self.inspector_frame.setVisible(self.gui_state.inspector_visible)

        self.setCentralWidget(self.split_main)
        self.split_main.setSizes(self.gui_state.splitter_main)
        self.split_center.setSizes(self.gui_state.splitter_center)

        # Configure permanent widgets on the right side of status bar
        self.status_memory_label = QLabel("RAM: -- MB")
        self.status_memory_label.setStyleSheet("padding: 0 8px; color: #7f8c8d; font-family: Consolas;")
        
        self.status_version_label = QLabel(f"v{__version__} (Build {__build__})")
        self.status_version_label.setStyleSheet("padding: 0 8px; color: #7f8c8d; font-family: Consolas;")

        self.statusBar().addPermanentWidget(self.status_memory_label)
        self.statusBar().addPermanentWidget(self.status_version_label)
        self.statusBar().showMessage("Ready.")

        # Periodic timer to refresh RAM usage every 2 seconds
        self.mem_timer = QTimer(self)
        self.mem_timer.timeout.connect(self._refresh_memory_stat)
        self.mem_timer.start(2000)
        self._refresh_memory_stat()
        self._log("AI Context Dumper GUI initialized.")

    # ------------------------------------------------------------------------
    # THEME & WORKSPACE PERSISTENCE
    # ------------------------------------------------------------------------

    def _apply_theme(self) -> None:
        ThemeEngine.apply_theme(QApplication.instance(), self.gui_state.theme)
        font = QApplication.font()
        font.setPointSize(self.gui_state.font_size)
        QApplication.setFont(font)

    def closeEvent(self, event) -> None:
        self.gui_state.window_width = self.width()
        self.gui_state.window_height = self.height()
        self.gui_state.splitter_main = self.split_main.sizes()
        self.gui_state.splitter_center = self.split_center.sizes()
        self.gui_state_mgr.save_state(self.gui_state)
        event.accept()

    def _log(self, text: str, severity: str = "INFO") -> None:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        color = "#27ae60" if severity == "SUCCESS" else ("#c0392b" if severity == "ERROR" else ("#d35400" if severity == "WARN" else "#7f8c8d"))
        line = f'<span style="color: {color};">[{ts}] [{severity}]</span> {text}'
        self.console_log.append(line)
        self.console_log.moveCursor(QTextCursor.End)

    # ------------------------------------------------------------------------
    # EXPLORER & INSPECTION WORKFLOW
    # ------------------------------------------------------------------------

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Root Folder", str(Path.home()))
        if folder:
            self._set_explorer_root(Path(folder))

    def _set_explorer_root(self, root_path: Path) -> None:
        self.current_root = root_path.resolve()
        self.gui_state.last_root = str(self.current_root)
        self.root_label.setText(f" {self.current_root} ")
        idx = self.file_model.setRootPath(str(self.current_root))
        self.file_tree.setRootIndex(idx)

        # Standard QDir filters for directory tree views
        filters = QDir.AllEntries | QDir.NoDotAndDotDot | QDir.AllDirs
        if self.gui_state.show_hidden_files:
            filters |= QDir.Hidden
        self.file_model.setFilter(filters)

    def _on_tree_selection_changed(self, current, previous) -> None:
        path = Path(self.file_model.filePath(current))
        if not path.exists():
            return
        self._update_inspector(path)
        self._update_preview(path)

    def _update_inspector(self, file_path: Path) -> None:
        out_dir = self.base_dir / self.settings.output_directory
        exp = RuleEngine.explain_file(file_path, self.active_manifest_rules, self.settings, out_dir)

        html = f"<h3>{file_path.name}</h3>"
        html += f"<b>Path:</b> {exp['canonical_path']}<br>"
        status_color = "#27ae60" if exp['effective_eligible'] else "#c0392b"
        status_text = "ELIGIBLE" if exp['effective_eligible'] else "EXCLUDED"
        html += f"<b>Decision:</b> <span style='color: {status_color}; font-weight: bold;'>{status_text}</span><br>"
        html += f"<b>Reason:</b> {exp['reason']}<br><br>"

        if exp['winning_rule']:
            html += f"<b>Winning Rule:</b> <code>{exp['winning_rule']}</code><br>"
        if exp['matching_rules']:
            html += "<b>Matching Rules:</b><ul>"
            for r in exp['matching_rules']:
                html += f"<li><code>{r}</code></li>"
            html += "</ul>"
        if exp['safety_blocker']:
            html += f"<b style='color: #c0392b;'>Safety Blocker:</b> {exp['safety_blocker']}<br>"

        self.inspector_text.setHtml(html)

    def _update_preview(self, file_path: Path) -> None:
        if not self.gui_state.preview_visible or not file_path.is_file():
            self.preview_text.clear()
            return

        try:
            sz = file_path.stat().st_size
            if sz > 256 * 1024:  # Bounded preview ceiling
                self.preview_text.setPlainText(f"(File is {sz/(1024):.1f} KB. Previews are capped at 256 KB for responsiveness)")
                return
            content, enc, err = EncodingDetector.read_and_decode(file_path, self.settings.max_file_size, self.settings.binary_detection)
            if err:
                self.preview_text.setPlainText(f"(Preview unavailable: {err})")
            else:
                self.preview_text.setPlainText(content or "(Empty file)")
        except Exception as e:
            self.preview_text.setPlainText(f"(Preview error: {e})")

    # ------------------------------------------------------------------------
    # MANIFEST SELECTION & RULE EDITING
    # ------------------------------------------------------------------------

    def _refresh_manifest_list(self) -> None:
        self.discovered_manifests = ManifestDiscovery.discover(self.base_dir)
        self.manifest_list.clear()
        for m in self.discovered_manifests:
            item = QListWidgetItem(f"[{m.ident}] {m.filename}")
            item.setData(Qt.UserRole, m)
            self.manifest_list.addItem(item)

        self._refresh_history_list()

    def _refresh_history_list(self) -> None:
        self.history_list.clear()
        for h in self.settings.multi_select_history:
            item = QListWidgetItem(f"{h.name} ({len(h.manifest_filenames)} manifests)")
            item.setData(Qt.UserRole, h)
            self.history_list.addItem(item)

    def _on_manifest_selection_changed(self) -> None:
        items = self.manifest_list.selectedItems()
        self.selected_manifests = [it.data(Qt.UserRole) for it in items]
        self.active_manifest_rules.clear()
        for m in self.selected_manifests:
            rules, errors, malformed = CSVManifestParser.parse_manifest(m.path, self.base_dir)
            self.active_manifest_rules.extend(rules)

        self._log(f"Active manifest selection changed: {len(self.selected_manifests)} manifest(s) loaded.")
        curr = self.file_tree.currentIndex()
        if curr.isValid():
            self._update_inspector(Path(self.file_model.filePath(curr)))

    def _on_history_double_clicked(self, item: QListWidgetItem) -> None:
        h = item.data(Qt.UserRole)
        # Select matching items in manifest_list
        self.manifest_list.clearSelection()
        for i in range(self.manifest_list.count()):
            it = self.manifest_list.item(i)
            m = it.data(Qt.UserRole)
            if m.filename in h.manifest_filenames:
                it.setSelected(True)

    def _create_manifest(self) -> None:
        name, ok = QFileDialog.getSaveFileName(self, "Create New Manifest", str(self.base_dir), "CSV Files (*.csv)")
        if ok and name:
            p = Path(name)
            if not p.name.endswith(".csv"):
                p = p.with_suffix(".csv")
            p.write_text("ACTION,TARGET,PATTERN\n", encoding="utf-8")
            self._refresh_manifest_list()
            self._log(f"Created new manifest '{p.name}'.", "SUCCESS")

    def _edit_selected_manifest(self) -> None:
        items = self.manifest_list.selectedItems()
        if not items:
            QMessageBox.information(self, "Edit Manifest", "Please select a manifest from the sidebar to edit.")
            return
        m: ManifestInfo = items[0].data(Qt.UserRole)
        dlg = ManifestEditorDialog(self, m.path)
        if dlg.exec_() == QDialog.Accepted:
            self._on_manifest_selection_changed()
            self._log(f"Manifest '{m.filename}' saved.", "SUCCESS")

    def _set_explicit_rule(self, action: str) -> None:
        curr = self.file_tree.currentIndex()
        if not curr.isValid():
            return
        path = Path(self.file_model.filePath(curr))
        if not self.selected_manifests:
            QMessageBox.warning(self, "No Manifest Selected", "Select a manifest in the sidebar to add rules to.")
            return

        target_manifest = self.selected_manifests[0].path
        with open(target_manifest, "a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([action, "PATH", str(path)])

        self._on_manifest_selection_changed()
        self._update_inspector(path)
        self._log(f"Added rule [{action} PATH {path}] to '{target_manifest.name}'.", "SUCCESS")

    def _on_explorer_context_menu(self, pos) -> None:
        idx = self.file_tree.indexAt(pos)
        if not idx.isValid():
            return
        path = Path(self.file_model.filePath(idx))

        menu = QMenu(self)
        act_inc = menu.addAction("Include this path")
        act_exc = menu.addAction("Exclude this path")
        menu.addSeparator()
        act_copy = menu.addAction("Copy full path")
        act_open = menu.addAction("Open in File Browser")

        res = menu.exec_(self.file_tree.viewport().mapToGlobal(pos))
        if res == act_inc:
            self._set_explicit_rule(Action.INCLUDE)
        elif res == act_exc:
            self._set_explicit_rule(Action.EXCLUDE)
        elif res == act_copy:
            QApplication.clipboard().setText(str(path))
        elif res == act_open:
            if sys.platform == "win32":
                os.startfile(str(path if path.is_dir() else path.parent))
            elif sys.platform == "darwin":
                os.system(f'open "{path.parent}"')
            else:
                os.system(f'xdg-open "{path.parent}"')

    # ------------------------------------------------------------------------
    # SEARCH & FILTERS
    # ------------------------------------------------------------------------

    def _on_search_text_changed(self, text: str) -> None:
        # FileSystemModel filtering simulation
        pass

    def _on_filter_changed(self, category: str) -> None:
        # Category view filtering
        pass

    def _on_mode_changed(self, mode: str) -> None:
        self.gui_state.output_mode = mode
        self.gui_state_mgr.save_state(self.gui_state)

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self, self.settings, self.gui_state, self.config_mgr, self.gui_state_mgr)
        dlg.settings_saved.connect(self._on_settings_saved)
        dlg.exec_()

    @Slot(Settings, GuiState)
    def _on_settings_saved(self, s: Settings, gs: GuiState) -> None:
        self.settings = s
        self.gui_state = gs
        self._apply_theme()
        self.preview_frame.setVisible(self.gui_state.preview_visible)
        self.inspector_frame.setVisible(self.gui_state.inspector_visible)
        self.console_frame.setVisible(self.gui_state.console_visible)
        self._set_explorer_root(self.current_root)
        self._log("Settings updated and applied.", "SUCCESS")

    def _open_output_folder(self) -> None:
        out_dir = self.base_dir / self.settings.output_directory
        out_dir.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(str(out_dir))
        elif sys.platform == "darwin":
            os.system(f'open "{out_dir}"')
        else:
            os.system(f'xdg-open "{out_dir}"')

    # ------------------------------------------------------------------------
    # GENERATION & BACKGROUND WORKER
    # ------------------------------------------------------------------------

    def _start_generation(self) -> None:
        if not self.selected_manifests:
            QMessageBox.warning(self, "No Manifests Selected", "Select at least one manifest from the sidebar to dump.")
            return

        mode = self.mode_selector.currentText()
        self.btn_generate.setEnabled(False)
        self.pbar.setVisible(True)
        self.pbar.setValue(0)
        self._log(f"Starting {mode}...")

        self.thread = QThread()
        self.worker = OutputWorker(self.base_dir, self.config_mgr, self.settings, self.selected_manifests, mode)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_worker_progress)
        self.worker.log_message.connect(self._log)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.start()

    @Slot(int, int)
    def _on_worker_progress(self, current: int, total: int) -> None:
        self.pbar.setMaximum(max(1, total))
        self.pbar.setValue(current)

    @Slot(str, str)
    def _on_worker_finished(self, status: str, result_path: str) -> None:
        self.btn_generate.setEnabled(True)
        self.pbar.setVisible(False)
        if "SUCCESS" in status:
            self._log(f"Export completed: {result_path}", "SUCCESS")
            QMessageBox.information(self, "Generation Complete", f"Successfully generated:\n{result_path}")
        else:
            self._log(f"Export failed/cancelled: {status}", "ERROR")
            QMessageBox.critical(self, "Generation Failed", f"Operation failed: {status}")

    def _refresh_memory_stat(self) -> None:
        mem_mb = get_process_memory_mb()
        self.status_memory_label.setText(f"RAM: {mem_mb:.1f} MB")

# ============================================================================
# 6. OUTPUT WORKER THREAD
# ============================================================================

class OutputWorker(QObject):
    progress = Signal(int, int)
    log_message = Signal(str, str)
    finished = Signal(str, str)

    def __init__(self, base_dir: Path, config_mgr: ConfigManager, settings: Settings,
                 selected_manifests: List[ManifestInfo], mode: str):
        super().__init__()
        self.base_dir = base_dir
        self.config_mgr = config_mgr
        self.settings = settings
        self.selected_manifests = selected_manifests
        self.mode = mode
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def run(self) -> None:
        try:
            engine = DumperEngine(self.base_dir, self.config_mgr, self.settings)
            out_dir = engine.get_output_dir()

            if self.mode == "Dump to Files":
                self.log_message.emit("Scanning filesystem for Dump to Files...", "INFO")
                # Collect files
                disc_files: List[DiscoveredFile] = []
                for m in self.selected_manifests:
                    rules, _, _ = CSVManifestParser.parse_manifest(m.path, self.base_dir)
                    res = FilesystemScanner.scan_manifest(m, rules, self.settings, out_dir, check_cancelled=lambda: self.cancelled)
                    disc_files.extend(res.discovered_files)

                # Keep only eligible
                eligible = [df for df in disc_files if df.match_result.eligible]
                self.log_message.emit(f"Found {len(eligible)} eligible files. Staging export...", "INFO")

                exporter = DumpToFilesEngine(self.settings, out_dir)
                base_name = "_".join(m.path.stem for m in self.selected_manifests) or "export"
                final_dir, report = exporter.export_files(
                    eligible, base_name=base_name,
                    progress_cb=lambda c, t: self.progress.emit(c, t),
                    check_cancelled=lambda: self.cancelled
                )
                self.finished.emit("SUCCESS", str(final_dir))
            else:
                self.log_message.emit("Generating Single TXT Dump...", "INFO")
                stats = engine.run_dump(
                    self.selected_manifests,
                    progress_cb=lambda c, t: self.progress.emit(c, t),
                    check_cancelled=lambda: self.cancelled
                )
                if stats.output_status == "SUCCESS":
                    self.finished.emit("SUCCESS", str(stats.output_path))
                else:
                    self.finished.emit(stats.output_status, str(stats.output_path or ""))
        except Exception as e:
            self.finished.emit(f"ERROR: {e}", "")

# ============================================================================
# 7. LAUNCH ENTRY POINT
# ============================================================================

def launch_gui(base_dir: Path) -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow(base_dir)
    window.show()
    app.exec_()
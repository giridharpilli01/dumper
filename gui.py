"""
AI Context Dumper - Desktop Application (PySide6)
v0.3 Workspace Layout & Quality-of-Life Edition

Architecture:
- Column 1: Persistent far-left Navigation Rail (Context Dumper, Diff Checker, Settings)
- Column 2: Manifests list & Saved Combinations parent/child tree
- Column 3: File Explorer, search/filter controls, preview, and expandable Activity Console
- Column 4: Rule Inspector (top) & live Manifest Contents viewer (bottom)
- In-rail Settings workspace with vertical category navigation
- Strict preservation of core engine semantics, safety ceilings, and persistence models
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
from typing import Dict, List, Optional, Set, Any, Tuple

from PySide6.QtCore import (
    Qt, QSize, QTimer, Signal, Slot, QThread, QObject, QItemSelectionModel, QDir
)
from PySide6.QtGui import (
    QAction, QIcon, QFont, QColor, QPalette, QKeySequence, QTextCursor, QPainter
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTreeView, QListView, QListWidget, QListWidgetItem,
    QTreeWidget, QTreeWidgetItem, QTextEdit, QLineEdit, QLabel, QPushButton,
    QToolBar, QComboBox, QCheckBox, QSpinBox, QDoubleSpinBox, QTabWidget,
    QDialog, QDialogButtonBox, QFileDialog, QMessageBox, QMenu, QProgressBar,
    QStatusBar, QFileSystemModel, QHeaderView, QFrame, QGroupBox,
    QFormLayout, QScrollArea, QSizePolicy, QStackedWidget, QTableWidget,
    QTableWidgetItem, QAbstractItemView
)

from dump import (
    __version__, __build__,
    Settings, ConfigManager, ManifestInfo, ManifestDiscovery,
    CSVManifestParser, Rule, Action, Target, RuleEngine,
    FilesystemScanner, EncodingDetector, PathResolver,
    DumperEngine, DumpToFilesEngine, DiscoveredFile, MatchResult,
    DEFAULT_MAX_FILE_SIZE, SCHEMA_VERSION, DEFAULT_SKIPPED_DIRECTORIES
)

# ============================================================================
# 1. PROCESS MEMORY HELPER (STANDARD LIBRARY)
# ============================================================================

def get_process_memory_mb() -> float:
    """Returns current process Resident Set Size (RSS) memory in megabytes."""
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
            return usage / 1024
    except Exception:
        pass
    return 0.0

# ============================================================================
# 2. DESIGN TOKENS & STYLING SYSTEM
# ============================================================================

@dataclass
class ThemeColors:
    bg_app: str
    bg_panel: str
    bg_surface: str
    bg_input: str
    bg_hover: str
    bg_selected: str
    border_subtle: str
    border_focus: str
    separator: str
    text_primary: str
    text_secondary: str
    text_muted: str
    text_disabled: str
    accent: str
    accent_hover: str
    accent_text: str
    status_success: str
    status_success_bg: str
    status_warning: str
    status_warning_bg: str
    status_error: str
    status_error_bg: str
    status_info: str
    status_info_bg: str

DARK_THEME = ThemeColors(
    bg_app="#0d0f12",
    bg_panel="#13161c",
    bg_surface="#1a1d24",
    bg_input="#101217",
    bg_hover="#21252f",
    bg_selected="#282e3b",
    border_subtle="#262a34",
    border_focus="#4377f0",
    separator="#1f232d",
    text_primary="#f1f4f8",
    text_secondary="#9aa2af",
    text_muted="#656c79",
    text_disabled="#3f444f",
    accent="#3b72f6",
    accent_hover="#2862ea",
    accent_text="#ffffff",
    status_success="#10b981",
    status_success_bg="#064e3b",
    status_warning="#f59e0b",
    status_warning_bg="#78350f",
    status_error="#ef4444",
    status_error_bg="#7f1d1d",
    status_info="#38bdf8",
    status_info_bg="#0c4a6e",
)

LIGHT_THEME = ThemeColors(
    bg_app="#f4f5f8",
    bg_panel="#ffffff",
    bg_surface="#ffffff",
    bg_input="#f8fafc",
    bg_hover="#edf0f5",
    bg_selected="#e2e7f3",
    border_subtle="#e1e4ea",
    border_focus="#2563eb",
    separator="#eceef3",
    text_primary="#111827",
    text_secondary="#4b5563",
    text_muted="#8c95a3",
    text_disabled="#cbd5e1",
    accent="#2563eb",
    accent_hover="#1d4ed8",
    accent_text="#ffffff",
    status_success="#059669",
    status_success_bg="#d1fae5",
    status_warning="#d97706",
    status_warning_bg="#fef3c7",
    status_error="#dc2626",
    status_error_bg="#fee2e2",
    status_info="#0284c7",
    status_info_bg="#e0f2fe",
)

class ThemeEngine:
    @staticmethod
    def get_colors(theme_name: str) -> ThemeColors:
        if theme_name == "Light":
            return LIGHT_THEME
        return DARK_THEME

    @staticmethod
    def generate_qss(c: ThemeColors, font_size: int = 10) -> str:
        # ====================================================================
        # CORNER RADIUS TOKENS
        # Change these 3 values to adjust rounding across the entire UI
        # ====================================================================
        r_sm = "8px"   # Small: row items, badges, scrollbars, progress bar
        r_md = "12px"   # Medium: buttons, inputs, dropdowns, tables, cards
        r_lg = "24px"   # Large: outer panels, dialogs, main containers

        return f"""
        * {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
            font-size: {font_size}pt;
            color: {c.text_primary};
        }}
        QMainWindow, QDialog {{
            background-color: {c.bg_app};
        }}
        QFrame#panelFrame {{
            background-color: {c.bg_panel};
            border: 1px solid {c.border_subtle};
            border-radius: {r_lg};
        }}
        QFrame#cardFrame {{
            background-color: {c.bg_surface};
            border: 1px solid {c.border_subtle};
            border-radius: {r_md};
        }}
        QFrame#navRail {{
            background-color: {c.bg_panel};
            border-right: 1px solid {c.border_subtle};
        }}
        QPushButton#navBtn {{
            background-color: transparent;
            border: none;
            border-radius: {r_md};
            padding: 8px 6px;
            font-size: 8.5pt;
            font-weight: 500;
            color: {c.text_secondary};
            text-align: center;
        }}
        QPushButton#navBtn:hover {{
            background-color: {c.bg_hover};
            color: {c.text_primary};
        }}
        QPushButton#navBtn[active="true"] {{
            background-color: {c.bg_selected};
            color: {c.text_primary};
            font-weight: 600;
            border-left: 2px solid {c.accent};
        }}
        QToolBar {{
            background-color: {c.bg_panel};
            border-bottom: 1px solid {c.border_subtle};
            padding: 6px 10px;
            spacing: 8px;
        }}
        QPushButton {{
            background-color: {c.bg_surface};
            border: 1px solid {c.border_subtle};
            border-radius: {r_md};
            padding: 5px 12px;
            font-weight: 500;
        }}
        QPushButton:hover {{
            background-color: {c.bg_hover};
            border-color: {c.border_focus};
        }}
        QPushButton:pressed {{
            background-color: {c.bg_selected};
        }}
        QPushButton:disabled {{
            background-color: {c.bg_input};
            color: {c.text_disabled};
            border-color: {c.border_subtle};
        }}
        QPushButton#primaryAction {{
            background-color: {c.accent};
            color: {c.accent_text};
            border: 1px solid {c.accent};
            border-radius: {r_md};
            font-weight: 600;
            padding: 5px 16px;
        }}
        QPushButton#primaryAction:hover {{
            background-color: {c.accent_hover};
            border-color: {c.accent_hover};
        }}
        QPushButton#successBtn {{
            background-color: {c.status_success_bg};
            color: {c.status_success};
            border: 1px solid {c.status_success};
            border-radius: {r_md};
            font-weight: 600;
        }}
        QPushButton#dangerBtn {{
            background-color: {c.status_error_bg};
            color: {c.status_error};
            border: 1px solid {c.status_error};
            border-radius: {r_md};
            font-weight: 600;
        }}
        QLineEdit, QComboBox, QSpinBox {{
            background-color: {c.bg_input};
            border: 1px solid {c.border_subtle};
            border-radius: {r_md};
            padding: 4px 8px;
            selection-background-color: {c.accent};
        }}
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
            border-color: {c.border_focus};
        }}
        QTreeView, QListView, QListWidget, QTreeWidget, QTextEdit, QTableWidget {{
            background-color: {c.bg_input};
            border: 1px solid {c.border_subtle};
            border-radius: {r_md};
            selection-background-color: {c.bg_selected};
            selection-color: {c.text_primary};
            outline: none;
        }}
        QTreeView::item, QListWidget::item, QTreeWidget::item {{
            height: 26px;
            padding: 2px 4px;
            border-radius: {r_sm};
        }}
        QTreeView::item:hover, QListWidget::item:hover, QTreeWidget::item:hover {{
            background-color: {c.bg_hover};
        }}
        QTreeView::item:selected, QListWidget::item:selected, QTreeWidget::item:selected {{
            background-color: {c.bg_selected};
        }}
        QHeaderView::section {{
            background-color: {c.bg_surface};
            color: {c.text_secondary};
            border: none;
            border-bottom: 1px solid {c.border_subtle};
            padding: 4px 8px;
            font-weight: 600;
            font-size: 8.5pt;
        }}
        QSplitter::handle:horizontal {{
            width: 3px;
            background-color: {c.border_subtle};
        }}
        QSplitter::handle:vertical {{
            height: 3px;
            background-color: {c.border_subtle};
        }}
        QScrollBar:vertical {{
            background: transparent;
            width: 8px;
            margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background-color: {c.border_subtle};
            border-radius: {r_sm};
            min-height: 20px;
        }}
        QScrollBar::handle:vertical:hover {{
            background-color: {c.text_muted};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}
        QTabWidget::pane {{
            border: 1px solid {c.border_subtle};
            background-color: {c.bg_panel};
            border-radius: {r_md};
        }}
        QTabBar::tab {{
            background-color: {c.bg_surface};
            border: 1px solid {c.border_subtle};
            padding: 6px 14px;
            margin-right: 2px;
            border-top-left-radius: {r_sm};
            border-top-right-radius: {r_sm};
        }}
        QTabBar::tab:selected {{
            background-color: {c.bg_panel};
            border-bottom-color: {c.bg_panel};
            font-weight: 600;
        }}
        QStatusBar {{
            background-color: {c.bg_panel};
            border-top: 1px solid {c.border_subtle};
            color: {c.text_secondary};
        }}
        QProgressBar {{
            background-color: {c.bg_input};
            border: 1px solid {c.border_subtle};
            border-radius: {r_sm};
            height: 6px;
            text-align: center;
        }}
        QProgressBar::chunk {{
            background-color: {c.accent};
            border-radius: {r_sm};
        }}
        """

   @staticmethod
    def apply_theme(app: QApplication, theme_name: str, font_size: int = 10) -> None:
        colors = ThemeEngine.get_colors(theme_name)
        app.setStyle("Fusion")
        app.setStyleSheet(ThemeEngine.generate_qss(colors, font_size))

# ============================================================================
# 3. GUI STATE & PERSISTENCE
# ============================================================================

GUI_STATE_FILE = "gui_state.json"

@dataclass
class GuiState:
    theme: str = "System"
    font_size: int = 10
    active_nav_index: int = 0  # 0: Context Dumper, 1: Diff Checker, 2: Settings
    show_hidden_files: bool = False
    preview_visible: bool = False
    inspector_visible: bool = True
    console_visible: bool = True
    console_expanded: bool = False
    last_root: str = ""
    last_selected_manifests: List[str] = field(default_factory=list)
    output_mode: str = "Single TXT Dump"
    window_width: int = 1280
    window_height: int = 840
    splitter_main: List[int] = field(default_factory=lambda: [240, 680, 360])
    splitter_center: List[int] = field(default_factory=lambda: [540, 180])
    splitter_col2: List[int] = field(default_factory=lambda: [360, 260])
    splitter_col4: List[int] = field(default_factory=lambda: [420, 300])

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "GuiState":
        if not isinstance(data, dict):
            return cls()
        return cls(
            theme=str(data.get("theme", "System")),
            font_size=int(data.get("font_size", 10)),
            active_nav_index=int(data.get("active_nav_index", 0)),
            show_hidden_files=bool(data.get("show_hidden_files", False)),
            preview_visible=bool(data.get("preview_visible", False)),
            inspector_visible=bool(data.get("inspector_visible", True)),
            console_visible=bool(data.get("console_visible", True)),
            console_expanded=bool(data.get("console_expanded", False)),
            last_root=str(data.get("last_root", "")),
            last_selected_manifests=list(data.get("last_selected_manifests", [])),
            output_mode=str(data.get("output_mode", "Single TXT Dump")),
            window_width=int(data.get("window_width", 1280)),
            window_height=int(data.get("window_height", 840)),
            splitter_main=list(data.get("splitter_main", [240, 680, 360])),
            splitter_center=list(data.get("splitter_center", [540, 180])),
            splitter_col2=list(data.get("splitter_col2", [360, 260])),
            splitter_col4=list(data.get("splitter_col4", [420, 300])),
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
# 4. STRUCTURED RULE INSPECTOR
# ============================================================================

class StructuredRuleInspector(QWidget):
    include_clicked = Signal()
    exclude_clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._build_ui()
        self.show_empty_state()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        header_lay = QHBoxLayout()
        title_lbl = QLabel("RULE INSPECTOR")
        title_lbl.setStyleSheet("font-size: 8.5pt; font-weight: 700; color: #9aa2af; letter-spacing: 0.5px;")
        header_lay.addWidget(title_lbl)
        header_lay.addStretch()
        layout.addLayout(header_lay)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)

        self.container = QWidget()
        self.cards_lay = QVBoxLayout(self.container)
        self.cards_lay.setContentsMargins(0, 0, 0, 0)
        self.cards_lay.setSpacing(8)

        # Card 1: Selected Item
        self.card_target = QFrame()
        self.card_target.setObjectName("cardFrame")
        c1_lay = QVBoxLayout(self.card_target)
        c1_lay.setContentsMargins(10, 8, 10, 8)
        self.item_name_lbl = QLabel("No selection")
        self.item_name_lbl.setStyleSheet("font-size: 10pt; font-weight: 600;")
        self.item_path_edit = QLineEdit()
        self.item_path_edit.setReadOnly(True)
        self.item_path_edit.setStyleSheet("font-family: Consolas, monospace; font-size: 8.5pt;")
        c1_lay.addWidget(self.item_name_lbl)
        c1_lay.addWidget(self.item_path_edit)
        self.cards_lay.addWidget(self.card_target)

        # Card 2: Decision
        self.card_decision = QFrame()
        self.card_decision.setObjectName("cardFrame")
        c2_lay = QVBoxLayout(self.card_decision)
        c2_lay.setContentsMargins(10, 8, 10, 8)
        self.decision_badge = QLabel("READY")
        self.decision_badge.setStyleSheet("padding: 3px 8px; border-radius: 4px; font-weight: 700; font-size: 8.5pt; background: #262a34; color: #9aa2af;")
        self.reason_lbl = QLabel("Select an item to evaluate effective inclusion.")
        self.reason_lbl.setWordWrap(True)
        self.reason_lbl.setStyleSheet("color: #9aa2af; font-size: 8.5pt;")
        c2_lay.addWidget(self.decision_badge)
        c2_lay.addWidget(self.reason_lbl)
        self.cards_lay.addWidget(self.card_decision)

        # Card 3: Specificity & Matching
        self.card_rules = QFrame()
        self.card_rules.setObjectName("cardFrame")
        c3_lay = QVBoxLayout(self.card_rules)
        c3_lay.setContentsMargins(10, 8, 10, 8)
        c3_title = QLabel("MATCHING RULES")
        c3_title.setStyleSheet("font-size: 8pt; font-weight: 700; color: #9aa2af;")
        self.rules_content_lbl = QLabel("No rules evaluated.")
        self.rules_content_lbl.setWordWrap(True)
        self.rules_content_lbl.setStyleSheet("font-family: Consolas, monospace; font-size: 8.5pt;")
        c3_lay.addWidget(c3_title)
        c3_lay.addWidget(self.rules_content_lbl)
        self.cards_lay.addWidget(self.card_rules)

        # Card 4: Safety Blocker
        self.card_safety = QFrame()
        self.card_safety.setObjectName("cardFrame")
        c4_lay = QVBoxLayout(self.card_safety)
        c4_lay.setContentsMargins(10, 8, 10, 8)
        self.safety_lbl = QLabel("")
        self.safety_lbl.setWordWrap(True)
        c4_lay.addWidget(self.safety_lbl)
        self.cards_lay.addWidget(self.card_safety)
        self.card_safety.setVisible(False)

        self.cards_lay.addStretch()
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll, 1)

        btn_bar = QHBoxLayout()
        self.btn_inc = QPushButton("Include Path")
        self.btn_inc.setObjectName("successBtn")
        self.btn_inc.clicked.connect(self.include_clicked.emit)
        self.btn_exc = QPushButton("Exclude Path")
        self.btn_exc.setObjectName("dangerBtn")
        self.btn_exc.clicked.connect(self.exclude_clicked.emit)
        btn_bar.addWidget(self.btn_inc)
        btn_bar.addWidget(self.btn_exc)
        layout.addLayout(btn_bar)

    def show_empty_state(self) -> None:
        self.item_name_lbl.setText("No selection")
        self.item_path_edit.setText("Select a file or folder to inspect its effective inclusion.")
        self.decision_badge.setText("READY")
        self.decision_badge.setStyleSheet("padding: 3px 8px; border-radius: 4px; font-weight: 700; font-size: 8.5pt; background: #262a34; color: #9aa2af;")
        self.reason_lbl.setText("Precedence evaluation will appear here once an item is selected.")
        self.rules_content_lbl.setText("No rules evaluated.")
        self.card_safety.setVisible(False)
        self.btn_inc.setEnabled(False)
        self.btn_exc.setEnabled(False)

    def update_inspection(self, file_path: Path, exp: Dict[str, Any], is_dark: bool) -> None:
        self.btn_inc.setEnabled(True)
        self.btn_exc.setEnabled(True)
        self.item_name_lbl.setText(file_path.name or str(file_path))
        self.item_path_edit.setText(exp.get("canonical_path", str(file_path)))

        eligible = exp.get("effective_eligible", False)
        blocker = exp.get("safety_blocker")

        if blocker:
            self.decision_badge.setText("SAFETY BLOCKED")
            self.decision_badge.setStyleSheet("padding: 3px 8px; border-radius: 4px; font-weight: 700; font-size: 8.5pt; background: #7f1d1d; color: #ef4444;")
        elif eligible:
            self.decision_badge.setText("EFFECTIVELY INCLUDED")
            self.decision_badge.setStyleSheet("padding: 3px 8px; border-radius: 4px; font-weight: 700; font-size: 8.5pt; background: #064e3b; color: #10b981;")
        else:
            self.decision_badge.setText("EFFECTIVELY EXCLUDED")
            self.decision_badge.setStyleSheet("padding: 3px 8px; border-radius: 4px; font-weight: 700; font-size: 8.5pt; background: #7f1d1d; color: #ef4444;")

        self.reason_lbl.setText(exp.get("reason", "No reason provided."))

        matching = exp.get("matching_rules", [])
        winning = exp.get("winning_rule")
        if matching:
            lines = []
            for r in matching:
                prefix = "★ WINNER : " if r == winning else "  MATCH  : "
                lines.append(f"{prefix}{r}")
            self.rules_content_lbl.setText("\n".join(lines))
        else:
            self.rules_content_lbl.setText("No matching manifest rules.\nDefault global filters apply.")

        if blocker:
            self.card_safety.setVisible(True)
            self.card_safety.setStyleSheet("background-color: #7f1d1d; border: 1px solid #ef4444; border-radius: 5px;")
            self.safety_lbl.setText(f"<b>Safety Blocker:</b> {blocker}")
            self.safety_lbl.setStyleSheet("color: #fee2e2; font-size: 8.5pt;")
        else:
            self.card_safety.setVisible(False)

# ============================================================================
# 5. MANIFEST CONTENTS PANEL (Column 4 Bottom)
# ============================================================================

class ManifestContentsWidget(QWidget):
    edit_manifest_requested = Signal(Path)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.current_manifest_path: Optional[Path] = None
        self._build_ui()
        self.show_empty_state()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        hdr_lay = QHBoxLayout()
        self.title_lbl = QLabel("MANIFEST CONTENTS")
        self.title_lbl.setStyleSheet("font-size: 8.5pt; font-weight: 700; color: #9aa2af; letter-spacing: 0.5px;")
        hdr_lay.addWidget(self.title_lbl)
        hdr_lay.addStretch()

        self.btn_edit = QPushButton("Edit CSV")
        self.btn_edit.setStyleSheet("font-size: 8pt; padding: 2px 8px;")
        self.btn_edit.clicked.connect(self._on_edit_clicked)
        hdr_lay.addWidget(self.btn_edit)
        layout.addLayout(hdr_lay)

        self.summary_badge = QLabel("0 rules defined")
        self.summary_badge.setStyleSheet("color: #9aa2af; font-size: 8.5pt;")
        layout.addWidget(self.summary_badge)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Action", "Target", "Pattern"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.table, 1)

        # Global Filters Info Footnote
        self.global_note = QLabel("Note: CSV entries override global extension and skipped-directory filters.")
        self.global_note.setStyleSheet("color: #656c79; font-size: 7.5pt; font-style: italic;")
        self.global_note.setWordWrap(True)
        layout.addWidget(self.global_note)

    def _on_edit_clicked(self) -> None:
        if self.current_manifest_path and self.current_manifest_path.exists():
            self.edit_manifest_requested.emit(self.current_manifest_path)

    def show_empty_state(self) -> None:
        self.current_manifest_path = None
        self.title_lbl.setText("MANIFEST CONTENTS")
        self.summary_badge.setText("No manifest or combination selected.")
        self.btn_edit.setEnabled(False)
        self.table.setRowCount(0)

    def display_manifest(self, m: ManifestInfo, base_dir: Path) -> None:
        self.current_manifest_path = m.path
        self.title_lbl.setText(f"MANIFEST: {m.filename}")
        self.btn_edit.setEnabled(True)

        rules, errors, _ = CSVManifestParser.parse_manifest(m.path, base_dir)
        path_c = sum(1 for r in rules if r.target == Target.PATH)
        file_c = sum(1 for r in rules if r.target == Target.FILENAME)
        ext_c = sum(1 for r in rules if r.target == Target.EXTENSION)
        inc_c = sum(1 for r in rules if r.action == Action.INCLUDE)
        exc_c = sum(1 for r in rules if r.action == Action.EXCLUDE)

        self.summary_badge.setText(
            f"{len(rules)} rule(s) defined ({inc_c} include, {exc_c} exclude) • {path_c} PATH, {file_c} FILENAME, {ext_c} EXTENSION"
        )

        self.table.setRowCount(len(rules))
        for row, r in enumerate(rules):
            item_act = QTableWidgetItem(r.action)
            item_act.setForeground(QColor("#10b981" if r.action == Action.INCLUDE else "#ef4444"))
            item_tgt = QTableWidgetItem(r.target)
            item_pat = QTableWidgetItem(r.raw_pattern)
            item_pat.setFont(QFont("Consolas", 8.5))

            self.table.setItem(row, 0, item_act)
            self.table.setItem(row, 1, item_tgt)
            self.table.setItem(row, 2, item_pat)

    def display_combination(self, name: str, manifests: List[ManifestInfo], base_dir: Path) -> None:
        self.current_manifest_path = manifests[0].path if manifests else None
        self.title_lbl.setText(f"COMBINATION: {name}")
        self.btn_edit.setEnabled(len(manifests) == 1)

        total_rules = []
        for m in manifests:
            rules, _, _ = CSVManifestParser.parse_manifest(m.path, base_dir)
            total_rules.extend(rules)

        self.summary_badge.setText(
            f"{len(manifests)} constituent manifest(s) • {len(total_rules)} total rules combined"
        )

        self.table.setRowCount(len(total_rules))
        for row, r in enumerate(total_rules):
            item_act = QTableWidgetItem(f"[{r.source_manifest}] {r.action}")
            item_act.setForeground(QColor("#10b981" if r.action == Action.INCLUDE else "#ef4444"))
            item_tgt = QTableWidgetItem(r.target)
            item_pat = QTableWidgetItem(r.raw_pattern)
            item_pat.setFont(QFont("Consolas", 8.5))

            self.table.setItem(row, 0, item_act)
            self.table.setItem(row, 1, item_tgt)
            self.table.setItem(row, 2, item_pat)

# ============================================================================
# 6. IN-RAIL SETTINGS VIEW (Section 10)
# ============================================================================

class SettingsView(QWidget):
    settings_saved = Signal(Settings, GuiState)

    def __init__(self, settings: Settings, gui_state: GuiState,
                 config_mgr: ConfigManager, gui_state_mgr: GuiStateManager,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.settings = settings
        self.gui_state = gui_state
        self.config_mgr = config_mgr
        self.gui_state_mgr = gui_state_mgr
        self._build_ui()
        self._load_fields()

    def _build_ui(self) -> None:
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(18, 16, 18, 16)
        main_lay.setSpacing(12)

        # Header Title
        hdr = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Settings & Preferences")
        title.setStyleSheet("font-size: 14pt; font-weight: 700;")
        sub = QLabel("Configure application appearance, workspace persistence, and dumper engine filters.")
        sub.setStyleSheet("color: #9aa2af; font-size: 9pt;")
        title_box.addWidget(title)
        title_box.addWidget(sub)
        hdr.addLayout(title_box)
        hdr.addStretch()

        self.btn_save = QPushButton("Save Settings")
        self.btn_save.setObjectName("primaryAction")
        self.btn_save.clicked.connect(self._on_save)
        hdr.addWidget(self.btn_save)
        main_lay.addLayout(hdr)

        # Splitter: Left Category List | Right Stacked Form
        splitter = QSplitter(Qt.Horizontal)

        self.cat_list = QListWidget()
        self.cat_list.setMaximumWidth(200)
        categories = ["Appearance", "Workspace", "Dumper Engine", "Output", "Diagnostics", "Recovery", "About"]
        for cat in categories:
            self.cat_list.addItem(QListWidgetItem(f"  {cat}"))
        self.cat_list.currentRowChanged.connect(self._on_category_changed)
        splitter.addWidget(self.cat_list)

        self.stack = QStackedWidget()
        splitter.addWidget(self.stack)
        main_lay.addWidget(splitter, 1)

        # 1. Appearance Page
        p_app = QWidget()
        lay_app = QFormLayout(p_app)
        lay_app.setContentsMargins(16, 12, 16, 12)
        lay_app.setSpacing(12)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["System", "Dark", "Light"])
        self.font_spin = QSpinBox()
        self.font_spin.setRange(8, 16)
        lay_app.addRow("Application Theme:", self.theme_combo)
        lay_app.addRow("Base Font Size (pt):", self.font_spin)
        self.stack.addWidget(p_app)

        # 2. Workspace Page
        p_ws = QWidget()
        lay_ws = QVBoxLayout(p_ws)
        lay_ws.setContentsMargins(16, 12, 16, 12)
        lay_ws.setSpacing(10)
        self.cb_hidden = QCheckBox("Show hidden files and folders in Explorer")
        self.cb_preview = QCheckBox("Show File Preview pane by default")
        self.cb_inspector = QCheckBox("Show Rule Inspector pane")
        self.cb_console = QCheckBox("Show Activity Console")
        lay_ws.addWidget(self.cb_hidden)
        lay_ws.addWidget(self.cb_preview)
        lay_ws.addWidget(self.cb_inspector)
        lay_ws.addWidget(self.cb_console)
        lay_ws.addStretch()
        self.stack.addWidget(p_ws)

        # 3. Dumper Engine Page
        p_dmp = QWidget()
        lay_dmp = QFormLayout(p_dmp)
        lay_dmp.setContentsMargins(16, 12, 16, 12)
        lay_dmp.setSpacing(12)
        self.output_dir_edit = QLineEdit()
        self.max_size_label = QLabel("5.00 MB (Hard Safety Limit - Locked)")
        self.max_size_label.setStyleSheet("color: #9aa2af; font-style: italic;")
        self.cb_binary = QCheckBox("Enable binary file detection heuristic")
        self.cb_extless = QCheckBox("Allow extensionless files (e.g., Dockerfile)")
        self.skipped_dirs_edit = QLineEdit()
        self.inc_ext_edit = QLineEdit()
        self.exc_ext_edit = QLineEdit()
        lay_dmp.addRow("Output Directory:", self.output_dir_edit)
        lay_dmp.addRow("Max File Size Limit:", self.max_size_label)
        lay_dmp.addRow("", self.cb_binary)
        lay_dmp.addRow("", self.cb_extless)
        lay_dmp.addRow("Skipped Directories:", self.skipped_dirs_edit)
        lay_dmp.addRow("Include Extensions:", self.inc_ext_edit)
        lay_dmp.addRow("Exclude Extensions:", self.exc_ext_edit)
        self.stack.addWidget(p_dmp)

        # 4. Output Page
        p_out = QWidget()
        lay_out = QFormLayout(p_out)
        lay_out.setContentsMargins(16, 12, 16, 12)
        lay_out.setSpacing(12)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Single TXT Dump", "Dump to Files"])
        lay_out.addRow("Default Output Mode:", self.mode_combo)
        self.stack.addWidget(p_out)

        # 5. Diagnostics Page
        p_diag = QWidget()
        lay_diag = QVBoxLayout(p_diag)
        lay_diag.setContentsMargins(16, 12, 16, 12)
        lay_diag.setSpacing(10)
        self.cb_verbose = QCheckBox("Enable verbose diagnostic logging")
        self.cb_token = QCheckBox("Calculate approximate token counts (~chars / 4)")
        lay_diag.addWidget(self.cb_verbose)
        lay_diag.addWidget(self.cb_token)
        lay_diag.addStretch()
        self.stack.addWidget(p_diag)

        # 6. Recovery Page
        p_rec = QWidget()
        lay_rec = QVBoxLayout(p_rec)
        lay_rec.setContentsMargins(16, 12, 16, 12)
        lay_rec.setSpacing(10)
        btn_open_cfg = QPushButton("Open Settings Location in File Browser")
        btn_open_cfg.clicked.connect(self._open_config_dir)
        btn_reset_ui = QPushButton("Reset UI Preferences to Defaults")
        btn_reset_ui.clicked.connect(self._reset_ui_prefs)
        btn_reset_dmp = QPushButton("Restore Dumper Settings to Defaults")
        btn_reset_dmp.clicked.connect(self._reset_dumper_settings)
        lay_rec.addWidget(btn_open_cfg)
        lay_rec.addWidget(btn_reset_ui)
        lay_rec.addWidget(btn_reset_dmp)
        lay_rec.addStretch()
        self.stack.addWidget(p_rec)

        # 7. About Page
        p_about = QWidget()
        lay_about = QVBoxLayout(p_about)
        lay_about.setContentsMargins(16, 12, 16, 12)
        from PySide6.QtCore import __version__ as q_ver
        import platform

        about_text = QTextEdit()
        about_text.setReadOnly(True)
        about_text.setHtml(f"""
        <div style="line-height: 1.5;">
            <h2 style="margin: 0;">AI Context Dumper</h2>
            <p style="color: #9aa2af; margin-top: 2px;">Four-Column Workspace Edition (v{__version__})</p>
            <hr style="border: 0; border-top: 1px solid #262a34;">
            <table style="width: 100%; border-collapse: collapse; font-size: 9pt;">
                <tr><td style="padding: 3px 0; color: #9aa2af;"><b>Version:</b></td><td>v{__version__}</td></tr>
                <tr><td style="padding: 3px 0; color: #9aa2af;"><b>Build Number:</b></td><td>{__build__}</td></tr>
                <tr><td style="padding: 3px 0; color: #9aa2af;"><b>Python Runtime:</b></td><td>{platform.python_version()} ({platform.architecture()[0]})</td></tr>
                <tr><td style="padding: 3px 0; color: #9aa2af;"><b>PySide6 / Qt:</b></td><td>{q_ver}</td></tr>
                <tr><td style="padding: 3px 0; color: #9aa2af;"><b>Platform:</b></td><td>{platform.system()} {platform.release()}</td></tr>
            </table>
            <hr style="border: 0; border-top: 1px solid #262a34;">
            <p style="font-size: 8.5pt; color: #9aa2af;">
                <b>Safety Guarantees:</b> 5 MiB ceiling &bull; Directory symlinks never followed &bull; Local execution only.
            </p>
        </div>
        """)
        lay_about.addWidget(about_text)
        self.stack.addWidget(p_about)

        self.cat_list.setCurrentRow(0)

    def _on_category_changed(self, row: int) -> None:
        self.stack.setCurrentIndex(row)

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
            self.settings.output_directory = self.output_dir_edit.text().strip() or "output"
            skipped = [s.strip() for s in self.skipped_dirs_edit.text().split(",") if s.strip()]
            self.settings.skipped_directories = skipped or DEFAULT_SKIPPED_DIRECTORIES
            self.settings.include_extensions = [s.strip().lower() if s.strip().startswith(".") else f".{s.strip().lower()}"
                                               for s in self.inc_ext_edit.text().split(",") if s.strip()]
            self.settings.exclude_extensions = [s.strip().lower() if s.strip().startswith(".") else f".{s.strip().lower()}"
                                               for s in self.exc_ext_edit.text().split(",") if s.strip()]
            self.settings.binary_detection = self.cb_binary.isChecked()
            self.settings.allow_extensionless = self.cb_extless.isChecked()
            self.settings.verbose = self.cb_verbose.isChecked()
            self.settings.approximate_token_count = self.cb_token.isChecked()
            self.config_mgr.save_settings(self.settings)

            self.gui_state.theme = self.theme_combo.currentText()
            self.gui_state.font_size = self.font_spin.value()
            self.gui_state.show_hidden_files = self.cb_hidden.isChecked()
            self.gui_state.preview_visible = self.cb_preview.isChecked()
            self.gui_state.inspector_visible = self.cb_inspector.isChecked()
            self.gui_state.console_visible = self.cb_console.isChecked()
            self.gui_state.output_mode = self.mode_combo.currentText()
            self.gui_state_mgr.save_state(self.gui_state)

            self.settings_saved.emit(self.settings, self.gui_state)
            QMessageBox.information(self, "Settings Saved", "Configuration updated successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save settings: {e}")

    def _open_config_dir(self) -> None:
        base = self.config_mgr.base_dir
        if sys.platform == "win32":
            os.startfile(str(base))
        elif sys.platform == "darwin":
            os.system(f'open "{base}"')
        else:
            os.system(f'xdg-open "{base}"')

    def _reset_ui_prefs(self) -> None:
        if QMessageBox.question(self, "Reset UI", "Reset UI preferences to defaults?",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.gui_state = GuiState()
            self._load_fields()

    def _reset_dumper_settings(self) -> None:
        if QMessageBox.question(self, "Reset Dumper", "Restore core settings.json to defaults?",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.settings = Settings()
            self._load_fields()

# ============================================================================
# 7. MANIFEST EDITOR DIALOG
# ============================================================================

class ManifestEditorDialog(QDialog):
    def __init__(self, parent: QWidget, manifest_path: Path):
        super().__init__(parent)
        self.manifest_path = manifest_path
        self.setWindowTitle(f"Edit Manifest — {manifest_path.name}")
        self.resize(720, 520)
        self._build_ui()
        self._load_file()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        lbl = QLabel("CSV Manifest Editor (Simple 1-column or Advanced 3-column ACTION,TARGET,PATTERN)")
        lbl.setStyleSheet("color: #9aa2af; font-size: 8.5pt;")
        layout.addWidget(lbl)

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
            temp_path = self.manifest_path.parent / f".tmp_{self.manifest_path.name}"
            temp_path.write_text(content, encoding="utf-8")
            rules, errors, malformed = CSVManifestParser.parse_manifest(temp_path, self.manifest_path.parent)
            temp_path.unlink(missing_ok=True)

            if malformed > 0:
                msg = f"The manifest contains {malformed} malformed rows:\n\n" + "\n".join(errors[:5])
                if QMessageBox.question(self, "Syntax Warning", f"{msg}\n\nSave anyway?",
                                        QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                    return

            self.manifest_path.write_text(content, encoding="utf-8")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save manifest: {e}")

# ============================================================================
# 8. MAIN APPLICATION WINDOW (4-COLUMN ARCHITECTURE)
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
        self.console_is_expanded: bool = self.gui_state.console_expanded

        self.setWindowTitle(f"AI Context Dumper v{__version__}")
        self.resize(self.gui_state.window_width, self.gui_state.window_height)

        self._build_actions()
        self._build_ui()
        self._apply_theme()
        self._refresh_manifest_list()

        initial_root = Path(self.gui_state.last_root) if self.gui_state.last_root and Path(self.gui_state.last_root).is_dir() else Path.home()
        self._set_explorer_root(initial_root)
        self._set_nav_destination(self.gui_state.active_nav_index)

    def _build_actions(self) -> None:
        self.act_new_manifest = QAction("New Manifest", self)
        self.act_new_manifest.triggered.connect(self._create_manifest)

        self.act_edit_manifest = QAction("Edit CSV", self)
        self.act_edit_manifest.triggered.connect(self._edit_selected_manifest)

        self.act_settings = QAction("Settings...", self)
        self.act_settings.setShortcut(QKeySequence.Preferences)
        self.act_settings.triggered.connect(lambda: self._set_nav_destination(2))

    def _build_ui(self) -> None:
        central_widget = QWidget(self)
        root_hlay = QHBoxLayout(central_widget)
        root_hlay.setContentsMargins(0, 0, 0, 0)
        root_hlay.setSpacing(0)

        # ============================================================
        # COLUMN 1: Far-Left Navigation Rail
        # ============================================================
        self.nav_rail = QFrame()
        self.nav_rail.setObjectName("navRail")
        self.nav_rail.setFixedWidth(72)
        rail_lay = QVBoxLayout(self.nav_rail)
        rail_lay.setContentsMargins(4, 12, 4, 12)
        rail_lay.setSpacing(8)

        self.btn_nav_dumper = QPushButton("📦\nDumper")
        self.btn_nav_dumper.setObjectName("navBtn")
        self.btn_nav_dumper.setToolTip("Context Dumper Workspace")
        self.btn_nav_dumper.clicked.connect(lambda: self._set_nav_destination(0))

        self.btn_nav_diff = QPushButton("⚖️\nDiff")
        self.btn_nav_diff.setObjectName("navBtn")
        self.btn_nav_diff.setToolTip("Diff Checker (Planned)")
        self.btn_nav_diff.clicked.connect(lambda: self._set_nav_destination(1))

        self.btn_nav_settings = QPushButton("⚙️\nSettings")
        self.btn_nav_settings.setObjectName("navBtn")
        self.btn_nav_settings.setToolTip("Preferences & Settings")
        self.btn_nav_settings.clicked.connect(lambda: self._set_nav_destination(2))

        rail_lay.addWidget(self.btn_nav_dumper)
        rail_lay.addWidget(self.btn_nav_diff)
        rail_lay.addStretch()
        rail_lay.addWidget(self.btn_nav_settings)
        root_hlay.addWidget(self.nav_rail)

        # ============================================================
        # Main Work Stack (Dumper, Diff Placeholder, Settings)
        # ============================================================
        self.main_stack = QStackedWidget()
        root_hlay.addWidget(self.main_stack, 1)

        # --- Page 0: Context Dumper Workspace ---
        dumper_page = QWidget()
        dumper_vlay = QVBoxLayout(dumper_page)
        dumper_vlay.setContentsMargins(0, 0, 0, 0)
        dumper_vlay.setSpacing(0)

        # Toolbar above Columns 2, 3, 4
        self.toolbar = QToolBar("Main Toolbar")
        self.toolbar.setMovable(False)

        btn_browse = QPushButton("Browse Root...")
        btn_browse.clicked.connect(self._browse_folder)
        self.toolbar.addWidget(btn_browse)

        self.root_label = QLineEdit()
        self.root_label.setReadOnly(True)
        self.root_label.setMaximumWidth(280)
        self.root_label.setStyleSheet("font-family: Consolas, monospace; font-size: 8.5pt;")
        self.toolbar.addWidget(self.root_label)

        self.toolbar.addSeparator()

        self.toolbar.addWidget(QLabel(" Mode: "))
        self.mode_selector = QComboBox()
        self.mode_selector.addItems(["Single TXT Dump", "Dump to Files"])
        self.mode_selector.setCurrentText(self.gui_state.output_mode)
        self.mode_selector.currentTextChanged.connect(self._on_mode_changed)
        self.toolbar.addWidget(self.mode_selector)

        self.toolbar.addSeparator()

        self.btn_generate = QPushButton("Generate Context Dump")
        self.btn_generate.setObjectName("primaryAction")
        self.btn_generate.clicked.connect(self._start_generation)
        self.toolbar.addWidget(self.btn_generate)

        btn_open_out = QPushButton("Open Output Folder")
        btn_open_out.clicked.connect(self._open_output_folder)
        self.toolbar.addWidget(btn_open_out)

        dumper_vlay.addWidget(self.toolbar)

        # 3-way Splitter hosting Columns 2, 3, 4
        self.split_main = QSplitter(Qt.Horizontal)

        # ------------------------------------------------------------
        # COLUMN 2: Manifests & Combinations (Vertical Splitter)
        # ------------------------------------------------------------
        col2_frame = QFrame()
        col2_frame.setObjectName("panelFrame")
        col2_vlay = QVBoxLayout(col2_frame)
        col2_vlay.setContentsMargins(8, 8, 8, 8)
        col2_vlay.setSpacing(6)

        self.split_col2 = QSplitter(Qt.Vertical)

        # Top: Manifests List
        m_container = QWidget()
        m_lay = QVBoxLayout(m_container)
        m_lay.setContentsMargins(0, 0, 0, 0)
        m_lay.setSpacing(6)

        m_hdr = QHBoxLayout()
        m_lbl = QLabel("MANIFESTS")
        m_lbl.setStyleSheet("font-size: 8.5pt; font-weight: 700; color: #9aa2af; letter-spacing: 0.5px;")
        self.manifest_count_badge = QLabel("0")
        self.manifest_count_badge.setStyleSheet("background: #262a34; color: #9aa2af; font-size: 8pt; border-radius: 8px; padding: 1px 6px;")
        m_hdr.addWidget(m_lbl)
        m_hdr.addWidget(self.manifest_count_badge)
        m_hdr.addStretch()
        m_lay.addLayout(m_hdr)

        self.manifest_list = QListWidget()
        self.manifest_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.manifest_list.itemSelectionChanged.connect(self._on_manifest_selection_changed)
        m_lay.addWidget(self.manifest_list, 1)

        m_btn_bar = QHBoxLayout()
        btn_new_m = QPushButton("+ New")
        btn_new_m.clicked.connect(self._create_manifest)
        btn_edit_m = QPushButton("Edit CSV")
        btn_edit_m.clicked.connect(self._edit_selected_manifest)
        m_btn_bar.addWidget(btn_new_m)
        m_btn_bar.addWidget(btn_edit_m)
        m_lay.addLayout(m_btn_bar)

        self.split_col2.addWidget(m_container)

        # Bottom: Saved Combinations Parent/Child Tree (Section 5.2)
        c_container = QWidget()
        c_lay = QVBoxLayout(c_container)
        c_lay.setContentsMargins(0, 0, 0, 0)
        c_lay.setSpacing(6)

        c_hdr = QLabel("SAVED COMBINATIONS")
        c_hdr.setStyleSheet("font-size: 8pt; font-weight: 700; color: #656c79; letter-spacing: 0.5px;")
        c_lay.addWidget(c_hdr)

        self.combinations_tree = QTreeWidget()
        self.combinations_tree.setHeaderHidden(True)
        self.combinations_tree.itemClicked.connect(self._on_combination_tree_clicked)
        self.combinations_tree.itemDoubleClicked.connect(self._on_combination_tree_double_clicked)
        c_lay.addWidget(self.combinations_tree, 1)

        self.split_col2.addWidget(c_container)
        col2_vlay.addWidget(self.split_col2)
        self.split_main.addWidget(col2_frame)

        # ------------------------------------------------------------
        # COLUMN 3: File Explorer & Activity Console
        # ------------------------------------------------------------
        col3_frame = QFrame()
        col3_frame.setObjectName("panelFrame")
        col3_vlay = QVBoxLayout(col3_frame)
        col3_vlay.setContentsMargins(8, 8, 8, 8)
        col3_vlay.setSpacing(6)

        ctrl_bar = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filter files (Ctrl+F)...")
        ctrl_bar.addWidget(self.search_edit, 2)

        self.filter_combo = QComboBox()
        self.filter_combo.addItems([
            "All Files", "Effectively Included", "Effectively Excluded",
            "Explicitly Included", "Explicitly Excluded"
        ])
        ctrl_bar.addWidget(self.filter_combo, 1)
        col3_vlay.addLayout(ctrl_bar)

        self.split_center = QSplitter(Qt.Vertical)

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

        self.preview_frame = QFrame()
        self.preview_frame.setObjectName("cardFrame")
        prev_lay = QVBoxLayout(self.preview_frame)
        prev_lay.setContentsMargins(8, 8, 8, 8)
        self.preview_label = QLabel("FILE PREVIEW (Read-only, 256 KB limit)")
        self.preview_label.setStyleSheet("font-size: 8pt; font-weight: 700; color: #9aa2af;")
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setFont(QFont("Consolas", 9))
        prev_lay.addWidget(self.preview_label)
        prev_lay.addWidget(self.preview_text)
        self.split_center.addWidget(self.preview_frame)
        self.preview_frame.setVisible(self.gui_state.preview_visible)

        # Expandable Activity Console
        self.console_frame = QFrame()
        self.console_frame.setObjectName("cardFrame")
        cons_lay = QVBoxLayout(self.console_frame)
        cons_lay.setContentsMargins(8, 8, 8, 8)
        cons_lay.setSpacing(6)

        cons_hdr = QHBoxLayout()
        cons_title = QLabel("ACTIVITY CONSOLE")
        cons_title.setStyleSheet("font-size: 8pt; font-weight: 700; color: #9aa2af; letter-spacing: 0.5px;")
        cons_hdr.addWidget(cons_title)

        self.pbar = QProgressBar()
        self.pbar.setMaximumWidth(160)
        self.pbar.setVisible(False)
        cons_hdr.addWidget(self.pbar)
        cons_hdr.addStretch()

        self.btn_expand_console = QPushButton("▲ Expand")
        self.btn_expand_console.setStyleSheet("font-size: 8pt; padding: 2px 8px;")
        self.btn_expand_console.clicked.connect(self._toggle_console_expanded)
        cons_hdr.addWidget(self.btn_expand_console)

        btn_clear = QPushButton("Clear")
        btn_clear.setStyleSheet("font-size: 8pt; padding: 2px 8px;")
        btn_clear.clicked.connect(lambda: self.console_log.clear())
        cons_hdr.addWidget(btn_clear)
        cons_lay.addLayout(cons_hdr)

        self.console_log = QTextEdit()
        self.console_log.setReadOnly(True)
        self.console_log.setFont(QFont("Consolas", 8.5))
        cons_lay.addWidget(self.console_log)

        self.split_center.addWidget(self.console_frame)
        col3_vlay.addWidget(self.split_center)
        self.split_main.addWidget(col3_frame)

        # ------------------------------------------------------------
        # COLUMN 4: Inspector & Manifest Contents (Vertical Splitter)
        # ------------------------------------------------------------
        col4_frame = QFrame()
        col4_frame.setObjectName("panelFrame")
        col4_vlay = QVBoxLayout(col4_frame)
        col4_vlay.setContentsMargins(6, 6, 6, 6)

        self.split_col4 = QSplitter(Qt.Vertical)

        # Top: Rule Inspector
        self.structured_inspector = StructuredRuleInspector()
        self.structured_inspector.include_clicked.connect(lambda: self._set_explicit_rule(Action.INCLUDE))
        self.structured_inspector.exclude_clicked.connect(lambda: self._set_explicit_rule(Action.EXCLUDE))
        self.split_col4.addWidget(self.structured_inspector)

        # Bottom: Manifest Contents Panel (Section 7)
        self.manifest_contents = ManifestContentsWidget()
        self.manifest_contents.edit_manifest_requested.connect(self._edit_manifest_direct)
        self.split_col4.addWidget(self.manifest_contents)

        col4_vlay.addWidget(self.split_col4)
        self.split_main.addWidget(col4_frame)

        # Compatibility pointers for test assertions
        self.inspector_text = self.structured_inspector.reason_lbl
        self.inspector_panel = col4_frame

        dumper_vlay.addWidget(self.split_main, 1)
        self.main_stack.addWidget(dumper_page)

        # --- Page 1: Diff Checker Placeholder (Section 3.2) ---
        diff_page = QWidget()
        diff_lay = QVBoxLayout(diff_page)
        diff_lay.setContentsMargins(40, 40, 40, 40)
        diff_lay.setAlignment(Qt.AlignCenter)

        diff_card = QFrame()
        diff_card.setObjectName("cardFrame")
        diff_card.setMaximumWidth(520)
        diff_card_lay = QVBoxLayout(diff_card)
        diff_card_lay.setContentsMargins(24, 24, 24, 24)
        diff_card_lay.setSpacing(12)

        icon_lbl = QLabel("⚖️")
        icon_lbl.setStyleSheet("font-size: 32pt;")
        icon_lbl.setAlignment(Qt.AlignCenter)
        diff_card_lay.addWidget(icon_lbl)

        d_title = QLabel("Diff Checker")
        d_title.setStyleSheet("font-size: 14pt; font-weight: 700;")
        d_title.setAlignment(Qt.AlignCenter)
        diff_card_lay.addWidget(d_title)

        d_desc = QLabel(
            "The Diff Checker workspace is not yet available.\n\n"
            "This destination is reserved for future integration. Your active Context Dumper "
            "rules, selected manifests, and working state remain preserved."
        )
        d_desc.setStyleSheet("color: #9aa2af; font-size: 9pt; line-height: 1.4;")
        d_desc.setWordWrap(True)
        d_desc.setAlignment(Qt.AlignCenter)
        diff_card_lay.addWidget(d_desc)

        btn_back_dumper = QPushButton("Return to Context Dumper")
        btn_back_dumper.setObjectName("primaryAction")
        btn_back_dumper.clicked.connect(lambda: self._set_nav_destination(0))
        diff_card_lay.addWidget(btn_back_dumper, alignment=Qt.AlignCenter)

        diff_lay.addWidget(diff_card)
        self.main_stack.addWidget(diff_page)

        # --- Page 2: In-Rail Settings Workspace (Section 10) ---
        self.settings_view = SettingsView(self.settings, self.gui_state, self.config_mgr, self.gui_state_mgr)
        self.settings_view.settings_saved.connect(self._on_settings_saved)
        self.main_stack.addWidget(self.settings_view)

        self.setCentralWidget(central_widget)

        # Restore remembered splitter geometries
        self.split_main.setSizes(self.gui_state.splitter_main)
        self.split_center.setSizes(self.gui_state.splitter_center)
        self.split_col2.setSizes(self.gui_state.splitter_col2)
        self.split_col4.setSizes(self.gui_state.splitter_col4)

        # Permanent Status Bar
        self.status_memory_label = QLabel("RAM: -- MB")
        self.status_memory_label.setStyleSheet("padding: 0 8px; color: #9aa2af; font-family: Consolas, monospace;")
        self.status_version_label = QLabel(f"v{__version__} (Build {__build__})")
        self.status_version_label.setStyleSheet("padding: 0 8px; color: #9aa2af; font-family: Consolas, monospace;")

        self.statusBar().addPermanentWidget(self.status_memory_label)
        self.statusBar().addPermanentWidget(self.status_version_label)
        self.statusBar().showMessage("Ready.")

        self.mem_timer = QTimer(self)
        self.mem_timer.timeout.connect(self._refresh_memory_stat)
        self.mem_timer.start(2000)
        self._refresh_memory_stat()

    # ------------------------------------------------------------------------
    # NAVIGATION RAIL
    # ------------------------------------------------------------------------

    def _set_nav_destination(self, index: int) -> None:
        self.gui_state.active_nav_index = index
        self.main_stack.setCurrentIndex(index)
        self.btn_nav_dumper.setProperty("active", "true" if index == 0 else "false")
        self.btn_nav_diff.setProperty("active", "true" if index == 1 else "false")
        self.btn_nav_settings.setProperty("active", "true" if index == 2 else "false")

        for b in [self.btn_nav_dumper, self.btn_nav_diff, self.btn_nav_settings]:
            b.style().unpolish(b)
            b.style().polish(b)

    # ------------------------------------------------------------------------
    # THEME & WORKSPACE PERSISTENCE
    # ------------------------------------------------------------------------

    def _apply_theme(self) -> None:
        ThemeEngine.apply_theme(QApplication.instance(), self.gui_state.theme, self.gui_state.font_size)

    def closeEvent(self, event) -> None:
        self.gui_state.window_width = self.width()
        self.gui_state.window_height = self.height()
        self.gui_state.splitter_main = self.split_main.sizes()
        self.gui_state.splitter_center = self.split_center.sizes()
        self.gui_state.splitter_col2 = self.split_col2.sizes()
        self.gui_state.splitter_col4 = self.split_col4.sizes()
        self.gui_state.console_expanded = self.console_is_expanded
        self.gui_state_mgr.save_state(self.gui_state)
        event.accept()

    def _log(self, text: str, severity: str = "INFO") -> None:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        is_dark = (self.gui_state.theme != "Light")
        color = "#10b981" if severity == "SUCCESS" else ("#ef4444" if severity == "ERROR" else ("#f59e0b" if severity == "WARN" else ("#9aa2af" if is_dark else "#4b5563")))
        line = f'<span style="color: {color};">[{ts}] [{severity}]</span> {text}'
        self.console_log.append(line)
        self.console_log.moveCursor(QTextCursor.End)

    def _refresh_memory_stat(self) -> None:
        mem = get_process_memory_mb()
        self.status_memory_label.setText(f"RAM: {mem:.1f} MB")

    def _toggle_console_expanded(self) -> None:
        sizes = self.split_center.sizes()
        if not sizes or len(sizes) < 2:
            return
        total = sum(sizes)
        if self.console_is_expanded:
            self.split_center.setSizes([total - 75, 75])
            self.btn_expand_console.setText("▲ Expand")
            self.console_is_expanded = False
        else:
            self.split_center.setSizes([max(100, total - 260), 260])
            self.btn_expand_console.setText("▼ Collapse")
            self.console_is_expanded = True

    # ------------------------------------------------------------------------
    # EXPLORER & INSPECTION
    # ------------------------------------------------------------------------

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Root Folder", str(Path.home()))
        if folder:
            self._set_explorer_root(Path(folder))

    def _set_explorer_root(self, root_path: Path) -> None:
        self.current_root = root_path.resolve()
        self.gui_state.last_root = str(self.current_root)
        self.root_label.setText(str(self.current_root))
        idx = self.file_model.setRootPath(str(self.current_root))
        self.file_tree.setRootIndex(idx)

        filters = QDir.AllEntries | QDir.NoDotAndDotDot | QDir.AllDirs
        if self.gui_state.show_hidden_files:
            filters |= QDir.Hidden
        self.file_model.setFilter(filters)

    def _on_tree_selection_changed(self, current, previous) -> None:
        path = Path(self.file_model.filePath(current))
        if not path.exists():
            self.structured_inspector.show_empty_state()
            return
        self._update_inspector(path)
        self._update_preview(path)

    def _update_inspector(self, file_path: Path) -> None:
        out_dir = self.base_dir / self.settings.output_directory
        exp = RuleEngine.explain_file(file_path, self.active_manifest_rules, self.settings, out_dir)
        is_dark = (self.gui_state.theme != "Light")
        self.structured_inspector.update_inspection(file_path, exp, is_dark)

    def _update_preview(self, file_path: Path) -> None:
        if not self.gui_state.preview_visible or not file_path.is_file():
            self.preview_text.clear()
            return

        try:
            sz = file_path.stat().st_size
            if sz > 256 * 1024:
                self.preview_text.setPlainText(f"(File size is {sz/1024:.1f} KB. Previews are capped at 256 KB)")
                return
            content, enc, err = EncodingDetector.read_and_decode(file_path, self.settings.max_file_size, self.settings.binary_detection)
            self.preview_text.setPlainText(content or (f"(Preview unavailable: {err})" if err else "(Empty file)"))
        except Exception as e:
            self.preview_text.setPlainText(f"(Preview error: {e})")

    # ------------------------------------------------------------------------
    # MANIFESTS & COMBINATIONS (Section 5)
    # ------------------------------------------------------------------------

    def _refresh_manifest_list(self) -> None:
        self.discovered_manifests = ManifestDiscovery.discover(self.base_dir)
        self.manifest_list.clear()
        for m in self.discovered_manifests:
            item = QListWidgetItem(f"[{m.ident}]  {m.filename}")
            item.setData(Qt.UserRole, m)
            self.manifest_list.addItem(item)

        self.manifest_count_badge.setText(str(len(self.discovered_manifests)))
        self._refresh_combinations_tree()

    def _refresh_combinations_tree(self) -> None:
        self.combinations_tree.clear()
        discovered_names = {m.filename for m in self.discovered_manifests}

        for h in self.settings.multi_select_history:
            parent_item = QTreeWidgetItem([f"📁 {h.name} ({len(h.manifest_filenames)})"])
            parent_item.setData(0, Qt.UserRole, h)

            for fn in h.manifest_filenames:
                if fn in discovered_names:
                    child = QTreeWidgetItem([f"📄 {fn}"])
                    child.setData(0, Qt.UserRole, (h, fn))
                else:
                    child = QTreeWidgetItem([f"⚠️ {fn} [Missing]"])
                    child.setForeground(0, QColor("#ef4444"))
                    child.setData(0, Qt.UserRole, (h, None))
                parent_item.addChild(child)

            self.combinations_tree.addTopLevelItem(parent_item)
            parent_item.setExpanded(True)

    def _on_manifest_selection_changed(self) -> None:
        items = self.manifest_list.selectedItems()
        self.selected_manifests = [it.data(Qt.UserRole) for it in items]
        self.active_manifest_rules.clear()
        for m in self.selected_manifests:
            rules, _, _ = CSVManifestParser.parse_manifest(m.path, self.base_dir)
            self.active_manifest_rules.extend(rules)

        self._log(f"Active manifests: {len(self.selected_manifests)} loaded ({len(self.active_manifest_rules)} rules).")

        if len(self.selected_manifests) == 1:
            self.manifest_contents.display_manifest(self.selected_manifests[0], self.base_dir)
        elif len(self.selected_manifests) > 1:
            self.manifest_contents.display_combination("Active Selection", self.selected_manifests, self.base_dir)
        else:
            self.manifest_contents.show_empty_state()

        curr = self.file_tree.currentIndex()
        if curr.isValid():
            self._update_inspector(Path(self.file_model.filePath(curr)))

    def _on_combination_tree_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        data = item.data(0, Qt.UserRole)
        if isinstance(data, tuple):
            h, fn = data
            if fn:
                m_match = next((m for m in self.discovered_manifests if m.filename == fn), None)
                if m_match:
                    self.manifest_contents.display_manifest(m_match, self.base_dir)
        elif data is not None:
            h = data
            matching = [m for m in self.discovered_manifests if m.filename in h.manifest_filenames]
            self.manifest_contents.display_combination(h.name, matching, self.base_dir)

    def _on_combination_tree_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        data = item.data(0, Qt.UserRole)
        h = data[0] if isinstance(data, tuple) else data
        if not h:
            return

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
            self._log(f"Created manifest '{p.name}'.", "SUCCESS")

    def _edit_selected_manifest(self) -> None:
        items = self.manifest_list.selectedItems()
        if not items:
            QMessageBox.information(self, "Edit Manifest", "Please select a manifest in the list to edit.")
            return
        m: ManifestInfo = items[0].data(Qt.UserRole)
        self._edit_manifest_direct(m.path)

    def _edit_manifest_direct(self, manifest_path: Path) -> None:
        dlg = ManifestEditorDialog(self, manifest_path)
        if dlg.exec() == QDialog.Accepted:
            self._on_manifest_selection_changed()
            self._log(f"Saved changes to '{manifest_path.name}'.", "SUCCESS")

    def _set_explicit_rule(self, action: str) -> None:
        curr = self.file_tree.currentIndex()
        if not curr.isValid():
            return
        path = Path(self.file_model.filePath(curr))
        if not self.selected_manifests:
            QMessageBox.warning(self, "No Manifest", "Select a manifest in Column 2 to add rules to.")
            return

        target_manifest = self.selected_manifests[0].path
        with open(target_manifest, "a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([action, "PATH", str(path)])

        self._on_manifest_selection_changed()
        self._update_inspector(path)
        self._log(f"Added [{action} PATH {path.name}] to '{target_manifest.name}'.", "SUCCESS")

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

        res = menu.exec(self.file_tree.viewport().mapToGlobal(pos))
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

    def _on_mode_changed(self, mode: str) -> None:
        self.gui_state.output_mode = mode
        self.gui_state_mgr.save_state(self.gui_state)

    @Slot(Settings, GuiState)
    def _on_settings_saved(self, s: Settings, gs: GuiState) -> None:
        self.settings = s
        self.gui_state = gs
        self._apply_theme()
        self.preview_frame.setVisible(self.gui_state.preview_visible)
        self.console_frame.setVisible(self.gui_state.console_visible)
        self._set_explorer_root(self.current_root)
        self._log("Settings applied.", "SUCCESS")

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
            QMessageBox.warning(self, "No Selection", "Select at least one manifest from Column 2 to dump.")
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
            self._log(f"Operation failed/cancelled: {status}", "ERROR")
            QMessageBox.critical(self, "Generation Failed", f"Operation failed: {status}")

# ============================================================================
# 9. OUTPUT WORKER THREAD
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
                self.log_message.emit("Scanning filesystem roots...", "INFO")
                disc_files: List[DiscoveredFile] = []
                for m in self.selected_manifests:
                    rules, _, _ = CSVManifestParser.parse_manifest(m.path, self.base_dir)
                    res = FilesystemScanner.scan_manifest(m, rules, self.settings, out_dir, check_cancelled=lambda: self.cancelled)
                    disc_files.extend(res.discovered_files)

                eligible = [df for df in disc_files if df.match_result.eligible]
                self.log_message.emit(f"Found {len(eligible)} eligible files. Staging transactional export...", "INFO")

                exporter = DumpToFilesEngine(self.settings, out_dir)
                base_name = "_".join(m.path.stem for m in self.selected_manifests) or "export"
                final_dir, report = exporter.export_files(
                    eligible, base_name=base_name,
                    progress_cb=lambda c, t: self.progress.emit(c, t),
                    check_cancelled=lambda: self.cancelled
                )
                self.finished.emit("SUCCESS", str(final_dir))
            else:
                self.log_message.emit("Generating single TXT context dump...", "INFO")
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
# 10. LAUNCH ENTRY POINT
# ============================================================================

def launch_gui(base_dir: Path) -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow(base_dir)
    window.show()
    app.exec()
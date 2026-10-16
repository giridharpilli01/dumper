import os
import pytest
from pathlib import Path

# Force Qt offscreen platform before importing QtGui/QtWidgets
os.environ["QT_QPA_PLATFORM"] = "offscreen"

def test_headless_gui_instantiation(tmp_path: Path):
    from PySide6.QtWidgets import QApplication
    from gui import MainWindow, GuiStateManager

    app = QApplication.instance() or QApplication(["ai-context-dumper-test"])
    
    # Instantiate MainWindow targeting temporary test workspace
    window = MainWindow(tmp_path)
    assert window is not None
    assert window.windowTitle() == "AI Context Dumper"
    assert window.centralWidget() is not None

    # Verify key pane models exist
    assert window.manifest_list is not None
    assert window.file_tree is not None
    assert window.inspector_text is not None
    assert window.preview_text is not None
    assert window.console_log is not None

    # Test clean shutdown and state persistence
    window.close()
    state_file = tmp_path / "gui_state.json"
    assert state_file.exists()
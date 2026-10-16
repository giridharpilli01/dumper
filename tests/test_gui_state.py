import json
import pytest
from pathlib import Path
from gui import GuiStateManager, GuiState

def test_gui_state_defaults(tmp_path: Path):
    mgr = GuiStateManager(tmp_path)
    state = mgr.load_state()
    assert state.theme == "System"
    assert state.show_hidden_files is False
    assert state.preview_visible is False
    assert state.inspector_visible is True
    assert state.console_visible is True

def test_gui_state_save_and_reload(tmp_path: Path):
    mgr = GuiStateManager(tmp_path)
    state = mgr.load_state()
    state.theme = "Dark"
    state.show_hidden_files = True
    state.last_root = str(tmp_path)
    mgr.save_state(state)

    reloaded = mgr.load_state()
    assert reloaded.theme == "Dark"
    assert reloaded.show_hidden_files is True
    assert reloaded.last_root == str(tmp_path)

def test_gui_state_recovery_on_corrupt_json(tmp_path: Path):
    state_file = tmp_path / "gui_state.json"
    state_file.write_text("{ corrupt json ...", encoding="utf-8")
    mgr = GuiStateManager(tmp_path)
    state = mgr.load_state()
    # Falls back gracefully to safe defaults without crashing
    assert state.theme == "System"
    assert state_file.exists()
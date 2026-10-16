import json
import pytest
from pathlib import Path
from dump import Settings, ConfigManager, DEFAULT_MAX_FILE_SIZE, SCHEMA_VERSION

def test_settings_default_values():
    s = Settings()
    assert s.schema_version == SCHEMA_VERSION
    assert s.max_file_size == DEFAULT_MAX_FILE_SIZE
    assert s.allow_extensionless is False
    assert s.binary_detection is True
    assert ".git" in s.skipped_directories

def test_max_file_size_hard_safety_ceiling():
    data = {
        "schema_version": SCHEMA_VERSION,
        "max_file_size": 10 * 1024 * 1024  # Attempt 10 MB > 5 MB
    }
    with pytest.raises(ValueError, match="cannot exceed the hard safety limit"):
        Settings.from_dict(data)

def test_config_bootstrap_and_recovery(tmp_path: Path):
    cfg_mgr = ConfigManager(tmp_path)
    # Missing settings -> creates default
    settings = cfg_mgr.bootstrap_settings(interactive=False)
    assert cfg_mgr.settings_path.exists()
    assert cfg_mgr.example_csv_path.exists()
    assert settings.schema_version == SCHEMA_VERSION

    # Write corrupt JSON
    cfg_mgr.settings_path.write_text("{ corrupt json ...", encoding="utf-8")
    recovered = cfg_mgr.bootstrap_settings(interactive=False)
    assert recovered.schema_version == SCHEMA_VERSION
    assert (tmp_path / "settings-old(1).json").exists()
from pathlib import Path

from focuspilot.config import load_config


def test_load_config_uses_local_app_data(tmp_path: Path) -> None:
    config = load_config({"LOCALAPPDATA": str(tmp_path)})

    assert config.data_dir == tmp_path / "FocusPilot"
    assert config.database_path == config.data_dir / "focuspilot.db"
    assert config.log_path == config.data_dir / "logs" / "focuspilot.log"


def test_load_config_has_portable_home_fallback(tmp_path: Path) -> None:
    config = load_config({}, home=tmp_path)

    assert config.data_dir == tmp_path / "AppData" / "Local" / "FocusPilot"

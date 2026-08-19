import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from nanosense.gui.lspr_ai_analysis_window import LSPRAIAnalysisWindow
from nanosense.gui.settings_dialog import SettingsDialog
from nanosense.ml import lspr_backend_factory
from nanosense.ml.lspr_backend_factory import create_lspr_backend
from nanosense.ml.lspr_backend_protocol import HealthCheckResponse
from nanosense.utils import config_manager


_APP = None


def qapp():
    global _APP
    if _APP is None:
        _APP = QApplication.instance() or QApplication([])
    return _APP


def write_config(monkeypatch, tmp_path: Path, payload):
    config_dir = tmp_path / "config"
    config_file = config_dir / "config.json"
    config_dir.mkdir()
    config_file.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(config_manager, "CONFIG_DIR", str(config_dir))
    monkeypatch.setattr(config_manager, "CONFIG_FILE", str(config_file))
    return config_file


def test_default_settings_use_the_canonical_backend_key():
    settings = config_manager.get_default_settings()

    assert settings["lspr_backend_mode"] == "auto"
    assert settings["lspr_subprocess_python"] == ""
    assert settings["lspr_cea_model_enabled"] is False
    assert settings["lspr_cea_model_artifact"] == ""
    assert settings["lspr_cea_runner_path"] == ""
    assert settings["lspr_cea_runner_python"] == ""
    assert settings["lspr_cea_runner_timeout"] == 30.0
    assert "lspr_default_model_mode" not in settings
    assert "backend_mode" not in settings


def test_load_settings_migrates_legacy_keys_in_priority_order(monkeypatch, tmp_path):
    config_file = write_config(
        monkeypatch,
        tmp_path,
        {"lspr_default_model_mode": "subprocess", "backend_mode": "inprocess"},
    )

    settings = config_manager.load_settings()

    assert settings["lspr_backend_mode"] == "subprocess"
    assert "lspr_default_model_mode" not in settings
    assert "backend_mode" not in settings
    persisted = json.loads(config_file.read_text(encoding="utf-8"))
    assert persisted["lspr_backend_mode"] == "subprocess"
    assert "lspr_default_model_mode" not in persisted
    assert "backend_mode" not in persisted


def test_canonical_backend_key_wins_over_legacy_values(monkeypatch, tmp_path):
    write_config(
        monkeypatch,
        tmp_path,
        {
            "lspr_backend_mode": "inprocess",
            "lspr_default_model_mode": "subprocess",
            "backend_mode": "auto",
        },
    )

    settings = config_manager.load_settings()

    assert settings["lspr_backend_mode"] == "inprocess"


def test_invalid_backend_mode_falls_back_to_safe_default(monkeypatch, tmp_path):
    config_file = write_config(monkeypatch, tmp_path, {"lspr_backend_mode": "broken"})

    settings = config_manager.load_settings()

    assert settings["lspr_backend_mode"] == "auto"
    persisted = json.loads(config_file.read_text(encoding="utf-8"))
    assert persisted["lspr_backend_mode"] == "auto"


@pytest.mark.parametrize(
    "mode, expected_backend",
    [
        ("inprocess", lspr_backend_factory.InProcessLSPRBackend),
        ("subprocess", lspr_backend_factory.SubprocessLSPRBackend),
    ],
)
def test_backend_factory_uses_canonical_mode(mode, expected_backend):
    backend = create_lspr_backend({"lspr_backend_mode": mode})

    assert isinstance(backend, expected_backend)


def test_backend_factory_auto_mode_uses_health_check(monkeypatch):
    class MarkerBackend:
        def __init__(self, config=None):
            self.config = config or {}

        def health_check(self):
            return HealthCheckResponse(ok=True, backend="marker")

    monkeypatch.setattr(lspr_backend_factory, "InProcessLSPRBackend", MarkerBackend)
    monkeypatch.setattr(lspr_backend_factory, "SubprocessLSPRBackend", MarkerBackend)

    backend = create_lspr_backend({"lspr_backend_mode": "auto"})

    assert isinstance(backend, MarkerBackend)


def test_backend_factory_rejects_invalid_canonical_mode():
    with pytest.raises(ValueError, match="lspr_backend_mode"):
        create_lspr_backend({"lspr_backend_mode": "broken"})


def test_settings_dialog_reads_and_saves_canonical_mode():
    qapp()
    dialog = SettingsDialog({"lspr_backend_mode": "subprocess"})

    try:
        assert dialog.lspr_backend_mode_combo.currentData() == "subprocess"
        dialog.lspr_backend_mode_combo.setCurrentIndex(1)
        dialog._save_and_accept()

        settings = dialog.get_settings()
        assert settings["lspr_backend_mode"] == "inprocess"
        assert "lspr_default_model_mode" not in settings
    finally:
        dialog.close()


def test_settings_dialog_reads_and_saves_subprocess_python():
    qapp()
    dialog = SettingsDialog({"lspr_subprocess_python": "C:/Python/python.exe"})

    try:
        assert dialog.lspr_subprocess_python_edit.text() == "C:/Python/python.exe"
        dialog.lspr_subprocess_python_edit.setText("C:/Python/py39.exe")
        dialog._save_and_accept()

        assert dialog.get_settings()["lspr_subprocess_python"] == "C:/Python/py39.exe"
    finally:
        dialog.close()


def test_settings_dialog_reads_and_saves_cea_runner_configuration():
    qapp()
    dialog = SettingsDialog(
        {
            "lspr_cea_model_enabled": True,
            "lspr_cea_model_artifact": "C:/models/manifest.json",
            "lspr_cea_runner_path": "C:/models/runner.py",
            "lspr_cea_runner_python": "C:/Python/py39.exe",
            "lspr_cea_runner_timeout": 45.0,
        }
    )

    try:
        assert dialog.lspr_cea_model_enabled_checkbox.isChecked() is True
        assert dialog.lspr_cea_model_artifact_edit.text() == "C:/models/manifest.json"
        assert dialog.lspr_cea_runner_path_edit.text() == "C:/models/runner.py"
        assert dialog.lspr_cea_runner_python_edit.text() == "C:/Python/py39.exe"
        assert dialog.lspr_cea_runner_timeout_spinbox.value() == 45.0

        dialog.lspr_cea_model_enabled_checkbox.setChecked(False)
        dialog.lspr_cea_runner_timeout_spinbox.setValue(60.0)
        dialog._save_and_accept()
        settings = dialog.get_settings()
        assert settings["lspr_cea_model_enabled"] is False
        assert settings["lspr_cea_runner_timeout"] == 60.0
    finally:
        dialog.close()


def test_settings_dialog_tests_connection_without_persisting(monkeypatch):
    qapp()
    created_configs = []

    class StubBackend:
        def health_check(self):
            return HealthCheckResponse(
                ok=True,
                backend="stub",
                details={"master_root": "C:/LSPR_Spectra_Master"},
            )

    def fake_create_backend(config):
        created_configs.append(dict(config))
        return StubBackend()

    monkeypatch.setattr("nanosense.gui.settings_dialog.create_lspr_backend", fake_create_backend)
    monkeypatch.setattr("nanosense.gui.settings_dialog.QMessageBox.information", lambda *args: None)
    monkeypatch.setattr("nanosense.gui.settings_dialog.QMessageBox.warning", lambda *args: None)
    monkeypatch.setattr("nanosense.gui.settings_dialog.QMessageBox.critical", lambda *args: None)

    dialog = SettingsDialog({"lspr_backend_mode": "subprocess"})
    try:
        dialog.lspr_master_root_edit.setText("C:/LSPR_Spectra_Master")
        dialog.lspr_subprocess_python_edit.setText("C:/Python/py39.exe")
        dialog._test_lspr_connection()

        assert created_configs == [
            {
                "lspr_master_root": "C:/LSPR_Spectra_Master",
                "lspr_backend_mode": "subprocess",
                "lspr_subprocess_python": "C:/Python/py39.exe",
            }
        ]
        assert dialog.result() == 0
    finally:
        dialog.close()


def test_analysis_window_rebuilds_service_after_config_reload(monkeypatch):
    qapp()
    created_configs = []

    class StubService:
        def __init__(self, config=None):
            created_configs.append(dict(config or {}))

    monkeypatch.setattr(
        "nanosense.gui.lspr_ai_analysis_window.LSPRAIService",
        StubService,
    )
    window = LSPRAIAnalysisWindow(config={"lspr_backend_mode": "auto"})

    window.reload_config({"lspr_backend_mode": "subprocess"})

    assert created_configs == [{"lspr_backend_mode": "subprocess"}]
    assert window.config["lspr_backend_mode"] == "subprocess"
    window.close()

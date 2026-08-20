import json
import os
from nanosense.utils.logging_config import get_logger


logger = get_logger(__name__)


CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".nanosense")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
LSPR_BACKEND_MODE_KEY = "lspr_backend_mode"
LSPR_BACKEND_MODES = ("auto", "inprocess", "subprocess")
_LEGACY_LSPR_BACKEND_KEYS = ("lspr_default_model_mode", "backend_mode")


def normalize_lspr_backend_mode(value):
    mode = str(value or "auto").strip().lower()
    if mode in LSPR_BACKEND_MODES:
        return mode
    return "auto"


def _migrate_lspr_backend_settings(settings, source_settings=None):
    migrated = dict(settings)
    source = source_settings if source_settings is not None else settings
    if LSPR_BACKEND_MODE_KEY in source:
        raw_mode = source[LSPR_BACKEND_MODE_KEY]
    elif "lspr_default_model_mode" in source:
        raw_mode = source["lspr_default_model_mode"]
    elif "backend_mode" in source:
        raw_mode = source["backend_mode"]
    else:
        raw_mode = "auto"

    migrated[LSPR_BACKEND_MODE_KEY] = normalize_lspr_backend_mode(raw_mode)
    for legacy_key in _LEGACY_LSPR_BACKEND_KEYS:
        migrated.pop(legacy_key, None)
    return migrated


def get_default_settings():
    default_db_path = os.path.join(CONFIG_DIR, "nanosense_data.db")
    return {
        "default_save_path": "",
        "default_load_path": "",
        "analysis_wl_start": 450.0,
        "analysis_wl_end": 750.0,
        "theme": "dark",
        "database_path": default_db_path,
        "lspr_master_root": "",
        LSPR_BACKEND_MODE_KEY: "auto",
        "lspr_subprocess_python": "",
        "lspr_cea_model_enabled": False,
        "lspr_cea_model_artifact": "",
        "lspr_cea_runner_path": "",
        "lspr_cea_runner_python": "",
        "lspr_cea_runner_timeout": 30.0,
        "lspr_default_artifact_dir": "",
        "lspr_enable_digital_twin_overlay": True,
        "lspr_batch_export_dir": "",
        "onboarding_welcome_done": False,
        "onboarding_main_window_done": False,
        "mock_api_config": {
            "mode": "dynamic",
            "static_peak_pos": 650.0,
            "static_peak_amp": 15000.0,
            "static_peak_width": 10.0,
            "noise_level": 50.0,
            "dynamic_initial_pos": 650.0,
            "dynamic_shift_total": 10.0,
            "dynamic_baseline_duration": 5,
            "dynamic_assoc_duration": 20,
            "dynamic_dissoc_duration": 30,
        },
    }


def load_settings():
    defaults = get_default_settings()
    if not os.path.exists(CONFIG_FILE):
        return defaults

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as handle:
            loaded_settings = json.load(handle)
        settings = dict(defaults)
        settings.update(loaded_settings)
        for key, value in defaults.items():
            settings.setdefault(key, value)
            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    settings[key].setdefault(sub_key, sub_value)
        settings = _migrate_lspr_backend_settings(settings, loaded_settings)
        if settings != loaded_settings:
            save_settings(settings)
        return settings
    except (json.JSONDecodeError, IOError) as exc:
        logger.exception("event=config_load_failed")
        return defaults


def save_settings(settings):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        settings = _migrate_lspr_backend_settings(settings)
        with open(CONFIG_FILE, "w", encoding="utf-8") as handle:
            json.dump(settings, handle, indent=4)
    except IOError as exc:
        logger.exception("event=config_save_failed")

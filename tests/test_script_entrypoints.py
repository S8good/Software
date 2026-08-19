import importlib
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


def run_python(*args):
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def test_import_spectra_module_help():
    result = run_python("-m", "scripts.import_spectra", "--help")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "import spectra data" in result.stdout.lower()


def test_generate_demo_database_module_help():
    result = run_python("-m", "scripts.generate_demo_database", "--help")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "generate a demo sqlite database" in result.stdout.lower()


@pytest.mark.parametrize(
    "module_name",
    ["scripts.import_spectra", "scripts.generate_demo_database"],
)
def test_script_main_accepts_explicit_argv(module_name):
    module = importlib.import_module(module_name)
    with pytest.raises(SystemExit) as exc_info:
        module.main(["--help"])
    assert exc_info.value.code == 0

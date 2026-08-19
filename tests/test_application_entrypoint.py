import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def run_python(*args):
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def test_python_module_help_exits_without_starting_qt():
    result = run_python("-m", "nanosense", "--help")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "usage: nanosense" in result.stdout.lower()


def test_importing_main_does_not_create_qapplication():
    code = (
        "from PyQt5.QtWidgets import QApplication; "
        "import main; "
        "assert QApplication.instance() is None; "
        "print('IMPORT_OK')"
    )
    result = run_python("-c", code)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "IMPORT_OK" in result.stdout

from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile

from packaging.requirements import Requirement
import tomli


ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"

EXPECTED_RUNTIME = {
    "pyqt5": "==5.15.10",
    "pyqtgraph": "==0.12.4",
    "numpy": "==1.26.4",
    "scipy": "==1.10.1",
    "pandas": "==1.3.5",
    "matplotlib": "==3.5.3",
    "colour-science": "==0.4.4",
    "imageio": "==2.37.0",
    "openpyxl": "==3.1.5",
    "python-docx": "==1.2.0",
    "reportlab": "==4.4.5",
    "pythonnet": "==3.0.5",
}


def load_pyproject():
    with PYPROJECT.open("rb") as handle:
        return tomli.load(handle)


def requirement_map(items):
    parsed = (Requirement(item) for item in items)
    return {item.name.lower(): str(item.specifier) for item in parsed}


def test_project_metadata_matches_verified_py39_baseline():
    config = load_pyproject()
    project = config["project"]

    assert project["name"] == "nanosense"
    assert project["version"] == "0.1.0"
    assert project["requires-python"] == ">=3.9,<3.10"
    assert requirement_map(project["dependencies"]) == EXPECTED_RUNTIME
    assert project["optional-dependencies"]["dev"] == ["pytest==8.3.4"]
    assert project["scripts"] == {
        "nanosense": "main:main",
        "nanosense-import-spectra": "scripts.import_spectra:main",
        "nanosense-generate-demo-database": "scripts.generate_demo_database:main",
    }


def test_build_configuration_includes_modules_and_resources():
    config = load_pyproject()
    setuptools = config["tool"]["setuptools"]

    assert config["build-system"]["requires"] == [
        "setuptools==75.1.0",
        "wheel==0.44.0",
    ]
    assert setuptools["py-modules"] == [
        "main",
        "main_acquisition_loop",
        "mock_spectrometer_api",
        "ocean_direct_api",
    ]
    assert setuptools["package-data"]["nanosense"] == [
        "gui/assets/*",
        "gui/assets/icons/*",
        "translations/*.qm",
        "translations/*.ts",
    ]


def test_wheel_contains_entrypoint_assets_and_translation(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(tmp_path),
            str(ROOT),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    wheel = next(tmp_path.glob("nanosense-0.1.0-*.whl"))
    with ZipFile(wheel) as archive:
        names = set(archive.namelist())
        entry_points = archive.read(
            "nanosense-0.1.0.dist-info/entry_points.txt"
        ).decode("utf-8")

    assert "nanosense/gui/assets/app_icon.ico" in names
    assert "nanosense/gui/assets/icons/zoom.png" in names
    assert "nanosense/translations/chinese.qm" in names
    assert "scripts/import_spectra.py" in names
    assert "scripts/generate_demo_database.py" in names
    assert "nanosense = main:main" in entry_points
    assert "nanosense-import-spectra = scripts.import_spectra:main" in entry_points
    assert (
        "nanosense-generate-demo-database = scripts.generate_demo_database:main"
        in entry_points
    )

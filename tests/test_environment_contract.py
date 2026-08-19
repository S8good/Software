from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

EXPECTED_MINIMAL_ENVIRONMENT = """name: py39
channels:
  - conda-forge
  - defaults
dependencies:
  - python=3.9.7
  - pip=24.2
  - setuptools=75.1.0
  - wheel=0.44.0
  - pip:
      - -e .[dev]
"""


def test_requirements_delegates_to_project_metadata():
    content = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    assert lines == ["-e ."]


def test_conda_environment_is_the_minimal_verified_bootstrap():
    content = (ROOT / "environment.yml").read_text(encoding="utf-8")
    assert content == EXPECTED_MINIMAL_ENVIRONMENT


def test_full_environment_snapshot_is_diagnostic_and_portable():
    content = (ROOT / "environment-py39-lock.yml").read_text(encoding="utf-8")
    assert content.startswith(
        "# Generated from the verified Windows py39 environment on 2026-08-19.\n"
        "# Diagnostic snapshot only; use environment.yml for normal installation.\n"
    )
    assert not any(line.startswith("prefix:") for line in content.splitlines())
    assert "  - python=3.9.7=" in content
    assert "      - numpy==1.26.4" in content
    assert "      - pyqtgraph==0.12.4" in content

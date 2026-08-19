# Python 3.9 Dependency Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make NanoSense reproducibly installable from its verified Python 3.9 environment through authoritative project metadata, minimal Conda bootstrap, standard application entry points, and a diagnostic full-environment snapshot.

**Architecture:** `pyproject.toml` becomes the single source of truth for direct dependencies and entry points. `environment.yml` bootstraps a minimal Python 3.9.7 development environment, while `environment-py39-lock.yml` records the complete verified workstation state without becoming the normal install path. Both `python -m nanosense` and the `nanosense` console command delegate to one callable in `main.py`.

**Tech Stack:** Python 3.9.7, setuptools/PEP 517, Conda, pip editable installs, PyQt5, pytest, `importlib.metadata`, and standard-library `zipfile`/`subprocess`.

---

## File Map

| File | Responsibility |
|---|---|
| `pyproject.toml` | Authoritative metadata, exact direct dependencies, build configuration, package data, console script, and pytest defaults |
| `requirements.txt` | Compatibility shim that delegates installation to `pyproject.toml` |
| `environment.yml` | Minimal supported Conda environment using Python 3.9.7 and editable project installation |
| `environment-py39-lock.yml` | Generated, Windows-specific snapshot of the complete verified `py39` environment |
| `main.py` | Existing GUI behavior plus the shared `main(argv=None)` application entry function |
| `nanosense/__main__.py` | Module entry point for `python -m nanosense` |
| `README.md` | Canonical Python 3.9 installation, startup, testing, snapshot, and hardware-driver limitations |
| `tests/test_project_metadata.py` | Metadata, dependency, package-data, and wheel-content contract tests |
| `tests/test_environment_contract.py` | Minimal environment, compatibility requirements, snapshot, and README command contracts |
| `tests/test_application_entrypoint.py` | Subprocess behavior for module entry and import-side-effect regression |

## Preconditions

- Execute every task in the worktree:
  `C:\Users\Spc\Desktop\Spectrochimica Acta Part A\software\.worktrees\m0-py39-baseline`
- Branch must be `improvement/m0-py39-baseline`.
- Use `C:\ProgramData\anaconda3\envs\py39\python.exe` for baseline and RED/GREEN test commands.
- Set `QT_QPA_PLATFORM=offscreen` before GUI-related test runs.
- Do not run the old `pip install -r requirements.txt`; its lower bounds would upgrade the verified environment before the dependency files are corrected.

### Task 1: Add Authoritative Project Metadata and Wheel Contract

**Files:**

- Create: `tests/test_project_metadata.py`
- Create: `pyproject.toml`

- [ ] **Step 1: Write the failing metadata and wheel tests**

Create `tests/test_project_metadata.py`:

```python
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
    assert project["scripts"]["nanosense"] == "main:main"


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
    assert "nanosense = main:main" in entry_points
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pytest tests/test_project_metadata.py -v
```

Expected: FAIL with `FileNotFoundError` for `pyproject.toml` and wheel build failure because project metadata does not exist.

- [ ] **Step 3: Add the minimal `pyproject.toml`**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools==75.1.0", "wheel==0.44.0"]
build-backend = "setuptools.build_meta"

[project]
name = "nanosense"
version = "0.1.0"
description = "Desktop spectroscopy acquisition and analysis software"
readme = "README.md"
requires-python = ">=3.9,<3.10"
dependencies = [
    "PyQt5==5.15.10",
    "pyqtgraph==0.12.4",
    "numpy==1.26.4",
    "scipy==1.10.1",
    "pandas==1.3.5",
    "matplotlib==3.5.3",
    "colour-science==0.4.4",
    "imageio==2.37.0",
    "openpyxl==3.1.5",
    "python-docx==1.2.0",
    "reportlab==4.4.5",
    "pythonnet==3.0.5",
]

[project.optional-dependencies]
dev = ["pytest==8.3.4"]

[project.scripts]
nanosense = "main:main"

[tool.setuptools]
include-package-data = true
py-modules = [
    "main",
    "main_acquisition_loop",
    "mock_spectrometer_api",
    "ocean_direct_api",
]

[tool.setuptools.packages.find]
include = ["nanosense*"]

[tool.setuptools.package-data]
nanosense = [
    "gui/assets/*",
    "gui/assets/icons/*",
    "translations/*.qm",
    "translations/*.ts",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 4: Run the metadata and wheel tests and verify GREEN**

Run:

```powershell
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pytest tests/test_project_metadata.py -v
```

Expected: `3 passed`; wheel creation succeeds without downloading dependencies.

- [ ] **Step 5: Run the existing suite to detect packaging-config regressions**

Run:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pytest -q
```

Expected: `104 passed`.

- [ ] **Step 6: Commit Task 1**

```powershell
git add pyproject.toml tests/test_project_metadata.py
git diff --cached --check
git commit -m "build: add Python 3.9 project metadata"
```

### Task 2: Replace the Shared Environment Export with a Two-Layer Model

**Files:**

- Create: `tests/test_environment_contract.py`
- Modify: `requirements.txt`
- Modify: `environment.yml`
- Create: `environment-py39-lock.yml`

- [ ] **Step 1: Write failing environment contract tests**

Create `tests/test_environment_contract.py`:

```python
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
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pytest tests/test_environment_contract.py -v
```

Expected: all three tests FAIL because the requirements file duplicates dependencies, the Conda file is a full shared export, and the diagnostic lock file is absent.

- [ ] **Step 3: Replace `requirements.txt` with the compatibility shim**

The complete file becomes:

```text
-e .
```

- [ ] **Step 4: Replace `environment.yml` with the minimal bootstrap**

The complete file becomes:

```yaml
name: py39
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
```

- [ ] **Step 5: Generate the full snapshot from the current verified environment**

Run:

```powershell
& 'C:\ProgramData\anaconda3\Scripts\conda.exe' env export --name py39 --file environment-py39-lock.yml
```

Then use `apply_patch` to add these exact two lines before `name: py39`:

```yaml
# Generated from the verified Windows py39 environment on 2026-08-19.
# Diagnostic snapshot only; use environment.yml for normal installation.
```

Use `apply_patch` to remove this generated machine-specific final line:

```yaml
prefix: C:\ProgramData\anaconda3\envs\py39
```

- [ ] **Step 6: Run the contract tests and verify GREEN**

Run:

```powershell
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pytest tests/test_environment_contract.py -v
```

Expected: `3 passed`.

- [ ] **Step 7: Ask Conda to solve the minimal file without creating an environment**

Run:

```powershell
& 'C:\ProgramData\anaconda3\Scripts\conda.exe' env create --dry-run --name nanosense-m0-dry-run --file environment.yml
```

Expected: exit code 0 and a transaction plan containing Python 3.9.7, pip 24.2, setuptools 75.1.0, and wheel 0.44.0.

- [ ] **Step 8: Commit Task 2**

```powershell
git add requirements.txt environment.yml environment-py39-lock.yml tests/test_environment_contract.py
git diff --cached --check
git commit -m "build: define reproducible py39 environments"
```

### Task 3: Add One Shared Application Entry Function

**Files:**

- Create: `tests/test_application_entrypoint.py`
- Modify: `main.py:3-47,138-172`
- Create: `nanosense/__main__.py`

- [ ] **Step 1: Write the failing module-entry test**

Create `tests/test_application_entrypoint.py`:

```python
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
```

- [ ] **Step 2: Run the module-help test and verify RED**

Run:

```powershell
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pytest tests/test_application_entrypoint.py::test_python_module_help_exits_without_starting_qt -v
```

Expected: FAIL with `No module named nanosense.__main__`.

- [ ] **Step 3: Make `main.py` import-safe and expose `main(argv=None)`**

Add `import argparse` with the standard-library imports. Remove the module-level calls to `_install_global_excepthook()` and `configure_pyqtgraph_theme(...)`; those calls move into `main()` after argument parsing.

Replace the existing bottom `if __name__ == '__main__':` block with:

```python
def _build_argument_parser():
    return argparse.ArgumentParser(
        prog="nanosense",
        description="NanoSense spectroscopy acquisition and analysis software",
    )


def main(argv=None):
    _build_argument_parser().parse_args(argv)
    _install_global_excepthook()
    configure_pyqtgraph_theme(load_settings().get("theme", "dark"))

    qt_argv = sys.argv if argv is None else [sys.argv[0], *argv]
    app = QApplication(qt_argv)

    icon_path = os.path.join(
        os.path.dirname(__file__), "nanosense", "gui", "assets", "app_icon.ico"
    )
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    else:
        print(f"警告：应用图标文件未找到于 {icon_path}")

    splash = None
    splash_image_path = os.path.join(
        os.path.dirname(__file__), "nanosense", "gui", "assets", "splash.png"
    )
    if os.path.exists(splash_image_path):
        splash = SplashScreen(splash_image_path)
        splash.show()
        for progress in range(1, 101):
            splash.update_progress(progress)
            time.sleep(0.01)
            app.processEvents()

    show_welcome_screen()
    if splash is not None and welcome_screen:
        splash.finish(welcome_screen)

    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Add the module delegate**

Create `nanosense/__main__.py`:

```python
from main import main


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run the entry-point tests and verify GREEN**

Run:

```powershell
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pytest tests/test_application_entrypoint.py -v
```

Expected: `2 passed`; the command returns before `QApplication` construction when `--help` is supplied.

- [ ] **Step 6: Run main-window and import regressions**

Run:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pytest tests/test_main_window_imports.py tests/test_menu_bar.py tests/test_hardware_vendor_routing.py -v
```

Expected: all selected tests PASS.

- [ ] **Step 7: Commit Task 3**

```powershell
git add main.py nanosense/__main__.py tests/test_application_entrypoint.py
git diff --cached --check
git commit -m "feat: add standard application entry points"
```

### Task 4: Document the Supported Installation Path

**Files:**

- Modify: `tests/test_environment_contract.py`
- Modify: `README.md:253-268,463-497`

- [ ] **Step 1: Add a failing README contract test**

Append to `tests/test_environment_contract.py`:

```python
def test_readme_uses_the_verified_installation_commands():
    content = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "Python 3.9" in content
    assert "Python 3.10+" not in content
    assert "conda env create -f environment.yml" in content
    assert "conda activate py39" in content
    assert 'python -m pip install -e ".[dev]"' in content
    assert "python -m nanosense" in content
    assert "environment-py39-lock.yml" in content
    assert "可编辑安装" in content
    assert "独立 Windows 安装包" in content
```

- [ ] **Step 2: Run the README contract test and verify RED**

Run:

```powershell
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pytest tests/test_environment_contract.py::test_readme_uses_the_verified_installation_commands -v
```

Expected: FAIL because README still recommends Python 3.10+ and lacks the two-layer environment explanation.

- [ ] **Step 3: Replace README section 4.1 with the canonical setup**

Use this content under `### 4.1 环境准备`:

````markdown
当前支持并验证的运行环境为 64 位 Windows 和 Python 3.9。推荐使用 Conda 创建最小开发环境：

```powershell
conda env create -f environment.yml
conda activate py39
python -m nanosense
```

如果已经有 Python 3.9 环境，可使用可编辑安装：

```powershell
python -m pip install -e ".[dev]"
python -m nanosense
```

`environment.yml` 是日常安装入口；`environment-py39-lock.yml` 是当前已验证工作站的完整诊断快照，包含 NanoSense 不直接依赖的工具，不建议作为普通安装入口。

运行测试：

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q
```
````

- [ ] **Step 4: Add the editable-install hardware limitation to known limitations**

Add this paragraph under `## 10. 已知限制与使用建议`:

```markdown
当前发布形式支持从源码目录进行可编辑安装。硬件 DLL 仍从仓库顶层 `drivers/` 目录加载，尚未提供包含厂商驱动的独立 Windows 安装包；驱动重定位、许可核对和安装包验证属于 M4 发布工作。
```

- [ ] **Step 5: Run environment and README contract tests and verify GREEN**

Run:

```powershell
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pytest tests/test_environment_contract.py -v
```

Expected: `4 passed`.

- [ ] **Step 6: Commit Task 4**

```powershell
git add README.md tests/test_environment_contract.py
git diff --cached --check
git commit -m "docs: document the Python 3.9 setup"
```

### Task 5: Verify Editable Installation and Both Commands

**Files:**

- Verify only; no source change expected

- [ ] **Step 1: Install the worktree in editable mode without changing dependency versions**

Run:

```powershell
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pip install --no-deps -e ".[dev]"
```

Expected: successful editable build and installation of `nanosense==0.1.0`.

- [ ] **Step 2: Verify installed dependency consistency**

Run:

```powershell
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pip check
```

Expected: `No broken requirements found.`

- [ ] **Step 3: Verify the module command**

Run:

```powershell
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m nanosense --help
```

Expected: exit code 0 and output beginning with `usage: nanosense`.

- [ ] **Step 4: Verify the console command installed into `py39`**

Run:

```powershell
& 'C:\ProgramData\anaconda3\envs\py39\Scripts\nanosense.exe' --help
```

Expected: exit code 0 and output beginning with `usage: nanosense`.

- [ ] **Step 5: Verify installed metadata and assets**

Run:

```powershell
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -c "from importlib.metadata import version; from importlib.resources import files; assert version('nanosense') == '0.1.0'; assert files('nanosense').joinpath('gui/assets/app_icon.ico').is_file(); assert files('nanosense').joinpath('translations/chinese.qm').is_file(); print('installed metadata/resources: PASS')"
```

Expected: `installed metadata/resources: PASS`.

### Task 6: Verify a Clean Minimal Conda Environment

**Files:**

- Verify only; temporary environment lives under ignored `.pytest_tmp/`

- [ ] **Step 1: Confirm the target prefix is inside the worktree**

Run:

```powershell
$verifyPrefix = Join-Path (Resolve-Path '.').Path '.pytest_tmp\m0-clean-env'
$worktreeRoot = (Resolve-Path '.').Path
if (-not $verifyPrefix.StartsWith($worktreeRoot, [System.StringComparison]::OrdinalIgnoreCase)) { throw 'Verification prefix escaped the worktree' }
$verifyPrefix
```

Expected: an absolute path ending in `.worktrees\m0-py39-baseline\.pytest_tmp\m0-clean-env`.

- [ ] **Step 2: Create the clean environment from the minimal file**

Run:

```powershell
& 'C:\ProgramData\anaconda3\Scripts\conda.exe' env create --prefix $verifyPrefix --file environment.yml
```

Expected: exit code 0; Conda creates Python 3.9.7 and pip installs editable `nanosense[dev]` with the exact direct versions.

- [ ] **Step 3: Verify the clean interpreter and dependency graph**

Run:

```powershell
& "$verifyPrefix\python.exe" -c "import sys; assert sys.version_info[:2] == (3, 9); print(sys.version)"
& "$verifyPrefix\python.exe" -m pip check
```

Expected: Python 3.9.x and `No broken requirements found.`

- [ ] **Step 4: Verify commands in the clean environment**

Run:

```powershell
& "$verifyPrefix\python.exe" -m nanosense --help
& "$verifyPrefix\Scripts\nanosense.exe" --help
```

Expected: both commands exit 0 and print `usage: nanosense`.

- [ ] **Step 5: Run the complete suite in the clean environment**

Run:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
& "$verifyPrefix\python.exe" -m pytest -q
```

Expected: `110 passed` after the nine new metadata, environment, README, and entry-point tests are added.

- [ ] **Step 6: Remove only the verified temporary Conda prefix**

Re-run the containment assertion from Step 1, then run:

```powershell
& 'C:\ProgramData\anaconda3\Scripts\conda.exe' env remove --prefix $verifyPrefix --yes
```

Expected: the `.pytest_tmp\m0-clean-env` prefix is removed; source files are untouched.

### Task 7: Run Final Regression and Record the Branch State

**Files:**

- Verify all M0.1 files and commits

- [ ] **Step 1: Run focused M0.1 tests**

Run:

```powershell
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pytest tests/test_project_metadata.py tests/test_environment_contract.py tests/test_application_entrypoint.py -v
```

Expected: `9 passed`.

- [ ] **Step 2: Run the complete regression suite**

Run:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pytest -q
```

Expected: `110 passed`, zero failures.

- [ ] **Step 3: Run compilation and installed-environment checks**

Run:

```powershell
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m compileall -q main.py main_acquisition_loop.py mock_spectrometer_api.py ocean_direct_api.py nanosense scripts tests
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pip check
```

Expected: compile command exit code 0 and `No broken requirements found.`

- [ ] **Step 4: Confirm repository hygiene**

Run:

```powershell
git diff --check main...HEAD
git status --short --branch
git ls-files | Select-String -Pattern '(^|/)(data|logs|__pycache__|\.pytest_cache|\.pytest_tmp|\.idea|\.vscode|\.worktrees)(/|$)|\.db$|\.log$'
Select-String -Path environment-py39-lock.yml -Pattern '^prefix:'
rg -n "C:/Users/Spc|C:\\Users\\Spc" pyproject.toml environment.yml environment-py39-lock.yml README.md main.py nanosense tests
```

Expected:

- `git diff --check` exits 0.
- status contains no unstaged or untracked project files.
- tracked-file, lock-prefix, and absolute-user-path searches return no matches.

- [ ] **Step 5: Review the five branch commits**

Run:

```powershell
git log --oneline main..HEAD
git diff --stat main...HEAD
```

Expected commits, newest first:

```text
docs: document the Python 3.9 setup
feat: add standard application entry points
build: define reproducible py39 environments
build: add Python 3.9 project metadata
docs: plan Python 3.9 baseline implementation
```

- [ ] **Step 6: Hand off through the branch-finishing workflow**

Invoke the `finishing-a-development-branch` skill. Re-run its required verification, then present merge, push/PR, retention, and cleanup choices without changing `main` until the user selects an integration option.

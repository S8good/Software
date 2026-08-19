# NanoSense Python 3.9 Dependency Baseline Design

**Date:** 2026-08-19
**Status:** Approved
**Scope:** M0.1 only: Python version, dependency declarations, editable installation, application entry points, package resources, and installation documentation.

## 1. Context

NanoSense currently has three inconsistent environment descriptions:

- `README.md` recommends Python 3.10 or newer.
- `environment.yml` pins Python 3.9.7 but is a large historical export of a shared workstation environment.
- `requirements.txt` uses lower bounds that do not match several versions in the tested `py39` environment.

The verified workstation baseline is:

- Python 3.9.7, 64-bit Windows
- PyQt binding 5.15.10 with Qt runtime 5.15.2
- 101 project tests passing
- Project byte-compilation passing

The `py39` environment also contains unrelated tools and frameworks such as Jupyter, Django, CUDA packages, and documentation tooling. Requiring every user to install that entire environment would make installation slow and fragile. Omitting it entirely would lose useful reproduction evidence.

## 2. Decision

Use a two-layer dependency model:

1. A minimal, installable project definition containing only NanoSense direct runtime and development dependencies.
2. A complete snapshot of the currently verified `py39` environment for diagnostic reproduction.

The minimal definition is the supported installation path. The full snapshot records provenance; it is not the default installation path and does not imply that every package in it is required by NanoSense.

## 3. Python Support Policy

- Project metadata declares `requires-python = ">=3.9,<3.10"`.
- `environment.yml` pins the verified interpreter version, Python 3.9.7.
- Python 3.10 or newer is not advertised until the hardware SDKs and the full test suite pass in that environment.
- Future Python upgrades require a separate compatibility change and updated environment snapshot.

This policy distinguishes the supported Python series from the exact reproducible development interpreter.

## 4. Dependency Layers

### 4.1 Runtime Dependencies

The initial runtime dependency set is derived from imports in `main.py`, `nanosense/`, hardware integration code, and export paths. Versions match the verified `py39` environment.

| Distribution | Version | Purpose |
|---|---:|---|
| PyQt5 | 5.15.10 | Desktop GUI |
| pyqtgraph | 0.12.4 | Interactive spectrum plotting |
| numpy | 1.26.4 | Numeric arrays and spectrum calculations |
| scipy | 1.10.1 | Signal processing, fitting, and sparse operations |
| pandas | 1.3.5 | Tabular import, export, and reports |
| matplotlib | 3.5.3 | Static plots and report figures |
| colour-science | 0.4.4 | Colorimetry calculations |
| imageio | 2.37.0 | Image reading used by GUI analysis paths |
| openpyxl | 3.1.5 | Excel import and export engine |
| python-docx | 1.2.0 | Word report generation |
| reportlab | 4.4.5 | PDF report generation |
| pythonnet | 3.0.5 | IdeaOptics .NET bridge |

All initial runtime versions are exact pins because the objective of M0.1 is to reproduce the known-good environment, not to establish broad compatibility ranges. Relaxing pins may be considered only after CI tests a compatibility matrix.

PyTorch, CUDA, scikit-learn, XGBoost, Jupyter, and Django are not NanoSense direct runtime dependencies. They remain visible in the complete snapshot when installed in `py39`. LSPR master-model dependencies belong to the separately configured LSPR environment or subprocess backend until the two projects define a shared deployment contract.

### 4.2 Development Dependencies

The initial `dev` optional dependency group contains:

- `pytest==8.3.4`

No new test framework is introduced in M0.1. `pytest-qt`, coverage tooling, linting, and type checking belong to later test and CI milestones.

### 4.3 Build Dependencies

The project uses setuptools with a PEP 517 build declaration. The initial build baseline is `setuptools==75.1.0` and `wheel==0.44.0`, matching the verified environment. Build dependencies are isolated from runtime dependencies.

## 5. File Responsibilities

### `pyproject.toml`

This is the authoritative project metadata and dependency declaration. It defines:

- project name `nanosense` and initial development version `0.1.0`;
- supported Python series;
- exact runtime dependencies;
- the `dev` optional dependency group;
- setuptools package discovery;
- package data for GUI assets and translations;
- the `nanosense` console entry point;
- pytest defaults where practical.

### `requirements.txt`

This remains as a compatibility entry for users and tools expecting a requirements file. It must not contain an independently maintained dependency list. It references the installable project so that dependency truth remains in `pyproject.toml`.

### `environment.yml`

This becomes the minimal supported Conda bootstrap:

- Python 3.9.7;
- pip compatible with Python 3.9;
- editable installation of the project with the `dev` extra.

It must not contain Jupyter, CUDA, Django, or transitive packages unless they become direct NanoSense requirements.

### `environment-py39-lock.yml`

This is a generated full snapshot of the verified workstation environment. The absolute `prefix` field is removed before commit. A header explains:

- when and from which environment it was generated;
- that it is Windows-specific;
- that it is for diagnostics rather than normal installation;
- that pip packages with CUDA build tags may require their original package index.

The snapshot is regenerated only after a dependency baseline has passed the complete verification suite.

### `README.md`

The quick-start section presents one canonical path:

```powershell
conda env create -f environment.yml
conda activate py39
python -m nanosense
```

It also documents editable pip installation for an existing Python 3.9 environment and explains the difference between the minimal environment and the full snapshot.

## 6. Application Entry Points

M0.1 provides two equivalent entry points:

- `python -m nanosense`
- `nanosense`

`main.py` exposes a callable `main(argv=None)` while retaining its existing GUI startup behavior. `nanosense/__main__.py` delegates to that callable, and the console script points to the same function. Both entry points support `--help` without creating a `QApplication` or entering the Qt event loop, making installation verification deterministic.

Startup refactoring is limited to extracting the current `if __name__ == "__main__"` block. Hardware selection, welcome-screen behavior, theme selection, and window lifecycle are not redesigned in M0.1.

## 7. Package Resources and Hardware Drivers

The installable package includes resources located under the Python package:

- `nanosense/gui/assets/`, including nested icons;
- compiled and source translation files under `nanosense/translations/`.

Hardware DLLs currently live in the top-level `drivers/` directory. M0.1 supports editable installation from the source tree, so existing driver lookup behavior remains available. Moving or bundling vendor DLLs into a distributable wheel or Windows installer is deferred to M4 because it requires driver loading tests and license review.

The README must state this limitation: the editable development installation is supported, while a standalone redistributable hardware package is not yet provided.

## 8. Testing Strategy

Implementation follows test-driven development for behavior changes.

### Metadata tests

- Parse `pyproject.toml` and assert the Python constraint.
- Assert the direct dependency names and exact verified versions.
- Assert the `dev` dependency group contains the verified pytest version.
- Assert `requirements.txt` delegates to the project definition rather than duplicating pins.

### Entry-point tests

- Run `python -m nanosense --help` in a subprocess and require exit code 0.
- Invoke the installed console entry point with `--help` and require exit code 0 when available in the active environment.
- Import the entry module without creating a Qt event loop.

### Resource tests

- Resolve representative assets and the compiled Chinese translation through package-relative paths.
- Verify setuptools configuration includes nested asset and translation patterns.

### Regression verification

- Run the complete pytest suite with `QT_QPA_PLATFORM=offscreen`.
- Run `compileall` over application, scripts, and tests.
- Run `pip check` after editable installation.
- Confirm Git does not track environment directories, caches, databases, logs, or local prefixes.

## 9. Error Handling

- Unsupported Python versions fail during installation through project metadata.
- Missing optional LSPR model dependencies are reported by the existing LSPR health check, not installed implicitly by the core application.
- Missing vendor driver prerequisites continue through the existing hardware connection error path.
- Entry-point argument errors return a nonzero exit code and a concise command-line message before Qt initialization.
- Environment snapshot generation fails rather than committing a file containing an absolute `prefix`.

## 10. Acceptance Criteria

M0.1 is complete when all of the following are demonstrated:

1. A clean Windows environment can be created from the minimal `environment.yml`.
2. `python -m pip install -e ".[dev]"` succeeds under Python 3.9.
3. `python -m nanosense --help` and `nanosense --help` exit successfully without opening the GUI.
4. Representative GUI assets and translation files are available through the installed package.
5. All existing and new tests pass in offscreen mode.
6. `compileall` and `pip check` pass.
7. The committed full environment snapshot contains no local absolute prefix.
8. README commands match commands exercised during verification.

## 11. Out of Scope

M0.1 does not:

- upgrade Python or third-party libraries;
- make the LSPR external project part of the core install;
- redesign hardware driver discovery;
- build a Windows installer;
- choose the project license;
- add CI, pytest-qt, coverage enforcement, linting, or type checking;
- implement M0.2 script-entry fixes or M1 LSPR configuration fixes.

These items remain in their existing milestones so that the dependency baseline can be reviewed and reverted independently.

# Script Entry Points Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the spectrum importer and demo database generator available through stable module and installed console entry points.

**Architecture:** Keep each command's implementation in its existing `scripts` module and expose a uniform `main(argv=None) -> int` boundary. Package `scripts` in the wheel, map descriptive console commands to those functions, and verify both source-tree and built-distribution behavior.

**Tech Stack:** Python 3.9, argparse, setuptools/pyproject.toml, pytest, subprocess

---

### Task 1: Define the entry-point contract

**Files:**
- Create: `tests/test_script_entrypoints.py`
- Modify: `tests/test_project_metadata.py`

- [ ] **Step 1: Write subprocess tests for both module help commands**

Create a shared `run_python()` helper and assert that these commands exit with status 0 and print their argparse descriptions:

```python
def test_import_spectra_module_help():
    result = run_python("-m", "scripts.import_spectra", "--help")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "import spectra data" in result.stdout.lower()


def test_generate_demo_database_module_help():
    result = run_python("-m", "scripts.generate_demo_database", "--help")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "generate a demo sqlite database" in result.stdout.lower()
```

- [ ] **Step 2: Write a failing API test for explicit argument lists**

```python
@pytest.mark.parametrize(
    "module_name",
    ["scripts.import_spectra", "scripts.generate_demo_database"],
)
def test_script_main_accepts_explicit_argv(module_name):
    module = importlib.import_module(module_name)
    with pytest.raises(SystemExit) as exc_info:
        module.main(["--help"])
    assert exc_info.value.code == 0
```

- [ ] **Step 3: Write failing metadata and wheel assertions**

Require this exact script mapping and ensure both command modules are installed:

```python
assert project["scripts"] == {
    "nanosense": "main:main",
    "nanosense-import-spectra": "scripts.import_spectra:main",
    "nanosense-generate-demo-database": "scripts.generate_demo_database:main",
}

assert "scripts/import_spectra.py" in names
assert "scripts/generate_demo_database.py" in names
assert "nanosense-import-spectra = scripts.import_spectra:main" in entry_points
assert "nanosense-generate-demo-database = scripts.generate_demo_database:main" in entry_points
```

- [ ] **Step 4: Run the focused tests and verify RED**

Run: `conda run -n py39 python -m pytest tests/test_script_entrypoints.py tests/test_project_metadata.py -q`

Expected: failures showing `generate_demo_database.main()` does not accept an argument, the console script mappings are absent, and the wheel omits `scripts`.

### Task 2: Implement package-safe command entry points

**Files:**
- Create: `scripts/__init__.py`
- Modify: `scripts/import_spectra.py`
- Modify: `scripts/generate_demo_database.py`
- Modify: `pyproject.toml`
- Test: `tests/test_script_entrypoints.py`
- Test: `tests/test_project_metadata.py`

- [ ] **Step 1: Give both commands the same callable boundary**

Use `Optional[List[str]]` and allow argparse to read `sys.argv` when the value is `None`:

```python
def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    # existing command body
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

For the demo generator, extract its existing parser construction into `build_parser()` and retain all current generation behavior.

- [ ] **Step 2: Make `scripts` an installable package**

Add an empty `scripts/__init__.py`, then update package discovery:

```toml
[tool.setuptools.packages.find]
include = ["nanosense*", "scripts*"]
```

- [ ] **Step 3: Register the installed commands**

```toml
[project.scripts]
nanosense = "main:main"
nanosense-import-spectra = "scripts.import_spectra:main"
nanosense-generate-demo-database = "scripts.generate_demo_database:main"
```

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run: `conda run -n py39 python -m pytest tests/test_script_entrypoints.py tests/test_project_metadata.py -q`

Expected: all focused tests pass.

- [ ] **Step 5: Commit the tested implementation**

```powershell
git add pyproject.toml scripts/__init__.py scripts/import_spectra.py scripts/generate_demo_database.py tests/test_script_entrypoints.py tests/test_project_metadata.py
git commit -m "feat: expose data utility entry points"
```

### Task 3: Document the standard commands

**Files:**
- Modify: `README.md`
- Test: `tests/test_script_entrypoints.py`

- [ ] **Step 1: Add a failing README contract test**

```python
def test_readme_documents_standard_script_commands():
    content = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "python -m scripts.import_spectra --help" in content
    assert "python -m scripts.generate_demo_database --help" in content
    assert "nanosense-import-spectra" in content
    assert "nanosense-generate-demo-database" in content
```

- [ ] **Step 2: Run the README test and verify RED**

Run: `conda run -n py39 python -m pytest tests/test_script_entrypoints.py::test_readme_documents_standard_script_commands -q`

Expected: failure because README still documents direct file execution.

- [ ] **Step 3: Replace direct file execution examples**

Document module execution as the source-tree standard and the two console commands as installed equivalents. Keep the existing importer examples and demo database options intact.

- [ ] **Step 4: Run the README test and verify GREEN**

Run: `conda run -n py39 python -m pytest tests/test_script_entrypoints.py -q`

Expected: all script entry-point tests pass.

- [ ] **Step 5: Commit the documentation**

```powershell
git add README.md tests/test_script_entrypoints.py
git commit -m "docs: standardize utility command usage"
```

### Task 4: Verify the installed distribution

**Files:**
- Verify only

- [ ] **Step 1: Install the worktree without network access**

Run: `conda run -n py39 python -m pip install --no-build-isolation --no-deps -e .`

Expected: editable installation succeeds.

- [ ] **Step 2: Exercise both installed commands**

Run: `conda run -n py39 nanosense-import-spectra --help`

Run: `conda run -n py39 nanosense-generate-demo-database --help`

Expected: both commands exit with status 0 and print their help text.

- [ ] **Step 3: Run the full regression suite**

Run: `conda run -n py39 python -m pytest -q`

Expected: all tests pass with no failures.

- [ ] **Step 4: Check repository state and history**

Run: `git status --short --branch`

Run: `git log --oneline main..HEAD`

Expected: the worktree is clean and the M0.2 commits are listed.

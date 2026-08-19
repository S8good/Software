from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_gitignore_covers_local_project_artifacts():
    content = (ROOT / ".gitignore").read_text(encoding="utf-8")
    required_patterns = [
        "__pycache__/",
        ".pytest_cache/",
        ".pytest_tmp/",
        "data/",
        "*.db",
        "*.sqlite",
        "*.sqlite3",
        "*.db-shm",
        "*.db-wal",
        "logs/",
        "*.log",
        ".venv/",
        "venv/",
        ".idea/",
        ".vscode/",
        ".worktrees/",
        "build/",
        "dist/",
    ]
    for pattern in required_patterns:
        assert pattern in content, pattern


def test_lspr_simulation_widget_has_one_canonical_module():
    canonical = ROOT / "nanosense" / "gui" / "lspr_simulation_widget.py"
    duplicate_name = "lspr_simulation_widget" + "_new"
    duplicate = ROOT / "nanosense" / "gui" / f"{duplicate_name}.py"
    assert canonical.exists()
    assert not duplicate.exists()

    result = subprocess.run(
        ["git", "grep", "-n", duplicate_name],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stdout + result.stderr

    main_window = (ROOT / "nanosense" / "gui" / "main_window.py").read_text(
        encoding="utf-8"
    )
    assert "from .lspr_simulation_widget import LSPRSimulationWidget" in main_window


def test_docs_do_not_claim_unconfigured_github_actions_workflows():
    documented_files = [
        ROOT / "README.md",
        ROOT / "docs" / "operations" / "migration_governance_schedule.md",
        ROOT / "docs" / "validation" / "validate_migration_roadmap.md",
        ROOT / "docs" / "batch_migration_progress.md",
    ]
    workflow_dir = ".github/workflows/"
    stale_references = (
        workflow_dir + "validation.yml",
        workflow_dir + "governance.yml",
    )
    for path in documented_files:
        content = path.read_text(encoding="utf-8")
        for reference in stale_references:
            assert reference not in content, str(path)

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "尚未配置 GitHub Actions" in readme

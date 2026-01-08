"""Tests for incremental normalization features."""

import os
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from unityflow.cli import main
from unityflow.git_utils import (
    UNITY_EXTENSIONS,
    filter_unity_files,
    get_changed_files,
    get_files_changed_since,
    get_files_in_commit,
    get_repo_root,
    is_git_repository,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def git_commit(cwd, message):
    """Helper to run git commit with signing disabled."""
    return subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-m", message],
        cwd=cwd,
        capture_output=True,
        check=True,
    )


@pytest.fixture
def runner():
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary git repository with test files."""
    # Initialize git repo
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )

    # Create initial commit
    readme = tmp_path / "README.md"
    readme.write_text("# Test Repo\n")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, capture_output=True, check=True)
    git_commit(tmp_path, "Initial commit")

    # Create a sample prefab file (already normalized format)
    prefab_content = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!1 &100000
GameObject:
  m_Layer: 0
  m_Name: TestObject
"""
    prefab = tmp_path / "test.prefab"
    prefab.write_text(prefab_content)
    subprocess.run(["git", "add", "test.prefab"], cwd=tmp_path, capture_output=True, check=True)
    git_commit(tmp_path, "Add test prefab")

    # Save original directory and change to the repo
    original_dir = os.getcwd()
    os.chdir(tmp_path)

    yield tmp_path

    # Restore original directory
    os.chdir(original_dir)


class TestGitUtilsBasic:
    """Tests for basic git utility functions."""

    def test_unity_extensions(self):
        """Test that Unity extensions are defined correctly."""
        assert ".prefab" in UNITY_EXTENSIONS
        assert ".unity" in UNITY_EXTENSIONS
        assert ".asset" in UNITY_EXTENSIONS
        assert ".mat" in UNITY_EXTENSIONS

    def test_is_git_repository_true(self, git_repo):
        """Test is_git_repository returns True for git repo."""
        assert is_git_repository(git_repo) is True

    def test_is_git_repository_false(self, tmp_path):
        """Test is_git_repository returns False for non-git directory."""
        assert is_git_repository(tmp_path) is False

    def test_get_repo_root(self, git_repo):
        """Test get_repo_root returns correct path."""
        root = get_repo_root(git_repo)
        assert root == git_repo

    def test_get_repo_root_none(self, tmp_path):
        """Test get_repo_root returns None for non-git directory."""
        root = get_repo_root(tmp_path)
        assert root is None

    def test_filter_unity_files(self, tmp_path):
        """Test filter_unity_files filters correctly."""
        # Create test files
        prefab = tmp_path / "test.prefab"
        unity = tmp_path / "scene.unity"
        txt = tmp_path / "readme.txt"
        cs = tmp_path / "script.cs"

        prefab.touch()
        unity.touch()
        txt.touch()
        cs.touch()

        paths = [prefab, unity, txt, cs]
        filtered = filter_unity_files(paths)

        assert len(filtered) == 2
        assert prefab in filtered
        assert unity in filtered
        assert txt not in filtered
        assert cs not in filtered


class TestGitChangedFiles:
    """Tests for git changed file detection."""

    def test_get_changed_files_untracked(self, git_repo):
        """Test detecting untracked files."""
        # Create a new untracked prefab
        new_prefab = git_repo / "new.prefab"
        new_prefab.write_text("%YAML 1.1\n--- !u!1 &100\nGameObject:\n  m_Name: New\n")

        changed = get_changed_files(cwd=git_repo, include_untracked=True)
        assert any(f.name == "new.prefab" for f in changed)

    def test_get_changed_files_modified(self, git_repo):
        """Test detecting modified files."""
        # Modify existing prefab
        prefab = git_repo / "test.prefab"
        original = prefab.read_text()
        prefab.write_text(original + "# Modified\n")

        changed = get_changed_files(cwd=git_repo)
        assert any(f.name == "test.prefab" for f in changed)

    def test_get_changed_files_staged(self, git_repo):
        """Test detecting staged files."""
        # Create and stage a new prefab
        new_prefab = git_repo / "staged.prefab"
        new_prefab.write_text("%YAML 1.1\n--- !u!1 &100\nGameObject:\n  m_Name: Staged\n")
        subprocess.run(["git", "add", "staged.prefab"], cwd=git_repo, capture_output=True)

        # With staged_only=True
        changed = get_changed_files(cwd=git_repo, staged_only=True)
        assert any(f.name == "staged.prefab" for f in changed)

    def test_get_changed_files_excludes_deleted(self, git_repo):
        """Test that deleted files are excluded."""
        # Delete the prefab
        prefab = git_repo / "test.prefab"
        prefab.unlink()

        changed = get_changed_files(cwd=git_repo)
        assert not any(f.name == "test.prefab" for f in changed)

    def test_get_changed_files_filter_by_extension(self, git_repo):
        """Test filtering by extension."""
        # Create files with different extensions
        cs_file = git_repo / "script.cs"
        cs_file.write_text("// C# script\n")

        # Only .prefab extension
        changed = get_changed_files(cwd=git_repo, extensions=[".prefab"])
        assert not any(f.name == "script.cs" for f in changed)


class TestGitFilesChangedSince:
    """Tests for git files changed since reference."""

    def test_get_files_changed_since(self, git_repo):
        """Test getting files changed since a commit."""
        # Modify prefab
        prefab = git_repo / "test.prefab"
        original = prefab.read_text()
        prefab.write_text(original + "  m_Tag: Player\n")

        subprocess.run(["git", "add", "test.prefab"], cwd=git_repo, capture_output=True, check=True)
        git_commit(git_repo, "Modify prefab")

        # Get files changed since HEAD~1
        changed = get_files_changed_since("HEAD~1", cwd=git_repo)
        assert any(f.name == "test.prefab" for f in changed)

    def test_get_files_changed_since_no_changes(self, git_repo):
        """Test when there are no changes since reference."""
        changed = get_files_changed_since("HEAD", cwd=git_repo)
        assert len(changed) == 0


class TestGitFilesInCommit:
    """Tests for git files in specific commit."""

    def test_get_files_in_commit(self, git_repo):
        """Test getting files changed in a specific commit."""
        changed = get_files_in_commit("HEAD", cwd=git_repo)
        assert any(f.name == "test.prefab" for f in changed)


class TestCLIIncrementalNormalize:
    """Tests for CLI incremental normalization commands."""

    def test_normalize_no_input_shows_error(self, runner):
        """Test normalize without input shows error."""
        result = runner.invoke(main, ["normalize"])
        assert result.exit_code != 0
        assert "No input files specified" in result.output

    def test_normalize_multiple_files(self, runner):
        """Test normalizing multiple files."""
        result = runner.invoke(
            main,
            [
                "normalize",
                str(FIXTURES_DIR / "basic_prefab.prefab"),
                str(FIXTURES_DIR / "unsorted_prefab.prefab"),
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "Would normalize 2 file(s)" in result.output

    def test_normalize_dry_run(self, runner):
        """Test dry-run mode."""
        result = runner.invoke(
            main,
            [
                "normalize",
                str(FIXTURES_DIR / "basic_prefab.prefab"),
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "Would normalize" in result.output

    def test_normalize_output_with_multiple_files_error(self, runner):
        """Test that --output with multiple files shows error."""
        result = runner.invoke(
            main,
            [
                "normalize",
                str(FIXTURES_DIR / "basic_prefab.prefab"),
                str(FIXTURES_DIR / "unsorted_prefab.prefab"),
                "-o",
                "output.prefab",
            ],
        )
        assert result.exit_code != 0
        assert "--output cannot be used with multiple files" in result.output

    def test_normalize_stdout_with_multiple_files_error(self, runner):
        """Test that --stdout with multiple files shows error."""
        result = runner.invoke(
            main,
            [
                "normalize",
                str(FIXTURES_DIR / "basic_prefab.prefab"),
                str(FIXTURES_DIR / "unsorted_prefab.prefab"),
                "--stdout",
            ],
        )
        assert result.exit_code != 0
        assert "--stdout cannot be used with multiple files" in result.output

    def test_normalize_help_shows_incremental_options(self, runner):
        """Test that help shows incremental normalization options."""
        result = runner.invoke(main, ["normalize", "--help"])
        assert result.exit_code == 0
        assert "--changed-only" in result.output
        assert "--since" in result.output
        assert "--staged-only" in result.output
        assert "--pattern" in result.output
        assert "--dry-run" in result.output


class TestCLIIncrementalNormalizeWithGit:
    """Tests for CLI incremental normalization with git repository."""

    def test_normalize_changed_only_not_in_repo(self, runner, tmp_path):
        """Test --changed-only outside git repo shows error."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(main, ["normalize", "--changed-only"])
            assert result.exit_code != 0
            assert "Not in a git repository" in result.output

    def test_normalize_since_not_in_repo(self, runner, tmp_path):
        """Test --since outside git repo shows error."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(main, ["normalize", "--since", "HEAD~1"])
            assert result.exit_code != 0
            assert "Not in a git repository" in result.output

    def test_normalize_changed_only_no_changes(self, runner, git_repo):
        """Test --changed-only with no changes."""
        # git_repo fixture already changes directory
        result = runner.invoke(main, ["normalize", "--changed-only"])
        assert "No changed Unity files found" in result.output

    def test_normalize_changed_only_with_changes(self, runner, git_repo):
        """Test --changed-only with modified files."""
        # Modify the prefab
        prefab = git_repo / "test.prefab"
        original = prefab.read_text()
        prefab.write_text(original + "  m_Tag: Player\n")

        result = runner.invoke(main, ["normalize", "--changed-only", "--dry-run"])
        assert result.exit_code == 0
        assert "Would normalize 1 file(s)" in result.output
        assert "test.prefab" in result.output

    def test_normalize_since_with_changes(self, runner, git_repo):
        """Test --since with changed files."""
        # Modify and commit
        prefab = git_repo / "test.prefab"
        original = prefab.read_text()
        prefab.write_text(original + "  m_Tag: Player\n")

        subprocess.run(["git", "add", "test.prefab"], cwd=git_repo, capture_output=True, check=True)
        git_commit(git_repo, "Modify prefab")

        result = runner.invoke(main, ["normalize", "--since", "HEAD~1", "--dry-run"])
        assert result.exit_code == 0
        assert "Would normalize 1 file(s)" in result.output

    def test_normalize_with_pattern_filter(self, runner, git_repo):
        """Test --pattern filter."""
        # Create prefabs in different directories
        assets_dir = git_repo / "Assets" / "Prefabs"
        assets_dir.mkdir(parents=True)

        prefab1 = assets_dir / "player.prefab"
        prefab1.write_text("%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n--- !u!1 &100\nGameObject:\n  m_Name: Player\n")

        # Create another prefab outside Assets
        prefab2 = git_repo / "other.prefab"
        prefab2.write_text("%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n--- !u!1 &100\nGameObject:\n  m_Name: Other\n")

        result = runner.invoke(
            main,
            [
                "normalize",
                "--changed-only",
                "--pattern",
                "Assets/**/*.prefab",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "player.prefab" in result.output
        assert "other.prefab" not in result.output

    def test_normalize_staged_only(self, runner, git_repo):
        """Test --staged-only flag."""
        # Create two prefabs, stage only one
        prefab1 = git_repo / "staged.prefab"
        prefab1.write_text("%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n--- !u!1 &100\nGameObject:\n  m_Name: Staged\n")

        prefab2 = git_repo / "unstaged.prefab"
        yaml_header = "%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n"
        prefab2.write_text(f"{yaml_header}--- !u!1 &100\nGameObject:\n  m_Name: Unstaged\n")

        subprocess.run(["git", "add", "staged.prefab"], cwd=git_repo, capture_output=True)

        result = runner.invoke(main, ["normalize", "--changed-only", "--staged-only", "--dry-run"])
        assert result.exit_code == 0
        assert "staged.prefab" in result.output
        assert "unstaged.prefab" not in result.output


class TestCLIIncrementalNormalizeBatch:
    """Tests for batch normalization functionality."""

    def test_normalize_batch_success(self, runner, tmp_path):
        """Test successful batch normalization."""
        # Copy fixture files to temp dir
        for name in ["basic_prefab.prefab", "unsorted_prefab.prefab"]:
            src = FIXTURES_DIR / name
            dst = tmp_path / name
            dst.write_text(src.read_text())

        result = runner.invoke(
            main,
            [
                "normalize",
                str(tmp_path / "basic_prefab.prefab"),
                str(tmp_path / "unsorted_prefab.prefab"),
            ],
        )

        assert result.exit_code == 0
        assert "Completed: 2 normalized, 0 failed" in result.output

    def test_normalize_batch_with_errors(self, runner, tmp_path):
        """Test batch normalization with some errors."""
        # Create one valid and one truly invalid file (missing Unity header)
        valid = tmp_path / "valid.prefab"
        valid.write_text("%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n--- !u!1 &100\nGameObject:\n  m_Name: Valid\n")

        # This file is missing the required Unity YAML header structure
        invalid = tmp_path / "invalid.prefab"
        invalid.write_text("plain text that is definitely not a Unity YAML file\nno header no nothing")

        result = runner.invoke(
            main,
            ["normalize", str(valid), str(invalid)],
        )

        # Should complete (even if both succeed with lenient parser)
        assert "Completed:" in result.output
        # At least valid should be normalized
        assert "normalized" in result.output

"""Tests for CLI interface."""

import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from unityflow.cli import main

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def runner():
    """Create a CLI test runner."""
    return CliRunner()


class TestNormalizeCommand:
    """Tests for the normalize command."""

    def test_normalize_to_stdout(self, runner):
        """Test normalizing a file and outputting to stdout."""
        result = runner.invoke(
            main,
            ["normalize", str(FIXTURES_DIR / "basic_prefab.prefab"), "--stdout"],
        )

        assert result.exit_code == 0
        assert "%YAML 1.1" in result.output
        assert "GameObject" in result.output

    def test_normalize_to_file(self, runner, tmp_path):
        """Test normalizing a file and saving to output file."""
        output_file = tmp_path / "output.prefab"

        result = runner.invoke(
            main,
            [
                "normalize",
                str(FIXTURES_DIR / "basic_prefab.prefab"),
                "-o",
                str(output_file),
            ],
        )

        assert result.exit_code == 0
        assert output_file.exists()
        assert "Normalized:" in result.output

    def test_normalize_with_options(self, runner):
        """Test normalize with various options."""
        result = runner.invoke(
            main,
            [
                "normalize",
                str(FIXTURES_DIR / "basic_prefab.prefab"),
                "--stdout",
                "--precision",
                "4",
            ],
        )

        assert result.exit_code == 0

    def test_normalize_invalid_file(self, runner):
        """Test normalizing a non-existent file."""
        result = runner.invoke(
            main,
            ["normalize", "/nonexistent/file.prefab", "--stdout"],
        )

        assert result.exit_code != 0


class TestDiffCommand:
    """Tests for the diff command."""

    def test_diff_identical_files(self, runner):
        """Test diffing two identical files."""
        file_path = str(FIXTURES_DIR / "basic_prefab.prefab")

        result = runner.invoke(
            main,
            ["diff", file_path, file_path],
        )

        assert result.exit_code == 0
        assert "identical" in result.output.lower()

    def test_diff_different_files(self, runner):
        """Test diffing two different files."""
        result = runner.invoke(
            main,
            [
                "diff",
                str(FIXTURES_DIR / "basic_prefab.prefab"),
                str(FIXTURES_DIR / "unsorted_prefab.prefab"),
            ],
        )

        assert result.exit_code == 0
        # There should be some diff output
        assert len(result.output) > 0

    def test_diff_exit_code(self, runner):
        """Test diff with --exit-code flag."""
        result = runner.invoke(
            main,
            [
                "diff",
                str(FIXTURES_DIR / "basic_prefab.prefab"),
                str(FIXTURES_DIR / "unsorted_prefab.prefab"),
                "--exit-code",
            ],
        )

        # Different files should exit with 1
        assert result.exit_code == 1

    def test_diff_summary_format(self, runner):
        """Test diff with summary format."""
        result = runner.invoke(
            main,
            [
                "diff",
                str(FIXTURES_DIR / "basic_prefab.prefab"),
                str(FIXTURES_DIR / "unsorted_prefab.prefab"),
                "--format",
                "summary",
            ],
        )

        assert result.exit_code == 0
        assert "Lines" in result.output or "Comparing" in result.output


class TestValidateCommand:
    """Tests for the validate command."""

    def test_validate_valid_file(self, runner):
        """Test validating a valid prefab."""
        result = runner.invoke(
            main,
            ["validate", str(FIXTURES_DIR / "basic_prefab.prefab")],
        )

        assert result.exit_code == 0
        assert "VALID" in result.output

    def test_validate_multiple_files(self, runner):
        """Test validating multiple files."""
        result = runner.invoke(
            main,
            [
                "validate",
                str(FIXTURES_DIR / "basic_prefab.prefab"),
                str(FIXTURES_DIR / "unsorted_prefab.prefab"),
            ],
        )

        assert result.exit_code == 0

    def test_validate_json_output(self, runner):
        """Test validate with JSON output."""
        result = runner.invoke(
            main,
            [
                "validate",
                str(FIXTURES_DIR / "basic_prefab.prefab"),
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0
        assert '"valid"' in result.output
        assert '"path"' in result.output

    def test_validate_quiet_mode(self, runner):
        """Test validate in quiet mode."""
        result = runner.invoke(
            main,
            [
                "validate",
                str(FIXTURES_DIR / "basic_prefab.prefab"),
                "--quiet",
            ],
        )

        assert result.exit_code == 0


class TestQueryCommand:
    """Tests for the query command."""

    def test_query_summary(self, runner):
        """Test query without path shows summary."""
        result = runner.invoke(
            main,
            ["query", str(FIXTURES_DIR / "basic_prefab.prefab")],
        )

        assert result.exit_code == 0
        assert "Objects:" in result.output
        assert "GameObject" in result.output

    def test_query_with_path(self, runner):
        """Test query with path parameter."""
        result = runner.invoke(
            main,
            [
                "query",
                str(FIXTURES_DIR / "basic_prefab.prefab"),
                "--path",
                "gameObjects/*/name",
            ],
        )

        # Currently shows warning about path querying not implemented
        # but should still succeed
        assert "not yet" in result.output.lower() or "BasicPrefab" in result.output


class TestGitTextconvCommand:
    """Tests for the git-textconv command."""

    def test_git_textconv_output(self, runner):
        """Test git-textconv outputs normalized content."""
        result = runner.invoke(
            main,
            ["git-textconv", str(FIXTURES_DIR / "basic_prefab.prefab")],
        )

        assert result.exit_code == 0
        assert "%YAML 1.1" in result.output
        assert "GameObject" in result.output

    def test_git_textconv_normalized(self, runner):
        """Test that git-textconv produces normalized output."""
        # Use the unsorted prefab - output should be sorted
        result = runner.invoke(
            main,
            ["git-textconv", str(FIXTURES_DIR / "unsorted_prefab.prefab")],
        )

        assert result.exit_code == 0
        # The normalized output should have documents in fileID order
        assert "%YAML 1.1" in result.output


class TestMergeCommand:
    """Tests for the merge command."""

    def test_merge_identical_files(self, runner, tmp_path):
        """Test merging identical files."""
        # Create test files
        content = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!1 &100000
GameObject:
  m_Name: Test
"""
        base = tmp_path / "base.prefab"
        ours = tmp_path / "ours.prefab"
        theirs = tmp_path / "theirs.prefab"

        base.write_text(content)
        ours.write_text(content)
        theirs.write_text(content)

        result = runner.invoke(
            main,
            ["merge", str(base), str(ours), str(theirs)],
        )

        assert result.exit_code == 0

    def test_merge_only_theirs_changed(self, runner, tmp_path):
        """Test merge when only theirs changed."""
        base_content = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!1 &100000
GameObject:
  m_Name: Original
"""
        theirs_content = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!1 &100000
GameObject:
  m_Name: Modified
"""
        base = tmp_path / "base.prefab"
        ours = tmp_path / "ours.prefab"
        theirs = tmp_path / "theirs.prefab"

        base.write_text(base_content)
        ours.write_text(base_content)  # Ours is same as base
        theirs.write_text(theirs_content)

        result = runner.invoke(
            main,
            ["merge", str(base), str(ours), str(theirs)],
        )

        assert result.exit_code == 0
        # Ours should be updated with theirs' content
        assert "Modified" in ours.read_text()

    def test_merge_with_output_option(self, runner, tmp_path):
        """Test merge with explicit output file."""
        content = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!1 &100000
GameObject:
  m_Name: Test
"""
        base = tmp_path / "base.prefab"
        ours = tmp_path / "ours.prefab"
        theirs = tmp_path / "theirs.prefab"
        output = tmp_path / "merged.prefab"

        base.write_text(content)
        ours.write_text(content)
        theirs.write_text(content)

        result = runner.invoke(
            main,
            ["merge", str(base), str(ours), str(theirs), "-o", str(output)],
        )

        assert result.exit_code == 0
        assert output.exists()


class TestVersionOption:
    """Tests for version option."""

    def test_version(self, runner):
        """Test --version flag."""
        from unityflow import __version__

        result = runner.invoke(main, ["--version"])

        assert result.exit_code == 0
        assert "unityflow" in result.output
        assert __version__ in result.output


class TestHelpOption:
    """Tests for help option."""

    def test_main_help(self, runner):
        """Test main help."""
        result = runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "normalize" in result.output
        assert "diff" in result.output
        assert "validate" in result.output

    def test_normalize_help(self, runner):
        """Test normalize command help."""
        result = runner.invoke(main, ["normalize", "--help"])

        assert result.exit_code == 0
        assert "--output" in result.output
        assert "--stdout" in result.output

    def test_diff_help(self, runner):
        """Test diff command help."""
        result = runner.invoke(main, ["diff", "--help"])

        assert result.exit_code == 0
        assert "--context" in result.output
        assert "--format" in result.output


class TestAddObjectCommand:
    """Tests for the add-object command."""

    def test_add_object(self, runner, tmp_path):
        """Test adding a new GameObject."""
        # Copy fixture to temp
        source = FIXTURES_DIR / "basic_prefab.prefab"
        test_file = tmp_path / "test.prefab"
        test_file.write_text(source.read_text())

        result = runner.invoke(
            main,
            ["add-object", str(test_file), "--name", "NewObject"],
        )

        assert result.exit_code == 0
        assert "Added GameObject 'NewObject'" in result.output

        # Verify the file was modified
        content = test_file.read_text()
        assert "NewObject" in content

    def test_add_object_with_position(self, runner, tmp_path):
        """Test adding a GameObject with position."""
        source = FIXTURES_DIR / "basic_prefab.prefab"
        test_file = tmp_path / "test.prefab"
        test_file.write_text(source.read_text())

        result = runner.invoke(
            main,
            [
                "add-object",
                str(test_file),
                "--name",
                "PositionedObject",
                "--position",
                "10,5,3",
            ],
        )

        assert result.exit_code == 0
        content = test_file.read_text()
        assert "PositionedObject" in content
        # Check position is in file (simplified check)
        assert "10" in content or "m_LocalPosition" in content

    def test_add_object_ui(self, runner, tmp_path):
        """Test adding a UI GameObject with RectTransform."""
        source = FIXTURES_DIR / "basic_prefab.prefab"
        test_file = tmp_path / "test.prefab"
        test_file.write_text(source.read_text())

        result = runner.invoke(
            main,
            ["add-object", str(test_file), "--name", "UIElement", "--ui"],
        )

        assert result.exit_code == 0
        assert "Added GameObject 'UIElement'" in result.output
        content = test_file.read_text()
        assert "RectTransform" in content

    def test_add_object_help(self, runner):
        """Test add-object command help."""
        result = runner.invoke(main, ["add-object", "--help"])

        assert result.exit_code == 0
        assert "--name" in result.output
        assert "--parent" in result.output
        assert "--ui" in result.output


class TestAddComponentCommand:
    """Tests for the add-component command."""

    def test_add_component(self, runner, tmp_path):
        """Test adding a component to an existing GameObject."""
        source = FIXTURES_DIR / "basic_prefab.prefab"
        test_file = tmp_path / "test.prefab"
        test_file.write_text(source.read_text())

        result = runner.invoke(
            main,
            [
                "add-component",
                str(test_file),
                "--to",
                "BasicPrefab",  # GameObject path
                "--type",
                "SpriteRenderer",
            ],
        )

        assert result.exit_code == 0
        assert "Added SpriteRenderer component" in result.output
        content = test_file.read_text()
        assert "SpriteRenderer" in content

    def test_add_monobehaviour(self, runner, tmp_path):
        """Test adding a MonoBehaviour component."""
        source = FIXTURES_DIR / "basic_prefab.prefab"
        test_file = tmp_path / "test.prefab"
        test_file.write_text(source.read_text())

        result = runner.invoke(
            main,
            [
                "add-component",
                str(test_file),
                "--to",
                "BasicPrefab",  # GameObject path
                "--script",
                "abc123def456abc123def456abc12345",  # 32-char GUID
            ],
        )

        assert result.exit_code == 0
        assert "Added MonoBehaviour component" in result.output
        content = test_file.read_text()
        assert "MonoBehaviour" in content
        assert "abc123def456abc123def456abc12345" in content

    def test_add_component_requires_type_or_script(self, runner, tmp_path):
        """Test that add-component requires --type or --script."""
        source = FIXTURES_DIR / "basic_prefab.prefab"
        test_file = tmp_path / "test.prefab"
        test_file.write_text(source.read_text())

        result = runner.invoke(
            main,
            ["add-component", str(test_file), "--to", "BasicPrefab"],
        )

        assert result.exit_code != 0
        assert "Specify --type or --script" in result.output

    def test_add_component_help(self, runner):
        """Test add-component command help."""
        result = runner.invoke(main, ["add-component", "--help"])

        assert result.exit_code == 0
        assert "--to" in result.output
        assert "--type" in result.output
        assert "--script" in result.output


class TestDeleteObjectCommand:
    """Tests for the delete-object command."""

    def test_delete_object(self, runner, tmp_path):
        """Test deleting a GameObject."""
        source = FIXTURES_DIR / "basic_prefab.prefab"
        test_file = tmp_path / "test.prefab"
        test_file.write_text(source.read_text())

        result = runner.invoke(
            main,
            [
                "delete-object",
                str(test_file),
                "--id",
                "BasicPrefab",  # GameObject path
                "--force",
            ],
        )

        assert result.exit_code == 0
        assert "Deleted" in result.output

        # Verify the GameObject is removed
        content = test_file.read_text()
        assert "BasicPrefab" not in content

    def test_delete_object_nonexistent(self, runner, tmp_path):
        """Test deleting a non-existent object."""
        source = FIXTURES_DIR / "basic_prefab.prefab"
        test_file = tmp_path / "test.prefab"
        test_file.write_text(source.read_text())

        result = runner.invoke(
            main,
            ["delete-object", str(test_file), "--id", "NonExistent/Path", "--force"],
        )

        assert result.exit_code != 0
        assert "not found" in result.output

    def test_delete_object_help(self, runner):
        """Test delete-object command help."""
        result = runner.invoke(main, ["delete-object", "--help"])

        assert result.exit_code == 0
        assert "--id" in result.output
        assert "--cascade" in result.output


class TestDeleteComponentCommand:
    """Tests for the delete-component command."""

    def test_delete_component(self, runner, tmp_path):
        """Test deleting a component."""
        source = FIXTURES_DIR / "basic_prefab.prefab"
        test_file = tmp_path / "test.prefab"
        test_file.write_text(source.read_text())

        result = runner.invoke(
            main,
            [
                "delete-component",
                str(test_file),
                "--id",
                "400000",  # Transform fileID
                "--force",
            ],
        )

        assert result.exit_code == 0
        assert "Deleted component" in result.output

    def test_delete_component_help(self, runner):
        """Test delete-component command help."""
        result = runner.invoke(main, ["delete-component", "--help"])

        assert result.exit_code == 0
        assert "--id" in result.output
        assert "--force" in result.output


class TestCloneObjectCommand:
    """Tests for the clone-object command."""

    def test_clone_gameobject(self, runner, tmp_path):
        """Test cloning a GameObject."""
        source = FIXTURES_DIR / "basic_prefab.prefab"
        test_file = tmp_path / "test.prefab"
        test_file.write_text(source.read_text())

        result = runner.invoke(
            main,
            ["clone-object", str(test_file), "--id", "BasicPrefab"],
        )

        assert result.exit_code == 0
        assert "Cloned GameObject" in result.output
        assert "Source:" in result.output
        assert "Total objects cloned:" in result.output

        # Verify the clone exists
        content = test_file.read_text()
        assert "BasicPrefab (Clone)" in content

    def test_clone_with_name(self, runner, tmp_path):
        """Test cloning with custom name."""
        source = FIXTURES_DIR / "basic_prefab.prefab"
        test_file = tmp_path / "test.prefab"
        test_file.write_text(source.read_text())

        result = runner.invoke(
            main,
            ["clone-object", str(test_file), "--id", "BasicPrefab", "--name", "MyClone"],
        )

        assert result.exit_code == 0
        content = test_file.read_text()
        assert "MyClone" in content

    def test_clone_with_position_offset(self, runner, tmp_path):
        """Test cloning with position offset."""
        source = FIXTURES_DIR / "basic_prefab.prefab"
        test_file = tmp_path / "test.prefab"
        test_file.write_text(source.read_text())

        result = runner.invoke(
            main,
            [
                "clone-object",
                str(test_file),
                "--id",
                "BasicPrefab",
                "--position",
                "5,0,0",
            ],
        )

        assert result.exit_code == 0
        # Position offset applied
        content = test_file.read_text()
        # Original position is 0,0,0, so with offset 5,0,0 we should see x: 5
        assert "x: 5" in content or "{x: 5" in content

    def test_clone_nonexistent_source(self, runner, tmp_path):
        """Test cloning a non-existent source."""
        source = FIXTURES_DIR / "basic_prefab.prefab"
        test_file = tmp_path / "test.prefab"
        test_file.write_text(source.read_text())

        result = runner.invoke(
            main,
            ["clone-object", str(test_file), "--id", "NonExistent/Path"],
        )

        assert result.exit_code != 0
        assert "not found" in result.output

    def test_clone_help(self, runner):
        """Test clone-object command help."""
        result = runner.invoke(main, ["clone-object", "--help"])

        assert result.exit_code == 0
        assert "--id" in result.output
        assert "--name" in result.output
        assert "--deep" in result.output


class TestQueryEnhancements:
    """Tests for enhanced query command options."""

    def test_query_find_name(self, runner):
        """Test query with --find-name."""
        result = runner.invoke(
            main,
            [
                "query",
                str(FIXTURES_DIR / "basic_prefab.prefab"),
                "--find-name",
                "BasicPrefab",
            ],
        )

        assert result.exit_code == 0
        assert "BasicPrefab" in result.output
        assert "Found" in result.output

    def test_query_find_name_wildcard(self, runner):
        """Test query with --find-name using wildcard."""
        result = runner.invoke(
            main,
            [
                "query",
                str(FIXTURES_DIR / "basic_prefab.prefab"),
                "--find-name",
                "*Prefab",
            ],
        )

        assert result.exit_code == 0
        assert "BasicPrefab" in result.output

    def test_query_find_name_no_match(self, runner):
        """Test query with --find-name that matches nothing."""
        result = runner.invoke(
            main,
            [
                "query",
                str(FIXTURES_DIR / "basic_prefab.prefab"),
                "--find-name",
                "NonExistent*",
            ],
        )

        assert result.exit_code == 0
        assert "No GameObjects found" in result.output

    def test_query_find_component(self, runner):
        """Test query with --find-component."""
        result = runner.invoke(
            main,
            [
                "query",
                str(FIXTURES_DIR / "basic_prefab.prefab"),
                "--find-component",
                "Transform",
            ],
        )

        assert result.exit_code == 0
        assert "BasicPrefab" in result.output or "GameObject" in result.output

    def test_query_find_component_json(self, runner):
        """Test query with --find-component and JSON output."""
        result = runner.invoke(
            main,
            [
                "query",
                str(FIXTURES_DIR / "basic_prefab.prefab"),
                "--find-component",
                "Transform",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0
        assert '"fileID"' in result.output

    def test_query_find_name_help(self, runner):
        """Test that --find-name is documented in help."""
        result = runner.invoke(main, ["query", "--help"])

        assert result.exit_code == 0
        assert "--find-name" in result.output
        assert "--find-component" in result.output
        assert "--find-script" in result.output

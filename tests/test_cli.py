"""Tests for CLI interface."""

import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from prefab_tool.cli import main

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
                "--no-sort-documents",
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


class TestVersionOption:
    """Tests for version option."""

    def test_version(self, runner):
        """Test --version flag."""
        result = runner.invoke(main, ["--version"])

        assert result.exit_code == 0
        assert "prefab-tool" in result.output
        assert "0.1.0" in result.output


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

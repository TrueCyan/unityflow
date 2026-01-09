"""Tests for CLI interface."""

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

    def test_diff_semantic_output(self, runner):
        """Test diff with semantic output format."""
        result = runner.invoke(
            main,
            [
                "diff",
                str(FIXTURES_DIR / "basic_prefab.prefab"),
                str(FIXTURES_DIR / "unsorted_prefab.prefab"),
            ],
        )

        # Semantic diff shows summary line
        assert result.exit_code == 0
        assert "Summary:" in result.output or "Files are identical" in result.output


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
        assert "--exit-code" in result.output
        assert "semantic" in result.output.lower()


class TestSetCommand:
    """Tests for the set command."""

    def test_set_recttransform_batch(self, runner, tmp_path):
        """Test setting RectTransform properties with batch mode.

        This verifies the fix for the bug where batch mode with a path ending
        in a component type (like RectTransform) was incorrectly storing values
        inline in the GameObject instead of the actual component document.
        """
        import shutil

        from unityflow.parser import UnityYAMLDocument

        # Copy fixture to temp location
        test_file = tmp_path / "BossSceneUI.prefab"
        shutil.copy(FIXTURES_DIR / "BossSceneUI.prefab", test_file)

        # Run set command with batch mode on RectTransform
        # Use Canvas_LeaderboardUI which is a direct child of BossSceneUI and has RectTransform
        result = runner.invoke(
            main,
            [
                "set",
                str(test_file),
                "--path",
                "BossSceneUI/Canvas_LeaderboardUI/RectTransform",
                "--batch",
                '{"m_AnchorMin": {"x": 0.1, "y": 0.2}, "m_SizeDelta": {"x": 50, "y": 100}}',
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "Set" in result.output

        # Verify values were set in the actual RectTransform component
        doc = UnityYAMLDocument.load(test_file)

        # Find the Canvas_LeaderboardUI GameObject
        target_go = None
        for go in doc.get_game_objects():
            content = go.get_content()
            if content and content.get("m_Name") == "Canvas_LeaderboardUI":
                target_go = go
                break

        assert target_go is not None, "Canvas_LeaderboardUI GameObject not found"

        # Get the RectTransform component
        go_content = target_go.get_content()
        rect_transform = None
        for comp_ref in go_content.get("m_Component", []):
            comp_id = comp_ref.get("component", {}).get("fileID", 0)
            comp = doc.get_by_file_id(comp_id)
            if comp and comp.class_name == "RectTransform":
                rect_transform = comp
                break

        assert rect_transform is not None, "RectTransform component not found"

        # Verify the values were set in the actual component
        rt_content = rect_transform.get_content()
        assert rt_content["m_AnchorMin"]["x"] == 0.1
        assert rt_content["m_AnchorMin"]["y"] == 0.2
        assert rt_content["m_SizeDelta"]["x"] == 50
        assert rt_content["m_SizeDelta"]["y"] == 100

        # Verify values are NOT stored inline in the GameObject
        assert "RectTransform" not in go_content or not isinstance(
            go_content.get("RectTransform"), dict
        ), "Values should not be stored inline in the GameObject"

    def test_set_component_property(self, runner, tmp_path):
        """Test setting a single property on a component."""
        import shutil

        test_file = tmp_path / "basic_prefab.prefab"
        shutil.copy(FIXTURES_DIR / "basic_prefab.prefab", test_file)

        result = runner.invoke(
            main,
            [
                "set",
                str(test_file),
                "--path",
                "BasicPrefab/Transform/m_LocalPosition",
                "--value",
                '{"x": 10, "y": 20, "z": 30}',
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "Set" in result.output

    def test_set_path_ending_with_transform(self, runner, tmp_path):
        """Test batch mode with path ending in Transform component."""
        import shutil

        from unityflow.parser import UnityYAMLDocument

        test_file = tmp_path / "basic_prefab.prefab"
        shutil.copy(FIXTURES_DIR / "basic_prefab.prefab", test_file)

        result = runner.invoke(
            main,
            [
                "set",
                str(test_file),
                "--path",
                "BasicPrefab/Transform",
                "--batch",
                '{"m_LocalPosition": {"x": 5, "y": 10, "z": 15}}',
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify value was set in the Transform component
        doc = UnityYAMLDocument.load(test_file)

        # Find the BasicPrefab GameObject
        go = None
        for game_obj in doc.get_game_objects():
            content = game_obj.get_content()
            if content and content.get("m_Name") == "BasicPrefab":
                go = game_obj
                break

        assert go is not None

        # Find the Transform component
        go_content = go.get_content()
        transform = None
        for comp_ref in go_content.get("m_Component", []):
            comp_id = comp_ref.get("component", {}).get("fileID", 0)
            comp = doc.get_by_file_id(comp_id)
            if comp and comp.class_name == "Transform":
                transform = comp
                break

        assert transform is not None
        t_content = transform.get_content()
        assert t_content["m_LocalPosition"]["x"] == 5
        assert t_content["m_LocalPosition"]["y"] == 10
        assert t_content["m_LocalPosition"]["z"] == 15

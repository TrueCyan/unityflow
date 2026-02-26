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


class TestCreateCommand:

    def test_create_basic_prefab(self, runner, tmp_path):
        output_file = tmp_path / "NewPrefab.prefab"

        result = runner.invoke(
            main,
            ["create", str(output_file)],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert output_file.exists()
        assert "Created" in result.output
        assert "NewPrefab" in result.output

        from unityflow.parser import UnityYAMLDocument

        doc = UnityYAMLDocument.load(output_file)
        assert len(doc.get_game_objects()) == 1
        assert len(doc.get_transforms()) == 1

        go = doc.get_game_objects()[0]
        go_content = go.get_content()
        assert go_content["m_Name"] == "NewPrefab"

    def test_create_with_custom_name(self, runner, tmp_path):
        output_file = tmp_path / "Enemy.prefab"

        result = runner.invoke(
            main,
            ["create", str(output_file), "--name", "EnemyRoot"],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        from unityflow.parser import UnityYAMLDocument

        doc = UnityYAMLDocument.load(output_file)
        go = doc.get_game_objects()[0]
        assert go.get_content()["m_Name"] == "EnemyRoot"

    def test_create_with_rect_transform(self, runner, tmp_path):
        output_file = tmp_path / "MyUI.prefab"

        result = runner.invoke(
            main,
            ["create", str(output_file), "--name", "MyRoot", "--type", "rect-transform"],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        from unityflow.parser import UnityYAMLDocument

        doc = UnityYAMLDocument.load(output_file)
        assert len(doc.get_rect_transforms()) == 1
        assert len(doc.get_transforms()) == 0

        rt = doc.get_rect_transforms()[0]
        rt_content = rt.get_content()
        assert "m_AnchorMin" in rt_content
        assert "m_SizeDelta" in rt_content

    def test_create_file_already_exists(self, runner, tmp_path):
        output_file = tmp_path / "Existing.prefab"
        output_file.write_text("dummy")

        result = runner.invoke(
            main,
            ["create", str(output_file)],
        )

        assert result.exit_code != 0
        assert "already exists" in result.output

    def test_create_valid_yaml_roundtrip(self, runner, tmp_path):
        output_file = tmp_path / "Roundtrip.prefab"

        result = runner.invoke(
            main,
            ["create", str(output_file), "--name", "Root"],
        )
        assert result.exit_code == 0

        from unityflow.parser import UnityYAMLDocument

        doc = UnityYAMLDocument.load(output_file)
        content = output_file.read_text(encoding="utf-8")
        assert content.startswith("%YAML 1.1")
        assert "--- !u!1 &" in content
        assert "--- !u!4 &" in content

        go = doc.get_game_objects()[0]
        go_content = go.get_content()
        transform_id = go_content["m_Component"][0]["component"]["fileID"]
        transform = doc.get_by_file_id(transform_id)
        assert transform is not None
        assert transform.get_content()["m_GameObject"]["fileID"] == go.file_id


class TestSetAddComponent:

    def test_add_component(self, runner, tmp_path):
        import shutil

        test_file = tmp_path / "basic.prefab"
        shutil.copy(FIXTURES_DIR / "basic_prefab.prefab", test_file)

        result = runner.invoke(
            main,
            [
                "set",
                str(test_file),
                "--path",
                "BasicPrefab",
                "--add-component",
                "CanvasRenderer",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "Added CanvasRenderer to BasicPrefab" in result.output

        from unityflow.parser import UnityYAMLDocument

        doc = UnityYAMLDocument.load(test_file)
        go = doc.get_game_objects()[0]
        go_content = go.get_content()
        assert len(go_content["m_Component"]) == 2

    def test_add_component_duplicate_transform_blocked(self, runner, tmp_path):
        import shutil

        test_file = tmp_path / "basic.prefab"
        shutil.copy(FIXTURES_DIR / "basic_prefab.prefab", test_file)

        result = runner.invoke(
            main,
            [
                "set",
                str(test_file),
                "--path",
                "BasicPrefab",
                "--add-component",
                "Transform",
            ],
        )

        assert result.exit_code != 0
        assert "already exists" in result.output

    def test_add_component_duplicate_allowed(self, runner, tmp_path):
        import shutil

        test_file = tmp_path / "basic.prefab"
        shutil.copy(FIXTURES_DIR / "basic_prefab.prefab", test_file)

        runner.invoke(
            main,
            ["set", str(test_file), "--path", "BasicPrefab", "--add-component", "CanvasRenderer"],
        )
        result = runner.invoke(
            main,
            ["set", str(test_file), "--path", "BasicPrefab", "--add-component", "CanvasRenderer"],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        from unityflow.parser import UnityYAMLDocument

        doc = UnityYAMLDocument.load(test_file)
        go = doc.get_game_objects()[0]
        go_content = go.get_content()
        assert len(go_content["m_Component"]) == 3

    def test_remove_component(self, runner, tmp_path):
        import shutil

        test_file = tmp_path / "basic.prefab"
        shutil.copy(FIXTURES_DIR / "basic_prefab.prefab", test_file)

        runner.invoke(
            main,
            [
                "set",
                str(test_file),
                "--path",
                "BasicPrefab",
                "--add-component",
                "CanvasRenderer",
            ],
        )

        result = runner.invoke(
            main,
            [
                "set",
                str(test_file),
                "--path",
                "BasicPrefab",
                "--remove-component",
                "CanvasRenderer",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "Removed CanvasRenderer from BasicPrefab" in result.output

        from unityflow.parser import UnityYAMLDocument

        doc = UnityYAMLDocument.load(test_file)
        go = doc.get_game_objects()[0]
        go_content = go.get_content()
        assert len(go_content["m_Component"]) == 1

    def test_remove_nonexistent_component(self, runner, tmp_path):
        import shutil

        test_file = tmp_path / "basic.prefab"
        shutil.copy(FIXTURES_DIR / "basic_prefab.prefab", test_file)

        result = runner.invoke(
            main,
            [
                "set",
                str(test_file),
                "--path",
                "BasicPrefab",
                "--remove-component",
                "Button",
            ],
        )

        assert result.exit_code != 0
        assert "not found" in result.output

    def test_deprecated_create_still_works(self, runner, tmp_path):
        import shutil

        test_file = tmp_path / "basic.prefab"
        shutil.copy(FIXTURES_DIR / "basic_prefab.prefab", test_file)

        result = runner.invoke(
            main,
            [
                "set",
                str(test_file),
                "--path",
                "BasicPrefab/CanvasRenderer",
                "--create",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "Added CanvasRenderer to BasicPrefab" in result.output

    def test_deprecated_remove_still_works(self, runner, tmp_path):
        import shutil

        test_file = tmp_path / "basic.prefab"
        shutil.copy(FIXTURES_DIR / "basic_prefab.prefab", test_file)

        runner.invoke(
            main,
            [
                "set",
                str(test_file),
                "--path",
                "BasicPrefab/CanvasRenderer",
                "--create",
            ],
        )

        result = runner.invoke(
            main,
            [
                "set",
                str(test_file),
                "--path",
                "BasicPrefab/CanvasRenderer",
                "--remove",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "Removed CanvasRenderer from BasicPrefab" in result.output

    def test_add_package_component_via_guid_fallback(self, runner, tmp_path):
        import shutil

        test_file = tmp_path / "basic.prefab"
        shutil.copy(FIXTURES_DIR / "basic_prefab.prefab", test_file)

        result = runner.invoke(
            main,
            [
                "set",
                str(test_file),
                "--path",
                "BasicPrefab",
                "--add-component",
                "GraphicRaycaster",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "Added GraphicRaycaster to BasicPrefab" in result.output

        content = test_file.read_text()
        assert "dc42784cf147c0c48a680349fa168899" in content

    def test_add_package_component_via_meta(self, runner, tmp_path):
        import shutil

        project_root = tmp_path / "project"
        (project_root / "Assets").mkdir(parents=True)
        (project_root / "ProjectSettings").mkdir()

        pkg_dir = project_root / "Library" / "PackageCache" / "com.unity.ugui" / "Runtime" / "UI"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "CustomPkgComp.cs").write_text("public class CustomPkgComp : MonoBehaviour {}")
        (pkg_dir / "CustomPkgComp.cs.meta").write_text("fileFormatVersion: 2\nguid: aabbccdd11223344aabbccdd11223344\n")

        prefab_dir = project_root / "Assets"
        test_file = prefab_dir / "basic.prefab"
        shutil.copy(FIXTURES_DIR / "basic_prefab.prefab", test_file)

        result = runner.invoke(
            main,
            [
                "set",
                str(test_file),
                "--path",
                "BasicPrefab",
                "--add-component",
                "CustomPkgComp",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "Added CustomPkgComp to BasicPrefab" in result.output

        content = test_file.read_text()
        assert "aabbccdd11223344aabbccdd11223344" in content

    def test_add_component_duplicate_scripts_warns(self, runner, tmp_path):
        import shutil

        project_root = tmp_path / "project"
        (project_root / "Assets" / "Scripts").mkdir(parents=True)
        (project_root / "ProjectSettings").mkdir()

        assets_dir = project_root / "Assets" / "Scripts"
        (assets_dir / "DupComp.cs").write_text("public class DupComp : MonoBehaviour {}")
        (assets_dir / "DupComp.cs.meta").write_text("fileFormatVersion: 2\nguid: aaaa000011112222aaaa000011112222\n")

        pkg_dir = project_root / "Library" / "PackageCache" / "com.example" / "Runtime"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "DupComp.cs").write_text("public class DupComp : MonoBehaviour {}")
        (pkg_dir / "DupComp.cs.meta").write_text("fileFormatVersion: 2\nguid: bbbb000011112222bbbb000011112222\n")

        prefab_dir = project_root / "Assets"
        test_file = prefab_dir / "basic.prefab"
        shutil.copy(FIXTURES_DIR / "basic_prefab.prefab", test_file)

        result = runner.invoke(
            main,
            [
                "set",
                str(test_file),
                "--path",
                "BasicPrefab",
                "--add-component",
                "DupComp",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "Warning: Multiple scripts" in result.output

        content = test_file.read_text()
        assert "aaaa000011112222aaaa000011112222" in content

    def test_add_component_not_found_shows_search_paths(self, runner, tmp_path):
        import shutil

        project_root = tmp_path / "project"
        (project_root / "Assets").mkdir(parents=True)
        (project_root / "ProjectSettings").mkdir()

        test_file = project_root / "Assets" / "basic.prefab"
        shutil.copy(FIXTURES_DIR / "basic_prefab.prefab", test_file)

        result = runner.invoke(
            main,
            [
                "set",
                str(test_file),
                "--path",
                "BasicPrefab",
                "--add-component",
                "NonExistentComponent",
            ],
        )

        assert result.exit_code != 0
        assert "not found" in result.output
        assert "Library/PackageCache/" in result.output


class TestSetAddRemoveObject:

    def test_add_object(self, runner, tmp_path):
        import shutil

        test_file = tmp_path / "basic.prefab"
        shutil.copy(FIXTURES_DIR / "basic_prefab.prefab", test_file)

        result = runner.invoke(
            main,
            [
                "set",
                str(test_file),
                "--path",
                "BasicPrefab",
                "--add-object",
                "Child",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "Added 'Child' under 'BasicPrefab'" in result.output

        from unityflow.parser import UnityYAMLDocument

        doc = UnityYAMLDocument.load(test_file)
        assert len(doc.get_game_objects()) == 2

        child_go = None
        for go in doc.get_game_objects():
            if go.get_content()["m_Name"] == "Child":
                child_go = go
                break
        assert child_go is not None

        child_transform_id = child_go.get_content()["m_Component"][0]["component"]["fileID"]
        child_transform = doc.get_by_file_id(child_transform_id)
        assert child_transform is not None
        assert child_transform.class_id == 4

    def test_add_object_with_rect_transform(self, runner, tmp_path):
        import shutil

        test_file = tmp_path / "basic.prefab"
        shutil.copy(FIXTURES_DIR / "basic_prefab.prefab", test_file)

        result = runner.invoke(
            main,
            [
                "set",
                str(test_file),
                "--path",
                "BasicPrefab",
                "--add-object",
                "UIChild",
                "--type",
                "rect-transform",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        from unityflow.parser import UnityYAMLDocument

        doc = UnityYAMLDocument.load(test_file)
        assert len(doc.get_rect_transforms()) == 1

        child_go = None
        for go in doc.get_game_objects():
            if go.get_content()["m_Name"] == "UIChild":
                child_go = go
                break
        assert child_go is not None

    def test_add_object_parent_child_link(self, runner, tmp_path):
        import shutil

        test_file = tmp_path / "basic.prefab"
        shutil.copy(FIXTURES_DIR / "basic_prefab.prefab", test_file)

        result = runner.invoke(
            main,
            [
                "set",
                str(test_file),
                "--path",
                "BasicPrefab",
                "--add-object",
                "MyChild",
            ],
        )
        assert result.exit_code == 0

        from unityflow.parser import UnityYAMLDocument

        doc = UnityYAMLDocument.load(test_file)

        parent_go = None
        child_go = None
        for go in doc.get_game_objects():
            name = go.get_content()["m_Name"]
            if name == "BasicPrefab":
                parent_go = go
            elif name == "MyChild":
                child_go = go

        assert parent_go is not None
        assert child_go is not None

        parent_transform_id = parent_go.get_content()["m_Component"][0]["component"]["fileID"]
        parent_transform = doc.get_by_file_id(parent_transform_id)
        parent_t_content = parent_transform.get_content()
        child_transform_id = child_go.get_content()["m_Component"][0]["component"]["fileID"]

        child_refs = [c["fileID"] for c in parent_t_content["m_Children"]]
        assert child_transform_id in child_refs

        child_transform = doc.get_by_file_id(child_transform_id)
        child_t_content = child_transform.get_content()
        assert child_t_content["m_Father"]["fileID"] == parent_transform_id

    def test_remove_object(self, runner, tmp_path):
        import shutil

        test_file = tmp_path / "basic.prefab"
        shutil.copy(FIXTURES_DIR / "basic_prefab.prefab", test_file)

        runner.invoke(
            main,
            [
                "set",
                str(test_file),
                "--path",
                "BasicPrefab",
                "--add-object",
                "ToRemove",
            ],
        )

        from unityflow.parser import UnityYAMLDocument

        doc_before = UnityYAMLDocument.load(test_file)
        assert len(doc_before.get_game_objects()) == 2

        result = runner.invoke(
            main,
            [
                "set",
                str(test_file),
                "--path",
                "BasicPrefab",
                "--remove-object",
                "ToRemove",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "Removed 'ToRemove' from 'BasicPrefab'" in result.output

        doc_after = UnityYAMLDocument.load(test_file)
        assert len(doc_after.get_game_objects()) == 1
        assert doc_after.get_game_objects()[0].get_content()["m_Name"] == "BasicPrefab"

        parent_go = doc_after.get_game_objects()[0]
        parent_transform_id = parent_go.get_content()["m_Component"][0]["component"]["fileID"]
        parent_transform = doc_after.get_by_file_id(parent_transform_id)
        assert parent_transform.get_content()["m_Children"] == []

    def test_remove_nonexistent_object(self, runner, tmp_path):
        import shutil

        test_file = tmp_path / "basic.prefab"
        shutil.copy(FIXTURES_DIR / "basic_prefab.prefab", test_file)

        result = runner.invoke(
            main,
            [
                "set",
                str(test_file),
                "--path",
                "BasicPrefab",
                "--remove-object",
                "NoSuchChild",
            ],
        )

        assert result.exit_code != 0
        assert "not found" in result.output

    def test_full_workflow(self, runner, tmp_path):
        prefab_file = tmp_path / "Board.prefab"

        result = runner.invoke(
            main,
            ["create", str(prefab_file), "--name", "Root", "--type", "rect-transform"],
        )
        assert result.exit_code == 0

        result = runner.invoke(
            main,
            [
                "set",
                str(prefab_file),
                "--path",
                "Root",
                "--add-object",
                "board_base",
                "--type",
                "rect-transform",
            ],
        )
        assert result.exit_code == 0

        result = runner.invoke(
            main,
            [
                "set",
                str(prefab_file),
                "--path",
                "Root",
                "--add-component",
                "CanvasRenderer",
            ],
        )
        assert result.exit_code == 0

        from unityflow.parser import UnityYAMLDocument

        doc = UnityYAMLDocument.load(prefab_file)
        assert len(doc.get_game_objects()) == 2
        assert len(doc.get_rect_transforms()) == 2

        root_go = None
        child_go = None
        for go in doc.get_game_objects():
            name = go.get_content()["m_Name"]
            if name == "Root":
                root_go = go
            elif name == "board_base":
                child_go = go

        assert root_go is not None
        assert child_go is not None
        assert len(root_go.get_content()["m_Component"]) == 2

        result = runner.invoke(
            main,
            [
                "set",
                str(prefab_file),
                "--path",
                "Root/board_base/RectTransform",
                "--batch",
                '{"m_SizeDelta": {"x": 200, "y": 300}}',
            ],
        )
        assert result.exit_code == 0, f"Command failed: {result.output}"

        result = runner.invoke(
            main,
            [
                "set",
                str(prefab_file),
                "--path",
                "Root",
                "--remove-component",
                "CanvasRenderer",
            ],
        )
        assert result.exit_code == 0

        result = runner.invoke(
            main,
            [
                "set",
                str(prefab_file),
                "--path",
                "Root",
                "--remove-object",
                "board_base",
            ],
        )
        assert result.exit_code == 0

        doc = UnityYAMLDocument.load(prefab_file)
        assert len(doc.get_game_objects()) == 1
        assert doc.get_game_objects()[0].get_content()["m_Name"] == "Root"

    def test_add_component_prefers_runtime_over_editor(self, runner, tmp_path):
        import shutil

        project_root = tmp_path / "project"
        (project_root / "Assets").mkdir(parents=True)
        (project_root / "ProjectSettings").mkdir()

        editor_dir = project_root / "Assets" / "Editor"
        editor_dir.mkdir(parents=True)
        (editor_dir / "MyComp.cs").write_text("public class MyComp : MonoBehaviour {}")
        (editor_dir / "MyComp.cs.meta").write_text("fileFormatVersion: 2\nguid: eeee000011112222eeee000011112222\n")

        runtime_dir = project_root / "Assets" / "Scripts"
        runtime_dir.mkdir(parents=True)
        (runtime_dir / "MyComp.cs").write_text("public class MyComp : MonoBehaviour {}")
        (runtime_dir / "MyComp.cs.meta").write_text("fileFormatVersion: 2\nguid: aabb000011112222aabb000011112222\n")

        test_file = project_root / "Assets" / "basic.prefab"
        shutil.copy(FIXTURES_DIR / "basic_prefab.prefab", test_file)

        result = runner.invoke(
            main,
            [
                "set",
                str(test_file),
                "--path",
                "BasicPrefab",
                "--add-component",
                "MyComp",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        content = test_file.read_text()
        assert "aabb000011112222aabb000011112222" in content
        assert "eeee000011112222eeee000011112222" not in content

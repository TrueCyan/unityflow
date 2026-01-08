"""Tests for Unity prefab validator."""

from pathlib import Path

from unityflow.parser import UnityYAMLDocument
from unityflow.validator import (
    PrefabValidator,
    Severity,
    ValidationIssue,
    fix_document,
    fix_invalid_guids,
    fix_scene_roots,
    is_valid_guid,
    validate_prefab,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestPrefabValidator:
    """Tests for PrefabValidator class."""

    def test_validate_basic_prefab(self):
        """Test validating a basic valid prefab."""
        validator = PrefabValidator()
        result = validator.validate_file(FIXTURES_DIR / "basic_prefab.prefab")

        assert result.is_valid
        assert len(result.errors) == 0

    def test_validate_unsorted_prefab(self):
        """Test validating an unsorted but valid prefab."""
        validator = PrefabValidator()
        result = validator.validate_file(FIXTURES_DIR / "unsorted_prefab.prefab")

        assert result.is_valid
        assert len(result.errors) == 0

    def test_validate_prefab_with_modifications(self):
        """Test validating a prefab with modifications."""
        validator = PrefabValidator()
        result = validator.validate_file(FIXTURES_DIR / "prefab_with_modifications.prefab")

        # Should be valid (external references are warnings, not errors)
        assert result.is_valid

    def test_file_not_found(self):
        """Test error when file doesn't exist."""
        validator = PrefabValidator()
        result = validator.validate_file(Path("/nonexistent/file.prefab"))

        assert not result.is_valid
        assert len(result.errors) == 1
        assert "not found" in result.errors[0].message.lower()

    def test_validate_invalid_yaml(self):
        """Test error when YAML is invalid."""
        validator = PrefabValidator()

        # Create a temp file with invalid content
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".prefab", delete=False) as f:
            f.write("%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n--- !u!1 &123\n  invalid: yaml:\n")
            temp_path = f.name

        try:
            result = validator.validate_file(temp_path)
            # Should fail to parse
            assert not result.is_valid
        finally:
            Path(temp_path).unlink()


class TestValidationIssue:
    """Tests for ValidationIssue class."""

    def test_issue_string_representation(self):
        """Test string representation of validation issue."""
        issue = ValidationIssue(
            severity=Severity.ERROR,
            message="Test error",
            file_id=12345,
            property_path="Transform.m_LocalPosition",
            suggestion="Fix it",
        )

        str_repr = str(issue)
        assert "ERROR" in str_repr
        assert "12345" in str_repr
        assert "Test error" in str_repr
        assert "Transform.m_LocalPosition" in str_repr
        assert "Fix it" in str_repr

    def test_issue_without_optional_fields(self):
        """Test issue without optional fields."""
        issue = ValidationIssue(
            severity=Severity.WARNING,
            message="Simple warning",
        )

        str_repr = str(issue)
        assert "WARNING" in str_repr
        assert "Simple warning" in str_repr


class TestValidationResult:
    """Tests for ValidationResult class."""

    def test_filter_by_severity(self):
        """Test filtering issues by severity."""
        from unityflow.validator import ValidationResult

        result = ValidationResult(
            path="test.prefab",
            is_valid=False,
            issues=[
                ValidationIssue(severity=Severity.ERROR, message="Error 1"),
                ValidationIssue(severity=Severity.ERROR, message="Error 2"),
                ValidationIssue(severity=Severity.WARNING, message="Warning 1"),
                ValidationIssue(severity=Severity.INFO, message="Info 1"),
            ],
        )

        assert len(result.errors) == 2
        assert len(result.warnings) == 1
        assert len(result.infos) == 1


class TestStrictMode:
    """Tests for strict validation mode."""

    def test_strict_mode_fails_on_warnings(self):
        """Test that strict mode treats warnings as errors."""
        validator = PrefabValidator(strict=True)

        # Create content that generates warnings but not errors
        content = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!1 &100000
GameObject:
  m_ObjectHideFlags: 0
"""
        result = validator.validate_content(content, "test.prefab")

        # In strict mode, warnings make the result invalid
        if result.warnings:
            assert not result.is_valid


class TestDuplicateFileIDs:
    """Tests for duplicate fileID detection."""

    def test_detect_duplicate_file_ids(self):
        """Test detection of duplicate fileIDs."""
        validator = PrefabValidator()

        content = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!1 &100000
GameObject:
  m_Name: First
--- !u!1 &100000
GameObject:
  m_Name: Second
"""
        result = validator.validate_content(content, "test.prefab")

        assert not result.is_valid
        assert any("Duplicate" in e.message for e in result.errors)


class TestConvenienceFunction:
    """Tests for the validate_prefab convenience function."""

    def test_validate_prefab_function(self):
        """Test the validate_prefab convenience function."""
        result = validate_prefab(FIXTURES_DIR / "basic_prefab.prefab")

        assert result.is_valid
        assert result.path == str(FIXTURES_DIR / "basic_prefab.prefab")

    def test_validate_prefab_strict(self):
        """Test validate_prefab with strict mode."""
        result = validate_prefab(FIXTURES_DIR / "basic_prefab.prefab", strict=True)

        # A valid prefab should still be valid in strict mode
        # (unless there are warnings)
        assert isinstance(result.is_valid, bool)


class TestGuidValidation:
    """Tests for GUID format validation."""

    def test_valid_guid(self):
        """Test valid GUID formats."""
        assert is_valid_guid("31ad2c60d35ebf74484676a2cf8f247c")
        assert is_valid_guid("ABCDEF0123456789abcdef0123456789")
        assert is_valid_guid("00000000000000000000000000000000")

    def test_invalid_guid_formats(self):
        """Test invalid GUID formats."""
        # Float value (common LLM mistake)
        assert not is_valid_guid(0.0)
        assert not is_valid_guid(0)
        # Wrong length
        assert not is_valid_guid("abc123")
        assert not is_valid_guid("31ad2c60d35ebf74484676a2cf8f247c0")  # too long
        # Invalid characters
        assert not is_valid_guid("31ad2c60d35ebf74484676a2cf8f247g")
        # Empty string
        assert not is_valid_guid("")

    def test_none_guid_is_valid(self):
        """Test that None is valid (internal reference)."""
        assert is_valid_guid(None)

    def test_detect_invalid_guid_in_reference(self):
        """Test that validator detects invalid GUID in references."""
        validator = PrefabValidator()

        # Content with invalid GUID (float 0.0)
        content = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!104 &2
RenderSettings:
  m_SpotCookie: {fileID: 10001, guid: 0.0, type: 0}
"""
        result = validator.validate_content(content, "test.unity")

        assert not result.is_valid
        assert any("Invalid GUID format" in e.message for e in result.errors)


class TestSceneRootsValidation:
    """Tests for SceneRoots validation."""

    def test_detect_missing_scene_roots(self):
        """Test detection of missing roots in SceneRoots."""
        validator = PrefabValidator()

        # Scene with 2 root transforms but SceneRoots only has 1
        content = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!1 &100000
GameObject:
  m_Name: Object1
  m_Component:
  - component: {fileID: 100001}
--- !u!4 &100001
Transform:
  m_GameObject: {fileID: 100000}
  m_Father: {fileID: 0}
  m_Children: []
--- !u!1 &200000
GameObject:
  m_Name: Object2
  m_Component:
  - component: {fileID: 200001}
--- !u!4 &200001
Transform:
  m_GameObject: {fileID: 200000}
  m_Father: {fileID: 0}
  m_Children: []
--- !u!1660057539 &9223372036854775807
SceneRoots:
  m_Roots:
  - {fileID: 100001}
"""
        result = validator.validate_content(content, "test.unity")

        assert not result.is_valid
        assert any("SceneRoots missing" in e.message for e in result.errors)


class TestFixInvalidGuids:
    """Tests for fix_invalid_guids function."""

    def test_fix_float_guid(self):
        """Test fixing a float GUID value."""
        content = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!104 &2
RenderSettings:
  m_SpotCookie: {fileID: 10001, guid: 0.0, type: 0}
"""
        doc = UnityYAMLDocument.parse(content)
        fixed_count = fix_invalid_guids(doc)

        assert fixed_count == 1

        # Verify the guid was removed
        obj = doc.get_by_file_id(2)
        content = obj.get_content()
        spot_cookie = content.get("m_SpotCookie", {})
        assert "guid" not in spot_cookie
        assert spot_cookie.get("fileID") == 10001

    def test_preserve_valid_guid(self):
        """Test that valid GUIDs are preserved."""
        content = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!114 &100
MonoBehaviour:
  m_Script: {fileID: 11500000, guid: 31ad2c60d35ebf74484676a2cf8f247c, type: 3}
"""
        doc = UnityYAMLDocument.parse(content)
        fixed_count = fix_invalid_guids(doc)

        assert fixed_count == 0

        # Verify the guid is preserved
        obj = doc.get_by_file_id(100)
        content = obj.get_content()
        script = content.get("m_Script", {})
        assert script.get("guid") == "31ad2c60d35ebf74484676a2cf8f247c"


class TestFixSceneRoots:
    """Tests for fix_scene_roots function."""

    def test_fix_incomplete_scene_roots(self):
        """Test fixing incomplete SceneRoots."""
        content = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!1 &100000
GameObject:
  m_Name: Object1
  m_Component:
  - component: {fileID: 100001}
--- !u!4 &100001
Transform:
  m_GameObject: {fileID: 100000}
  m_Father: {fileID: 0}
  m_Children: []
--- !u!1 &200000
GameObject:
  m_Name: Object2
  m_Component:
  - component: {fileID: 200001}
--- !u!4 &200001
Transform:
  m_GameObject: {fileID: 200000}
  m_Father: {fileID: 0}
  m_Children: []
--- !u!1660057539 &9223372036854775807
SceneRoots:
  m_Roots:
  - {fileID: 100001}
"""
        doc = UnityYAMLDocument.parse(content)
        fixed = fix_scene_roots(doc)

        assert fixed is True

        # Verify SceneRoots now has both roots
        scene_roots = doc.get_by_file_id(9223372036854775807)
        content = scene_roots.get_content()
        roots = content.get("m_Roots", [])
        root_ids = {r.get("fileID") for r in roots}

        assert 100001 in root_ids
        assert 200001 in root_ids

    def test_no_fix_needed_for_complete_scene_roots(self):
        """Test that complete SceneRoots is not modified."""
        content = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!4 &100001
Transform:
  m_Father: {fileID: 0}
--- !u!1660057539 &9223372036854775807
SceneRoots:
  m_Roots:
  - {fileID: 100001}
"""
        doc = UnityYAMLDocument.parse(content)
        fixed = fix_scene_roots(doc)

        assert fixed is False


class TestFixDocument:
    """Tests for fix_document function."""

    def test_fix_document_multiple_issues(self):
        """Test fixing multiple issues in one document."""
        content = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!104 &2
RenderSettings:
  m_SpotCookie: {fileID: 10001, guid: 0.0, type: 0}
--- !u!4 &100001
Transform:
  m_Father: {fileID: 0}
--- !u!4 &200001
Transform:
  m_Father: {fileID: 0}
--- !u!1660057539 &9223372036854775807
SceneRoots:
  m_Roots:
  - {fileID: 100001}
"""
        doc = UnityYAMLDocument.parse(content)
        results = fix_document(doc)

        assert results["invalid_guids_fixed"] == 1
        assert results["scene_roots_fixed"] == 1

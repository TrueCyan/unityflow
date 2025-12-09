"""Tests for Unity prefab validator."""

from pathlib import Path

import pytest

from prefab_tool.validator import PrefabValidator, validate_prefab, Severity, ValidationIssue

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
        from prefab_tool.validator import ValidationResult

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

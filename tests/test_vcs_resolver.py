"""Tests for VCS merge conflict resolver."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from unityflow.semantic_merge import ConflictType, PropertyConflict
from unityflow.vcs_resolver import (
    ChangeInfo,
    ConflictInfo,
    ModificationContext,
    ResolutionStrategy,
    ResolveResult,
    VCSType,
    _calculate_relevance_score,
    _format_value,
    _suggest_resolution,
    detect_vcs,
    extract_object_names,
    format_conflict_for_user,
    infer_intent,
)


class TestExtractObjectNames:
    """Tests for extract_object_names function."""

    def test_extract_path_patterns(self):
        """Should extract path-like patterns."""
        desc = "Fixed position of Player/Body/Hand"
        names = extract_object_names(desc)
        assert "Player/Body/Hand" in names

    def test_extract_quoted_strings(self):
        """Should extract quoted strings."""
        desc = "Updated \"MainCamera\" position and 'Player' rotation"
        names = extract_object_names(desc)
        assert "MainCamera" in names
        assert "Player" in names

    def test_extract_component_types(self):
        """Should extract known component types."""
        desc = "Modified Transform and SpriteRenderer"
        names = extract_object_names(desc)
        assert "Transform" in names
        assert "SpriteRenderer" in names

    def test_case_insensitive_components(self):
        """Should find components case-insensitively."""
        desc = "fixed the image color"
        names = extract_object_names(desc)
        assert "Image" in names


class TestInferIntent:
    """Tests for infer_intent function."""

    def test_infer_bug_fix(self):
        """Should detect bug fix intent."""
        assert "bug fix" in infer_intent("Fix crash when loading scene").lower()
        assert "bug fix" in infer_intent("Bug: player position not saved").lower()

    def test_infer_new_feature(self):
        """Should detect new feature intent."""
        assert "new feature" in infer_intent("Add new health bar UI").lower()
        assert "new feature" in infer_intent("Implement inventory system").lower()

    def test_infer_layout_change(self):
        """Should detect layout change intent."""
        # "position", "move", "layout", "align" as separate words trigger layout pattern
        assert "layout" in infer_intent("Move buttons to center").lower()
        assert "layout" in infer_intent("Align panel layout").lower()

    def test_infer_visual_change(self):
        """Should detect visual change intent."""
        # "color", "style", "visual", "appearance" as separate words trigger visual pattern
        # Note: Must not contain "update", "change", etc. which trigger modification first
        assert "visual" in infer_intent("Improved visual effects").lower()
        assert "visual" in infer_intent("Better appearance for player").lower()

    def test_modification_pattern(self):
        """Should detect modification intent."""
        # "update", "adjust", "change" trigger modification pattern first
        assert "modification" in infer_intent("Update button position").lower()
        assert "modification" in infer_intent("Adjust panel layout").lower()

    def test_fallback_to_first_line(self):
        """Should use first line as fallback when no pattern matches."""
        desc = "XYZ something\nMore details here"
        intent = infer_intent(desc)
        # Should return first line when no pattern matches
        assert "XYZ something" in intent


class TestFormatValue:
    """Tests for _format_value function."""

    def test_format_vector2(self):
        """Should format Vector2 values."""
        result = _format_value({"x": 1, "y": 2})
        assert result == "(1, 2)"

    def test_format_vector3(self):
        """Should format Vector3 values."""
        result = _format_value({"x": 1, "y": 2, "z": 3})
        assert result == "(1, 2, 3)"

    def test_format_vector4(self):
        """Should format Vector4 values."""
        result = _format_value({"x": 1, "y": 2, "z": 3, "w": 4})
        assert result == "(1, 2, 3, 4)"

    def test_format_color(self):
        """Should format color values."""
        result = _format_value({"r": 1, "g": 0.5, "b": 0, "a": 1})
        assert "rgba" in result

    def test_format_reference(self):
        """Should format fileID references."""
        result = _format_value({"fileID": 12345})
        assert "ref(12345)" == result

    def test_format_list(self):
        """Should format lists with count."""
        result = _format_value([1, 2, 3, 4, 5])
        assert "[5 items]" == result

    def test_format_long_string(self):
        """Should truncate long strings."""
        long_str = "a" * 50
        result = _format_value(long_str)
        assert "..." in result
        assert len(result) < 50


class TestSuggestResolution:
    """Tests for _suggest_resolution function."""

    def test_transform_requires_manual(self):
        """Transform changes should require manual review."""
        conflict = PropertyConflict(
            file_id=1,
            class_name="Transform",
            property_path="m_LocalPosition.x",
            base_value=0,
            ours_value=1,
            theirs_value=2,
            conflict_type=ConflictType.BOTH_MODIFIED,
        )
        strategy, reason = _suggest_resolution(conflict, None)
        assert strategy == ResolutionStrategy.MANUAL

    def test_sorting_order_takes_higher(self):
        """Sorting order should take higher value."""
        conflict = PropertyConflict(
            file_id=1,
            class_name="SpriteRenderer",
            property_path="m_SortingOrder",
            base_value=0,
            ours_value=5,
            theirs_value=3,
            conflict_type=ConflictType.BOTH_MODIFIED,
        )
        strategy, reason = _suggest_resolution(conflict, None)
        assert strategy == ResolutionStrategy.OURS

    def test_enabled_keeps_enabled(self):
        """Should prefer keeping objects enabled."""
        conflict = PropertyConflict(
            file_id=1,
            class_name="MonoBehaviour",
            property_path="m_Enabled",
            base_value=1,
            ours_value=0,
            theirs_value=1,
            conflict_type=ConflictType.BOTH_MODIFIED,
        )
        strategy, reason = _suggest_resolution(conflict, None)
        assert strategy == ResolutionStrategy.THEIRS


class TestCalculateRelevanceScore:
    """Tests for _calculate_relevance_score function."""

    def test_score_with_matching_object_name(self):
        """Should increase score when object name matches."""
        conflict = PropertyConflict(
            file_id=1,
            class_name="Transform",
            property_path="m_LocalPosition",
            base_value=0,
            ours_value=1,
            theirs_value=2,
            conflict_type=ConflictType.BOTH_MODIFIED,
            game_object_name="Player",
        )
        context = ModificationContext(
            file_path=Path("test.prefab"),
            ours_change=ChangeInfo(
                identifier="abc123",
                author="test",
                date="2024-01-01",
                description="Updated Player position",
                vcs_type=VCSType.GIT,
            ),
            theirs_change=None,
            ours_objects=["Player"],
            theirs_objects=[],
            ours_intent="modification",
            theirs_intent="",
        )
        score = _calculate_relevance_score(conflict, context, is_ours=True)
        assert score >= 2  # Should get points for matching object name

    def test_score_with_bug_fix(self):
        """Bug fixes should get higher score."""
        conflict = PropertyConflict(
            file_id=1,
            class_name="Transform",
            property_path="m_LocalPosition",
            base_value=0,
            ours_value=1,
            theirs_value=2,
            conflict_type=ConflictType.BOTH_MODIFIED,
        )
        context = ModificationContext(
            file_path=Path("test.prefab"),
            ours_change=ChangeInfo(
                identifier="abc123",
                author="test",
                date="2024-01-01",
                description="Fix position bug",
                vcs_type=VCSType.GIT,
            ),
            theirs_change=None,
            ours_objects=[],
            theirs_objects=[],
            ours_intent="bug fix",
            theirs_intent="",
        )
        score = _calculate_relevance_score(conflict, context, is_ours=True)
        assert score >= 2


class TestFormatConflictForUser:
    """Tests for format_conflict_for_user function."""

    def test_basic_format(self):
        """Should format basic conflict info."""
        conflict = PropertyConflict(
            file_id=1,
            class_name="Transform",
            property_path="m_LocalPosition.x",
            base_value=0,
            ours_value=1,
            theirs_value=2,
            conflict_type=ConflictType.BOTH_MODIFIED,
            game_object_name="Player",
        )
        info = ConflictInfo(
            conflict=conflict,
            game_object_path="Player",
            component_type="Transform",
            property_display="m_LocalPosition.x: 1 vs 2",
            ours_context="abc123: modification",
            theirs_context="def456: layout change",
            suggested_resolution=ResolutionStrategy.MANUAL,
            suggestion_reason="Transform changes require manual review",
        )
        formatted = format_conflict_for_user(info, 1)
        assert "[Conflict 1]" in formatted
        assert "Player" in formatted
        assert "Transform" in formatted


class TestResolveResult:
    """Tests for ResolveResult dataclass."""

    def test_success_result(self):
        """Should create success result."""
        result = ResolveResult(
            file_path=Path("test.prefab"),
            success=True,
            strategy=ResolutionStrategy.AUTO,
            auto_merged_count=5,
            conflict_count=0,
            conflicts_resolved=0,
            message="Auto-merged successfully",
        )
        assert result.success
        assert result.strategy == ResolutionStrategy.AUTO

    def test_conflict_result(self):
        """Should create conflict result."""
        result = ResolveResult(
            file_path=Path("test.prefab"),
            success=False,
            strategy=ResolutionStrategy.MANUAL,
            auto_merged_count=3,
            conflict_count=2,
            conflicts_resolved=1,
            message="1 conflict remaining",
        )
        assert not result.success
        assert result.conflict_count == 2


class TestDetectVCS:
    """Tests for detect_vcs function."""

    @patch("unityflow.vcs_resolver.GitAdapter")
    @patch("unityflow.vcs_resolver.PerforceAdapter")
    def test_detect_git(self, mock_p4, mock_git):
        """Should detect Git when available."""
        mock_git_instance = MagicMock()
        mock_git_instance.is_available.return_value = True
        mock_git.return_value = mock_git_instance

        mock_p4_instance = MagicMock()
        mock_p4_instance.is_available.return_value = False
        mock_p4.return_value = mock_p4_instance

        adapter = detect_vcs()
        assert adapter is not None

    @patch("unityflow.vcs_resolver.GitAdapter")
    @patch("unityflow.vcs_resolver.PerforceAdapter")
    def test_detect_perforce(self, mock_p4, mock_git):
        """Should detect Perforce when Git not available."""
        mock_git_instance = MagicMock()
        mock_git_instance.is_available.return_value = False
        mock_git.return_value = mock_git_instance

        mock_p4_instance = MagicMock()
        mock_p4_instance.is_available.return_value = True
        mock_p4.return_value = mock_p4_instance

        adapter = detect_vcs()
        assert adapter is not None

    @patch("unityflow.vcs_resolver.GitAdapter")
    @patch("unityflow.vcs_resolver.PerforceAdapter")
    def test_detect_none(self, mock_p4, mock_git):
        """Should return None when no VCS available."""
        mock_git_instance = MagicMock()
        mock_git_instance.is_available.return_value = False
        mock_git.return_value = mock_git_instance

        mock_p4_instance = MagicMock()
        mock_p4_instance.is_available.return_value = False
        mock_p4.return_value = mock_p4_instance

        adapter = detect_vcs()
        assert adapter is None


class TestVCSType:
    """Tests for VCSType enum."""

    def test_git_type(self):
        """Git type should have correct value."""
        assert VCSType.GIT.value == "git"

    def test_perforce_type(self):
        """Perforce type should have correct value."""
        assert VCSType.PERFORCE.value == "perforce"


class TestChangeInfo:
    """Tests for ChangeInfo dataclass."""

    def test_get_summary(self):
        """Should get first line as summary."""
        info = ChangeInfo(
            identifier="abc123",
            author="test",
            date="2024-01-01",
            description="First line\nSecond line\nThird line",
            vcs_type=VCSType.GIT,
        )
        assert info.get_summary() == "First line"

    def test_get_summary_empty(self):
        """Should handle empty description."""
        info = ChangeInfo(
            identifier="abc123",
            author="test",
            date="2024-01-01",
            description="",
            vcs_type=VCSType.GIT,
        )
        assert info.get_summary() == ""

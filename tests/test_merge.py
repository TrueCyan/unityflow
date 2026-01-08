"""Tests for three-way merge functionality."""

from unityflow.merge import (
    CONFLICT_END,
    CONFLICT_START,
    compute_changes,
    merge_lines,
    three_way_merge,
)


class TestThreeWayMerge:
    """Tests for the three_way_merge function."""

    def test_identical_files(self):
        """Test merging identical files."""
        content = "line1\nline2\nline3\n"
        result, has_conflict = three_way_merge(content, content, content)

        assert result == content
        assert not has_conflict

    def test_only_ours_changed(self):
        """Test when only our version changed."""
        base = "line1\nline2\nline3\n"
        ours = "line1\nmodified\nline3\n"
        theirs = base

        result, has_conflict = three_way_merge(base, ours, theirs)

        assert result == ours
        assert not has_conflict

    def test_only_theirs_changed(self):
        """Test when only their version changed."""
        base = "line1\nline2\nline3\n"
        ours = base
        theirs = "line1\nmodified\nline3\n"

        result, has_conflict = three_way_merge(base, ours, theirs)

        assert result == theirs
        assert not has_conflict

    def test_both_made_same_change(self):
        """Test when both sides made the same change."""
        base = "line1\nline2\nline3\n"
        ours = "line1\nmodified\nline3\n"
        theirs = "line1\nmodified\nline3\n"

        result, has_conflict = three_way_merge(base, ours, theirs)

        assert result == ours
        assert not has_conflict

    def test_non_overlapping_changes(self):
        """Test non-overlapping changes merge cleanly."""
        base = "line1\nline2\nline3\nline4\nline5\n"
        ours = "OURS\nline2\nline3\nline4\nline5\n"
        theirs = "line1\nline2\nline3\nline4\nTHEIRS\n"

        result, has_conflict = three_way_merge(base, ours, theirs)

        assert "OURS" in result
        assert "THEIRS" in result
        assert not has_conflict

    def test_conflicting_changes(self):
        """Test that overlapping changes create conflicts."""
        base = "line1\nline2\nline3\n"
        ours = "line1\nOURS\nline3\n"
        theirs = "line1\nTHEIRS\nline3\n"

        result, has_conflict = three_way_merge(base, ours, theirs)

        assert has_conflict
        assert CONFLICT_START in result
        assert CONFLICT_END in result
        assert "OURS" in result
        assert "THEIRS" in result

    def test_addition_by_ours(self):
        """Test when ours adds lines."""
        base = "line1\nline3\n"
        ours = "line1\nline2\nline3\n"
        theirs = base

        result, has_conflict = three_way_merge(base, ours, theirs)

        assert result == ours
        assert not has_conflict

    def test_deletion_by_theirs(self):
        """Test when theirs deletes lines."""
        base = "line1\nline2\nline3\n"
        ours = base
        theirs = "line1\nline3\n"

        result, has_conflict = three_way_merge(base, ours, theirs)

        assert result == theirs
        assert not has_conflict


class TestMergeLines:
    """Tests for the merge_lines function."""

    def test_empty_files(self):
        """Test merging empty files."""
        result = merge_lines([], [], [])

        # Empty input produces empty output (or just trailing newline)
        assert result.content in ("", "\n")
        assert not result.has_conflicts

    def test_multiple_conflicts(self):
        """Test multiple conflicts are counted."""
        base = ["a\n", "b\n", "c\n", "d\n", "e\n"]
        ours = ["A\n", "b\n", "C\n", "d\n", "E\n"]
        theirs = ["X\n", "b\n", "Y\n", "d\n", "Z\n"]

        result = merge_lines(base, ours, theirs)

        assert result.has_conflicts
        assert result.conflict_count >= 1


class TestComputeChanges:
    """Tests for the compute_changes function."""

    def test_no_changes(self):
        """Test when there are no changes."""
        lines = ["a\n", "b\n", "c\n"]
        changes = list(compute_changes(lines, lines))

        assert len(changes) == 0

    def test_single_replacement(self):
        """Test a single line replacement."""
        base = ["a\n", "b\n", "c\n"]
        new = ["a\n", "X\n", "c\n"]

        changes = list(compute_changes(base, new))

        assert len(changes) == 1
        assert changes[0].base_start == 1
        assert changes[0].base_end == 2
        assert changes[0].new_lines == ["X\n"]

    def test_insertion(self):
        """Test line insertion."""
        base = ["a\n", "c\n"]
        new = ["a\n", "b\n", "c\n"]

        changes = list(compute_changes(base, new))

        assert len(changes) == 1
        assert changes[0].new_lines == ["b\n"]

    def test_deletion(self):
        """Test line deletion."""
        base = ["a\n", "b\n", "c\n"]
        new = ["a\n", "c\n"]

        changes = list(compute_changes(base, new))

        assert len(changes) == 1
        assert changes[0].new_lines == []


class TestUnityYAMLMerge:
    """Tests for merging Unity YAML content."""

    def test_merge_different_properties(self):
        """Test merging changes to different properties."""
        base = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!4 &100000
Transform:
  m_LocalPosition: {x: 0, y: 0, z: 0}
  m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}
  m_LocalScale: {x: 1, y: 1, z: 1}
"""
        ours = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!4 &100000
Transform:
  m_LocalPosition: {x: 5, y: 0, z: 0}
  m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}
  m_LocalScale: {x: 1, y: 1, z: 1}
"""
        theirs = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!4 &100000
Transform:
  m_LocalPosition: {x: 0, y: 0, z: 0}
  m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}
  m_LocalScale: {x: 2, y: 2, z: 2}
"""

        result, has_conflict = three_way_merge(base, ours, theirs)

        # Both changes should be applied
        assert "x: 5" in result  # Our position change
        assert "x: 2, y: 2, z: 2" in result  # Their scale change
        assert not has_conflict

    def test_merge_same_property_conflict(self):
        """Test conflict when both modify same property."""
        base = """%YAML 1.1
--- !u!4 &100000
Transform:
  m_LocalPosition: {x: 0, y: 0, z: 0}
"""
        ours = """%YAML 1.1
--- !u!4 &100000
Transform:
  m_LocalPosition: {x: 5, y: 0, z: 0}
"""
        theirs = """%YAML 1.1
--- !u!4 &100000
Transform:
  m_LocalPosition: {x: 10, y: 0, z: 0}
"""

        result, has_conflict = three_way_merge(base, ours, theirs)

        assert has_conflict
        assert "x: 5" in result
        assert "x: 10" in result

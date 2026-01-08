"""Tests for semantic three-way merge functionality."""

from unityflow.parser import UnityYAMLDocument, UnityYAMLObject
from unityflow.semantic_merge import (
    ConflictType,
    PropertyConflict,
    SemanticMergeResult,
    apply_all_resolutions,
    apply_resolution,
    semantic_three_way_merge,
)


def _create_transform_object(
    file_id: int,
    position: dict | None = None,
    rotation: dict | None = None,
    scale: dict | None = None,
    children: list | None = None,
) -> UnityYAMLObject:
    """Helper to create a Transform object."""
    return UnityYAMLObject(
        class_id=4,
        file_id=file_id,
        data={
            "Transform": {
                "m_LocalPosition": position or {"x": 0, "y": 0, "z": 0},
                "m_LocalRotation": rotation or {"x": 0, "y": 0, "z": 0, "w": 1},
                "m_LocalScale": scale or {"x": 1, "y": 1, "z": 1},
                "m_Children": children if children is not None else [],
                "m_Father": {"fileID": 0},
            }
        },
    )


def _create_game_object(file_id: int, name: str) -> UnityYAMLObject:
    """Helper to create a GameObject."""
    return UnityYAMLObject(
        class_id=1,
        file_id=file_id,
        data={
            "GameObject": {
                "m_Name": name,
                "m_Layer": 0,
                "m_IsActive": 1,
            }
        },
    )


class TestSemanticThreeWayMerge:
    """Tests for the semantic_three_way_merge function."""

    def test_identical_documents(self):
        """Test merging identical documents."""
        doc = UnityYAMLDocument()
        doc.add_object(_create_transform_object(100000))

        result = semantic_three_way_merge(doc, doc, doc)

        assert not result.has_conflicts
        assert result.conflict_count == 0

    def test_only_ours_changed(self):
        """Test when only our version changed."""
        base = UnityYAMLDocument()
        base.add_object(_create_transform_object(100000, position={"x": 0, "y": 0, "z": 0}))

        ours = UnityYAMLDocument()
        ours.add_object(_create_transform_object(100000, position={"x": 5, "y": 0, "z": 0}))

        theirs = UnityYAMLDocument()
        theirs.add_object(_create_transform_object(100000, position={"x": 0, "y": 0, "z": 0}))

        result = semantic_three_way_merge(base, ours, theirs)

        assert not result.has_conflicts
        # Merged should have our position
        merged_obj = result.merged_document.get_by_file_id(100000)
        assert merged_obj is not None
        content = merged_obj.get_content()
        assert content["m_LocalPosition"]["x"] == 5

    def test_only_theirs_changed(self):
        """Test when only their version changed."""
        base = UnityYAMLDocument()
        base.add_object(_create_transform_object(100000, position={"x": 0, "y": 0, "z": 0}))

        ours = UnityYAMLDocument()
        ours.add_object(_create_transform_object(100000, position={"x": 0, "y": 0, "z": 0}))

        theirs = UnityYAMLDocument()
        theirs.add_object(_create_transform_object(100000, position={"x": 10, "y": 0, "z": 0}))

        result = semantic_three_way_merge(base, ours, theirs)

        assert not result.has_conflicts
        # Merged should have their position
        merged_obj = result.merged_document.get_by_file_id(100000)
        assert merged_obj is not None
        content = merged_obj.get_content()
        assert content["m_LocalPosition"]["x"] == 10

    def test_non_overlapping_changes(self):
        """Test non-overlapping changes merge automatically."""
        base = UnityYAMLDocument()
        base.add_object(
            _create_transform_object(100000, position={"x": 0, "y": 0, "z": 0}, scale={"x": 1, "y": 1, "z": 1})
        )

        ours = UnityYAMLDocument()
        ours.add_object(
            _create_transform_object(
                100000,
                position={"x": 5, "y": 0, "z": 0},  # Changed position
                scale={"x": 1, "y": 1, "z": 1},
            )
        )

        theirs = UnityYAMLDocument()
        theirs.add_object(
            _create_transform_object(
                100000,
                position={"x": 0, "y": 0, "z": 0},
                scale={"x": 2, "y": 2, "z": 2},  # Changed scale
            )
        )

        result = semantic_three_way_merge(base, ours, theirs)

        assert not result.has_conflicts
        # Both changes should be applied
        merged_obj = result.merged_document.get_by_file_id(100000)
        assert merged_obj is not None
        content = merged_obj.get_content()
        assert content["m_LocalPosition"]["x"] == 5  # Our change
        assert content["m_LocalScale"]["x"] == 2  # Their change

    def test_conflicting_changes(self):
        """Test conflicting changes are detected."""
        base = UnityYAMLDocument()
        base.add_object(_create_transform_object(100000, position={"x": 0, "y": 0, "z": 0}))

        ours = UnityYAMLDocument()
        ours.add_object(_create_transform_object(100000, position={"x": 5, "y": 0, "z": 0}))

        theirs = UnityYAMLDocument()
        theirs.add_object(_create_transform_object(100000, position={"x": 10, "y": 0, "z": 0}))

        result = semantic_three_way_merge(base, ours, theirs)

        assert result.has_conflicts
        assert result.conflict_count >= 1

        # Should have conflict for position.x
        conflicts = result.get_conflicts_for_object(100000)
        assert len(conflicts) >= 1

        conflict = conflicts[0]
        assert conflict.conflict_type == ConflictType.BOTH_MODIFIED
        assert conflict.base_value == 0
        assert conflict.ours_value == 5
        assert conflict.theirs_value == 10

    def test_both_made_same_change(self):
        """Test when both sides made the same change."""
        base = UnityYAMLDocument()
        base.add_object(_create_transform_object(100000, position={"x": 0, "y": 0, "z": 0}))

        ours = UnityYAMLDocument()
        ours.add_object(_create_transform_object(100000, position={"x": 5, "y": 0, "z": 0}))

        theirs = UnityYAMLDocument()
        theirs.add_object(_create_transform_object(100000, position={"x": 5, "y": 0, "z": 0}))

        result = semantic_three_way_merge(base, ours, theirs)

        assert not result.has_conflicts
        # Merged should have the common change
        merged_obj = result.merged_document.get_by_file_id(100000)
        assert merged_obj is not None
        content = merged_obj.get_content()
        assert content["m_LocalPosition"]["x"] == 5

    def test_object_added_by_theirs(self):
        """Test when theirs adds a new object."""
        base = UnityYAMLDocument()
        base.add_object(_create_transform_object(100000))

        ours = UnityYAMLDocument()
        ours.add_object(_create_transform_object(100000))

        theirs = UnityYAMLDocument()
        theirs.add_object(_create_transform_object(100000))
        theirs.add_object(_create_transform_object(200000))

        result = semantic_three_way_merge(base, ours, theirs)

        assert not result.has_conflicts
        # New object should be in merged
        assert result.merged_document.get_by_file_id(200000) is not None

    def test_object_added_by_ours(self):
        """Test when ours adds a new object."""
        base = UnityYAMLDocument()
        base.add_object(_create_transform_object(100000))

        ours = UnityYAMLDocument()
        ours.add_object(_create_transform_object(100000))
        ours.add_object(_create_transform_object(200000))

        theirs = UnityYAMLDocument()
        theirs.add_object(_create_transform_object(100000))

        result = semantic_three_way_merge(base, ours, theirs)

        assert not result.has_conflicts
        # New object should be in merged
        assert result.merged_document.get_by_file_id(200000) is not None

    def test_object_deleted_by_theirs(self):
        """Test when theirs deletes an object."""
        base = UnityYAMLDocument()
        base.add_object(_create_transform_object(100000))
        base.add_object(_create_transform_object(200000))

        ours = UnityYAMLDocument()
        ours.add_object(_create_transform_object(100000))
        ours.add_object(_create_transform_object(200000))

        theirs = UnityYAMLDocument()
        theirs.add_object(_create_transform_object(100000))

        result = semantic_three_way_merge(base, ours, theirs)

        assert not result.has_conflicts
        # Deleted object should not be in merged
        assert result.merged_document.get_by_file_id(200000) is None

    def test_object_deleted_by_ours(self):
        """Test when ours deletes an object."""
        base = UnityYAMLDocument()
        base.add_object(_create_transform_object(100000))
        base.add_object(_create_transform_object(200000))

        ours = UnityYAMLDocument()
        ours.add_object(_create_transform_object(100000))

        theirs = UnityYAMLDocument()
        theirs.add_object(_create_transform_object(100000))
        theirs.add_object(_create_transform_object(200000))

        result = semantic_three_way_merge(base, ours, theirs)

        assert not result.has_conflicts
        # Deleted object should not be in merged
        assert result.merged_document.get_by_file_id(200000) is None

    def test_children_merge(self):
        """Test merging children lists."""
        base = UnityYAMLDocument()
        base.add_object(_create_transform_object(100000, children=[{"fileID": 200000}]))

        ours = UnityYAMLDocument()
        ours.add_object(_create_transform_object(100000, children=[{"fileID": 200000}, {"fileID": 300000}]))

        theirs = UnityYAMLDocument()
        theirs.add_object(_create_transform_object(100000, children=[{"fileID": 200000}, {"fileID": 400000}]))

        result = semantic_three_way_merge(base, ours, theirs)

        assert not result.has_conflicts
        # Both additions should be in merged
        merged_obj = result.merged_document.get_by_file_id(100000)
        assert merged_obj is not None
        content = merged_obj.get_content()
        children_ids = {c["fileID"] for c in content["m_Children"]}
        assert 200000 in children_ids
        assert 300000 in children_ids
        assert 400000 in children_ids


class TestApplyResolution:
    """Tests for the apply_resolution function."""

    def test_apply_ours(self):
        """Test applying 'ours' resolution."""
        doc = UnityYAMLDocument()
        doc.add_object(_create_transform_object(100000, position={"x": 5, "y": 0, "z": 0}))

        conflict = PropertyConflict(
            file_id=100000,
            class_name="Transform",
            property_path="m_LocalPosition.x",
            base_value=0,
            ours_value=5,
            theirs_value=10,
            conflict_type=ConflictType.BOTH_MODIFIED,
        )

        result = apply_resolution(doc, conflict, "ours")

        assert result
        obj = doc.get_by_file_id(100000)
        content = obj.get_content()
        assert content["m_LocalPosition"]["x"] == 5

    def test_apply_theirs(self):
        """Test applying 'theirs' resolution."""
        doc = UnityYAMLDocument()
        doc.add_object(_create_transform_object(100000, position={"x": 5, "y": 0, "z": 0}))

        conflict = PropertyConflict(
            file_id=100000,
            class_name="Transform",
            property_path="m_LocalPosition.x",
            base_value=0,
            ours_value=5,
            theirs_value=10,
            conflict_type=ConflictType.BOTH_MODIFIED,
        )

        result = apply_resolution(doc, conflict, "theirs")

        assert result
        obj = doc.get_by_file_id(100000)
        content = obj.get_content()
        assert content["m_LocalPosition"]["x"] == 10

    def test_apply_base(self):
        """Test applying 'base' resolution."""
        doc = UnityYAMLDocument()
        doc.add_object(_create_transform_object(100000, position={"x": 5, "y": 0, "z": 0}))

        conflict = PropertyConflict(
            file_id=100000,
            class_name="Transform",
            property_path="m_LocalPosition.x",
            base_value=0,
            ours_value=5,
            theirs_value=10,
            conflict_type=ConflictType.BOTH_MODIFIED,
        )

        result = apply_resolution(doc, conflict, "base")

        assert result
        obj = doc.get_by_file_id(100000)
        content = obj.get_content()
        assert content["m_LocalPosition"]["x"] == 0

    def test_apply_custom_value(self):
        """Test applying a custom value."""
        doc = UnityYAMLDocument()
        doc.add_object(_create_transform_object(100000, position={"x": 5, "y": 0, "z": 0}))

        conflict = PropertyConflict(
            file_id=100000,
            class_name="Transform",
            property_path="m_LocalPosition.x",
            base_value=0,
            ours_value=5,
            theirs_value=10,
            conflict_type=ConflictType.BOTH_MODIFIED,
        )

        result = apply_resolution(doc, conflict, 7.5)

        assert result
        obj = doc.get_by_file_id(100000)
        content = obj.get_content()
        assert content["m_LocalPosition"]["x"] == 7.5


class TestApplyAllResolutions:
    """Tests for the apply_all_resolutions function."""

    def test_apply_all_ours(self):
        """Test applying 'ours' to all conflicts."""
        doc = UnityYAMLDocument()
        doc.add_object(
            _create_transform_object(100000, position={"x": 5, "y": 5, "z": 5}, scale={"x": 2, "y": 2, "z": 2})
        )

        conflicts = [
            PropertyConflict(
                file_id=100000,
                class_name="Transform",
                property_path="m_LocalPosition.x",
                base_value=0,
                ours_value=5,
                theirs_value=10,
                conflict_type=ConflictType.BOTH_MODIFIED,
            ),
            PropertyConflict(
                file_id=100000,
                class_name="Transform",
                property_path="m_LocalScale.x",
                base_value=1,
                ours_value=2,
                theirs_value=3,
                conflict_type=ConflictType.BOTH_MODIFIED,
            ),
        ]

        resolved = apply_all_resolutions(doc, conflicts, "ours")

        assert resolved == 2
        obj = doc.get_by_file_id(100000)
        content = obj.get_content()
        assert content["m_LocalPosition"]["x"] == 5
        assert content["m_LocalScale"]["x"] == 2


class TestPropertyConflict:
    """Tests for the PropertyConflict dataclass."""

    def test_full_path(self):
        """Test full_path property."""
        conflict = PropertyConflict(
            file_id=100000,
            class_name="Transform",
            property_path="m_LocalPosition.x",
            base_value=0,
            ours_value=5,
            theirs_value=10,
            conflict_type=ConflictType.BOTH_MODIFIED,
        )

        assert conflict.full_path == "Transform.m_LocalPosition.x"

    def test_repr(self):
        """Test string representation."""
        conflict = PropertyConflict(
            file_id=100000,
            class_name="Transform",
            property_path="m_LocalPosition.x",
            base_value=0,
            ours_value=5,
            theirs_value=10,
            conflict_type=ConflictType.BOTH_MODIFIED,
        )

        repr_str = repr(conflict)
        assert "both_modified" in repr_str
        assert "Transform.m_LocalPosition.x" in repr_str


class TestSemanticMergeResult:
    """Tests for the SemanticMergeResult dataclass."""

    def test_has_conflicts(self):
        """Test has_conflicts property."""
        doc = UnityYAMLDocument()
        result_no_conflicts = SemanticMergeResult(merged_document=doc)
        assert not result_no_conflicts.has_conflicts

        result_with_conflicts = SemanticMergeResult(
            merged_document=doc,
            property_conflicts=[
                PropertyConflict(
                    file_id=1,
                    class_name="T",
                    property_path="x",
                    base_value=0,
                    ours_value=1,
                    theirs_value=2,
                    conflict_type=ConflictType.BOTH_MODIFIED,
                )
            ],
        )
        assert result_with_conflicts.has_conflicts

    def test_conflict_count(self):
        """Test conflict_count property."""
        doc = UnityYAMLDocument()
        result = SemanticMergeResult(
            merged_document=doc,
            property_conflicts=[
                PropertyConflict(
                    file_id=1,
                    class_name="T",
                    property_path="a",
                    base_value=0,
                    ours_value=1,
                    theirs_value=2,
                    conflict_type=ConflictType.BOTH_MODIFIED,
                ),
                PropertyConflict(
                    file_id=1,
                    class_name="T",
                    property_path="b",
                    base_value=0,
                    ours_value=1,
                    theirs_value=2,
                    conflict_type=ConflictType.BOTH_MODIFIED,
                ),
            ],
        )

        assert result.conflict_count == 2

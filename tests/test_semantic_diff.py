"""Tests for semantic diff functionality."""

from unityflow.parser import UnityYAMLDocument, UnityYAMLObject
from unityflow.semantic_diff import (
    ChangeType,
    ObjectChange,
    PropertyChange,
    SemanticDiffResult,
    semantic_diff,
)


def _create_transform_object(
    file_id: int,
    position: dict | None = None,
    rotation: dict | None = None,
    scale: dict | None = None,
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
                "m_Children": [],
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


class TestSemanticDiff:
    """Tests for the semantic_diff function."""

    def test_identical_documents(self):
        """Test diffing identical documents."""
        doc = UnityYAMLDocument()
        doc.add_object(_create_transform_object(100000))

        result = semantic_diff(doc, doc)

        assert not result.has_changes
        assert len(result.property_changes) == 0
        assert len(result.object_changes) == 0

    def test_position_change(self):
        """Test detecting position change."""
        left_doc = UnityYAMLDocument()
        left_doc.add_object(_create_transform_object(100000, position={"x": 0, "y": 0, "z": 0}))

        right_doc = UnityYAMLDocument()
        right_doc.add_object(_create_transform_object(100000, position={"x": 5, "y": 0, "z": 0}))

        result = semantic_diff(left_doc, right_doc)

        assert result.has_changes
        assert result.modified_count == 1
        assert len(result.property_changes) == 1

        change = result.property_changes[0]
        assert change.change_type == ChangeType.MODIFIED
        assert "m_LocalPosition" in change.property_path
        assert "x" in change.property_path
        assert change.old_value == 0
        assert change.new_value == 5

    def test_multiple_property_changes(self):
        """Test detecting multiple property changes."""
        left_doc = UnityYAMLDocument()
        left_doc.add_object(
            _create_transform_object(100000, position={"x": 0, "y": 0, "z": 0}, scale={"x": 1, "y": 1, "z": 1})
        )

        right_doc = UnityYAMLDocument()
        right_doc.add_object(
            _create_transform_object(100000, position={"x": 5, "y": 0, "z": 0}, scale={"x": 2, "y": 2, "z": 2})
        )

        result = semantic_diff(left_doc, right_doc)

        assert result.has_changes
        # position.x, scale.x, scale.y, scale.z changed
        assert result.modified_count >= 2

    def test_object_added(self):
        """Test detecting added object."""
        left_doc = UnityYAMLDocument()
        left_doc.add_object(_create_transform_object(100000))

        right_doc = UnityYAMLDocument()
        right_doc.add_object(_create_transform_object(100000))
        right_doc.add_object(_create_transform_object(200000))

        result = semantic_diff(left_doc, right_doc)

        assert result.has_changes
        assert result.added_count >= 1

        # Find the added object change
        added_objects = [c for c in result.object_changes if c.change_type == ChangeType.ADDED]
        assert len(added_objects) == 1
        assert added_objects[0].file_id == 200000

    def test_object_removed(self):
        """Test detecting removed object."""
        left_doc = UnityYAMLDocument()
        left_doc.add_object(_create_transform_object(100000))
        left_doc.add_object(_create_transform_object(200000))

        right_doc = UnityYAMLDocument()
        right_doc.add_object(_create_transform_object(100000))

        result = semantic_diff(left_doc, right_doc)

        assert result.has_changes
        assert result.removed_count >= 1

        # Find the removed object change
        removed_objects = [c for c in result.object_changes if c.change_type == ChangeType.REMOVED]
        assert len(removed_objects) == 1
        assert removed_objects[0].file_id == 200000

    def test_children_added(self):
        """Test detecting added children references."""
        left_doc = UnityYAMLDocument()
        left_obj = _create_transform_object(100000)
        left_obj.data["Transform"]["m_Children"] = [{"fileID": 200000}]
        left_doc.add_object(left_obj)

        right_doc = UnityYAMLDocument()
        right_obj = _create_transform_object(100000)
        right_obj.data["Transform"]["m_Children"] = [{"fileID": 200000}, {"fileID": 300000}]
        right_doc.add_object(right_obj)

        result = semantic_diff(left_doc, right_doc)

        assert result.has_changes
        # Should detect the added child reference
        children_changes = [c for c in result.property_changes if "m_Children" in c.property_path]
        assert len(children_changes) == 1
        assert children_changes[0].change_type == ChangeType.ADDED
        assert children_changes[0].new_value == {"fileID": 300000}

    def test_children_removed(self):
        """Test detecting removed children references."""
        left_doc = UnityYAMLDocument()
        left_obj = _create_transform_object(100000)
        left_obj.data["Transform"]["m_Children"] = [{"fileID": 200000}, {"fileID": 300000}]
        left_doc.add_object(left_obj)

        right_doc = UnityYAMLDocument()
        right_obj = _create_transform_object(100000)
        right_obj.data["Transform"]["m_Children"] = [{"fileID": 200000}]
        right_doc.add_object(right_obj)

        result = semantic_diff(left_doc, right_doc)

        assert result.has_changes
        # Should detect the removed child reference
        children_changes = [c for c in result.property_changes if "m_Children" in c.property_path]
        assert len(children_changes) == 1
        assert children_changes[0].change_type == ChangeType.REMOVED

    def test_get_changes_for_object(self):
        """Test filtering changes by object."""
        left_doc = UnityYAMLDocument()
        left_doc.add_object(_create_transform_object(100000, position={"x": 0, "y": 0, "z": 0}))
        left_doc.add_object(_create_transform_object(200000, position={"x": 0, "y": 0, "z": 0}))

        right_doc = UnityYAMLDocument()
        right_doc.add_object(_create_transform_object(100000, position={"x": 5, "y": 0, "z": 0}))
        right_doc.add_object(_create_transform_object(200000, position={"x": 10, "y": 0, "z": 0}))

        result = semantic_diff(left_doc, right_doc)

        changes_100000 = result.get_changes_for_object(100000)
        changes_200000 = result.get_changes_for_object(200000)

        assert len(changes_100000) == 1
        assert changes_100000[0].new_value == 5

        assert len(changes_200000) == 1
        assert changes_200000[0].new_value == 10


class TestPropertyChange:
    """Tests for the PropertyChange dataclass."""

    def test_full_path(self):
        """Test full_path property."""
        change = PropertyChange(
            file_id=100000,
            class_name="Transform",
            property_path="m_LocalPosition.x",
            change_type=ChangeType.MODIFIED,
            old_value=0,
            new_value=5,
        )

        assert change.full_path == "Transform.m_LocalPosition.x"

    def test_repr(self):
        """Test string representation."""
        change = PropertyChange(
            file_id=100000,
            class_name="Transform",
            property_path="m_LocalPosition.x",
            change_type=ChangeType.MODIFIED,
            old_value=0,
            new_value=5,
        )

        repr_str = repr(change)
        assert "modified" in repr_str
        assert "Transform.m_LocalPosition.x" in repr_str


class TestSemanticDiffResult:
    """Tests for the SemanticDiffResult dataclass."""

    def test_counts(self):
        """Test count properties."""
        result = SemanticDiffResult(
            property_changes=[
                PropertyChange(
                    file_id=1,
                    class_name="T",
                    property_path="a",
                    change_type=ChangeType.ADDED,
                    old_value=None,
                    new_value=1,
                ),
                PropertyChange(
                    file_id=1,
                    class_name="T",
                    property_path="b",
                    change_type=ChangeType.REMOVED,
                    old_value=1,
                    new_value=None,
                ),
                PropertyChange(
                    file_id=1,
                    class_name="T",
                    property_path="c",
                    change_type=ChangeType.MODIFIED,
                    old_value=1,
                    new_value=2,
                ),
            ],
            object_changes=[
                ObjectChange(
                    file_id=2,
                    class_name="Transform",
                    change_type=ChangeType.ADDED,
                ),
            ],
        )

        assert result.added_count == 2  # 1 property + 1 object
        assert result.removed_count == 1
        assert result.modified_count == 1
        assert result.has_changes

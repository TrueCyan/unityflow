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


def _build_hierarchy_doc(
    go_file_id: int,
    transform_file_id: int,
    name: str,
    position: dict | None = None,
    components: list[tuple[int, int, str, dict]] | None = None,
    children: list[dict] | None = None,
    parent_transform_id: int = 0,
) -> list[UnityYAMLObject]:
    component_entries = [{"component": {"fileID": transform_file_id}}]
    if components:
        for comp_file_id, _class_id, _class_name, _data in components:
            component_entries.append({"component": {"fileID": comp_file_id}})

    go = UnityYAMLObject(
        class_id=1,
        file_id=go_file_id,
        data={
            "GameObject": {
                "m_Name": name,
                "m_Layer": 0,
                "m_IsActive": 1,
                "m_Component": component_entries,
            }
        },
    )

    transform = UnityYAMLObject(
        class_id=4,
        file_id=transform_file_id,
        data={
            "Transform": {
                "m_GameObject": {"fileID": go_file_id},
                "m_LocalPosition": position or {"x": 0, "y": 0, "z": 0},
                "m_LocalRotation": {"x": 0, "y": 0, "z": 0, "w": 1},
                "m_LocalScale": {"x": 1, "y": 1, "z": 1},
                "m_Children": [{"fileID": c["transform_file_id"]} for c in (children or [])],
                "m_Father": {"fileID": parent_transform_id},
            }
        },
    )

    objs = [go, transform]
    if components:
        for comp_file_id, class_id, class_name, data in components:
            comp_data = dict(data)
            comp_data["m_GameObject"] = {"fileID": go_file_id}
            objs.append(
                UnityYAMLObject(
                    class_id=class_id,
                    file_id=comp_file_id,
                    data={class_name: comp_data},
                )
            )
    return objs


def _create_prefab_instance(file_id: int, modifications: list) -> UnityYAMLObject:
    return UnityYAMLObject(
        class_id=1001,
        file_id=file_id,
        data={
            "PrefabInstance": {
                "m_Modification": {
                    "m_Modifications": modifications,
                    "m_RemovedComponents": [],
                }
            }
        },
    )


class TestModificationListDiff:

    def test_identical_modifications_no_changes(self):
        mods = [
            {"target": {"fileID": 100}, "propertyPath": "m_Name", "value": "A", "objectReference": {"fileID": 0}},
        ]
        left_doc = UnityYAMLDocument()
        left_doc.add_object(_create_prefab_instance(1000, list(mods)))
        right_doc = UnityYAMLDocument()
        right_doc.add_object(_create_prefab_instance(1000, list(mods)))

        result = semantic_diff(left_doc, right_doc)
        assert not result.has_changes

    def test_modification_added(self):
        base_mods = [
            {"target": {"fileID": 100}, "propertyPath": "m_Name", "value": "A", "objectReference": {"fileID": 0}},
        ]
        new_mods = list(base_mods) + [
            {"target": {"fileID": 200}, "propertyPath": "m_Enabled", "value": "1", "objectReference": {"fileID": 0}},
        ]
        left_doc = UnityYAMLDocument()
        left_doc.add_object(_create_prefab_instance(1000, base_mods))
        right_doc = UnityYAMLDocument()
        right_doc.add_object(_create_prefab_instance(1000, new_mods))

        result = semantic_diff(left_doc, right_doc)
        assert result.has_changes
        added = [c for c in result.property_changes if c.change_type == ChangeType.ADDED]
        assert len(added) == 1
        assert "fileID=200" in added[0].property_path

    def test_modification_removed(self):
        old_mods = [
            {"target": {"fileID": 100}, "propertyPath": "m_Name", "value": "A", "objectReference": {"fileID": 0}},
            {"target": {"fileID": 200}, "propertyPath": "m_Enabled", "value": "1", "objectReference": {"fileID": 0}},
        ]
        new_mods = [
            {"target": {"fileID": 100}, "propertyPath": "m_Name", "value": "A", "objectReference": {"fileID": 0}},
        ]
        left_doc = UnityYAMLDocument()
        left_doc.add_object(_create_prefab_instance(1000, old_mods))
        right_doc = UnityYAMLDocument()
        right_doc.add_object(_create_prefab_instance(1000, new_mods))

        result = semantic_diff(left_doc, right_doc)
        assert result.has_changes
        removed = [c for c in result.property_changes if c.change_type == ChangeType.REMOVED]
        assert len(removed) == 1

    def test_modification_value_changed(self):
        old_mods = [
            {"target": {"fileID": 100}, "propertyPath": "m_Name", "value": "A", "objectReference": {"fileID": 0}},
        ]
        new_mods = [
            {"target": {"fileID": 100}, "propertyPath": "m_Name", "value": "B", "objectReference": {"fileID": 0}},
        ]
        left_doc = UnityYAMLDocument()
        left_doc.add_object(_create_prefab_instance(1000, old_mods))
        right_doc = UnityYAMLDocument()
        right_doc.add_object(_create_prefab_instance(1000, new_mods))

        result = semantic_diff(left_doc, right_doc)
        assert result.has_changes
        modified = [c for c in result.property_changes if c.change_type == ChangeType.MODIFIED]
        assert len(modified) == 1

    def test_reordered_modifications_no_false_positive(self):
        mod_a = {"target": {"fileID": 100}, "propertyPath": "m_Name", "value": "A", "objectReference": {"fileID": 0}}
        mod_b = {"target": {"fileID": 200}, "propertyPath": "m_Enabled", "value": "1", "objectReference": {"fileID": 0}}

        left_doc = UnityYAMLDocument()
        left_doc.add_object(_create_prefab_instance(1000, [mod_a, mod_b]))
        right_doc = UnityYAMLDocument()
        right_doc.add_object(_create_prefab_instance(1000, [mod_b, mod_a]))

        result = semantic_diff(left_doc, right_doc)
        assert not result.has_changes


class TestHierarchyMatching:

    def test_matching_by_hierarchy_path(self):
        left_doc = UnityYAMLDocument()
        for obj in _build_hierarchy_doc(100, 101, "Root", position={"x": 0, "y": 0, "z": 0}):
            left_doc.add_object(obj)

        right_doc = UnityYAMLDocument()
        for obj in _build_hierarchy_doc(900, 901, "Root", position={"x": 5, "y": 0, "z": 0}):
            right_doc.add_object(obj)

        result = semantic_diff(left_doc, right_doc)

        assert len(result.object_changes) == 0
        modified = [c for c in result.property_changes if c.change_type == ChangeType.MODIFIED]
        assert len(modified) == 1
        assert modified[0].property_path == "m_LocalPosition.x"
        assert modified[0].old_value == 0
        assert modified[0].new_value == 5

    def test_component_index_differentiation(self):
        left_doc = UnityYAMLDocument()
        for obj in _build_hierarchy_doc(
            100,
            101,
            "Root",
            components=[
                (102, 212, "SpriteRenderer", {"m_Color": {"r": 1, "g": 1, "b": 1, "a": 1}}),
                (103, 212, "SpriteRenderer", {"m_Color": {"r": 0, "g": 0, "b": 0, "a": 1}}),
            ],
        ):
            left_doc.add_object(obj)

        right_doc = UnityYAMLDocument()
        for obj in _build_hierarchy_doc(
            200,
            201,
            "Root",
            components=[
                (202, 212, "SpriteRenderer", {"m_Color": {"r": 1, "g": 1, "b": 1, "a": 1}}),
                (203, 212, "SpriteRenderer", {"m_Color": {"r": 1, "g": 0, "b": 0, "a": 1}}),
            ],
        ):
            right_doc.add_object(obj)

        result = semantic_diff(left_doc, right_doc)

        assert len(result.object_changes) == 0
        modified = [c for c in result.property_changes if c.change_type == ChangeType.MODIFIED]
        assert len(modified) == 1
        assert modified[0].property_path == "m_Color.r"
        assert modified[0].old_value == 0
        assert modified[0].new_value == 1

    def test_hierarchy_path_populated(self):
        left_doc = UnityYAMLDocument()
        root_objs = _build_hierarchy_doc(100, 101, "Root", children=[{"transform_file_id": 201}])
        child_objs = _build_hierarchy_doc(200, 201, "Child", position={"x": 0, "y": 0, "z": 0}, parent_transform_id=101)
        for obj in root_objs + child_objs:
            left_doc.add_object(obj)

        right_doc = UnityYAMLDocument()
        root_objs_r = _build_hierarchy_doc(100, 101, "Root", children=[{"transform_file_id": 201}])
        child_objs_r = _build_hierarchy_doc(
            200, 201, "Child", position={"x": 3, "y": 0, "z": 0}, parent_transform_id=101
        )
        for obj in root_objs_r + child_objs_r:
            right_doc.add_object(obj)

        result = semantic_diff(left_doc, right_doc)

        assert len(result.property_changes) == 1
        assert result.property_changes[0].hierarchy_path == "Root/Child"

    def test_added_removed_objects(self):
        left_doc = UnityYAMLDocument()
        for obj in _build_hierarchy_doc(100, 101, "Root"):
            left_doc.add_object(obj)

        right_doc = UnityYAMLDocument()
        for obj in _build_hierarchy_doc(200, 201, "Other"):
            right_doc.add_object(obj)

        result = semantic_diff(left_doc, right_doc)

        removed = [c for c in result.object_changes if c.change_type == ChangeType.REMOVED]
        added = [c for c in result.object_changes if c.change_type == ChangeType.ADDED]
        assert len(removed) >= 1
        assert len(added) >= 1
        assert any(c.hierarchy_path == "Root" for c in removed)
        assert any(c.hierarchy_path == "Other" for c in added)

    def test_different_script_guid_not_matched(self):
        left_doc = UnityYAMLDocument()
        for obj in _build_hierarchy_doc(
            100,
            101,
            "Root",
            components=[
                (
                    102,
                    114,
                    "MonoBehaviour",
                    {
                        "m_Script": {"fileID": 11500000, "guid": "guid_aaaa", "type": 3},
                        "m_Enabled": 1,
                    },
                ),
            ],
        ):
            left_doc.add_object(obj)

        right_doc = UnityYAMLDocument()
        for obj in _build_hierarchy_doc(
            200,
            201,
            "Root",
            components=[
                (
                    202,
                    114,
                    "MonoBehaviour",
                    {
                        "m_Script": {"fileID": 11500000, "guid": "guid_bbbb", "type": 3},
                        "m_Enabled": 1,
                    },
                ),
            ],
        ):
            right_doc.add_object(obj)

        result = semantic_diff(left_doc, right_doc)

        mono_added = [
            c for c in result.object_changes if c.change_type == ChangeType.ADDED and c.class_name == "MonoBehaviour"
        ]
        mono_removed = [
            c for c in result.object_changes if c.change_type == ChangeType.REMOVED and c.class_name == "MonoBehaviour"
        ]
        assert len(mono_added) == 1
        assert len(mono_removed) == 1

    def test_same_script_guid_matched(self):
        left_doc = UnityYAMLDocument()
        for obj in _build_hierarchy_doc(
            100,
            101,
            "Root",
            components=[
                (
                    102,
                    114,
                    "MonoBehaviour",
                    {
                        "m_Script": {"fileID": 11500000, "guid": "guid_same", "type": 3},
                        "m_Enabled": 1,
                        "m_Health": 50,
                    },
                ),
            ],
        ):
            left_doc.add_object(obj)

        right_doc = UnityYAMLDocument()
        for obj in _build_hierarchy_doc(
            200,
            201,
            "Root",
            components=[
                (
                    202,
                    114,
                    "MonoBehaviour",
                    {
                        "m_Script": {"fileID": 11500000, "guid": "guid_same", "type": 3},
                        "m_Enabled": 1,
                        "m_Health": 100,
                    },
                ),
            ],
        ):
            right_doc.add_object(obj)

        result = semantic_diff(left_doc, right_doc)

        mono_changes = [c for c in result.object_changes if c.class_name == "MonoBehaviour"]
        assert len(mono_changes) == 0

        modified = [c for c in result.property_changes if c.change_type == ChangeType.MODIFIED]
        health_changes = [c for c in modified if "m_Health" in c.property_path]
        assert len(health_changes) == 1
        assert health_changes[0].old_value == 50
        assert health_changes[0].new_value == 100

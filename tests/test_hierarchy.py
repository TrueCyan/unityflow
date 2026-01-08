"""Tests for the hierarchy module."""

from pathlib import Path

from unityflow.hierarchy import (
    ComponentInfo,
    Hierarchy,
    HierarchyNode,
    build_hierarchy,
    get_prefab_instance_for_stripped,
    get_stripped_objects_for_prefab,
    resolve_game_object_for_component,
)
from unityflow.parser import UnityYAMLDocument

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestHierarchyBuild:
    """Test building hierarchy from documents."""

    def test_build_hierarchy_basic_prefab(self):
        """Test building hierarchy from a basic prefab."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")
        hierarchy = build_hierarchy(doc)

        assert hierarchy is not None
        assert len(hierarchy.root_objects) >= 1

    def test_build_hierarchy_nested_prefab(self):
        """Test building hierarchy from a nested prefab."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
        hierarchy = build_hierarchy(doc)

        assert hierarchy is not None
        # Should have root objects
        assert len(hierarchy.root_objects) >= 1

        # Find PrefabInstance nodes
        prefab_instances = [node for node in hierarchy.iter_all() if node.is_prefab_instance]
        assert len(prefab_instances) >= 1

    def test_hierarchy_indexes_stripped_objects(self):
        """Test that stripped objects are properly indexed."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
        hierarchy = build_hierarchy(doc)

        # Check stripped transforms index
        assert len(hierarchy._stripped_transforms) >= 1

        # Check stripped game objects index
        assert len(hierarchy._stripped_game_objects) >= 1

        # Check prefab instances index
        assert len(hierarchy._prefab_instances) >= 1


class TestHierarchyNavigation:
    """Test hierarchy navigation methods."""

    def test_find_by_path(self):
        """Test finding nodes by path."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
        hierarchy = build_hierarchy(doc)

        # Find root by name
        root = hierarchy.find("RootCanvas")
        assert root is not None
        assert root.name == "RootCanvas"

    def test_find_nested_path(self):
        """Test finding nested nodes by path."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
        hierarchy = build_hierarchy(doc)

        root = hierarchy.find("RootCanvas")
        if root and root.children:
            # Should have PrefabInstance as child
            child = root.children[0]
            assert child.is_prefab_instance

    def test_get_by_file_id(self):
        """Test getting node by fileID."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
        hierarchy = build_hierarchy(doc)

        # Get root node by file ID
        node = hierarchy.get_by_file_id(100000)
        assert node is not None
        assert node.name == "RootCanvas"

    def test_iter_all(self):
        """Test iterating over all nodes."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
        hierarchy = build_hierarchy(doc)

        nodes = list(hierarchy.iter_all())
        assert len(nodes) >= 1

    def test_iter_descendants(self):
        """Test iterating over descendants."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
        hierarchy = build_hierarchy(doc)

        root = hierarchy.find("RootCanvas")
        if root:
            descendants = list(root.iter_descendants())
            # Should have at least the PrefabInstance children
            assert len(descendants) >= 1


class TestHierarchyNodeProperties:
    """Test HierarchyNode properties."""

    def test_node_path_property(self):
        """Test the path property of nodes."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
        hierarchy = build_hierarchy(doc)

        root = hierarchy.find("RootCanvas")
        assert root is not None
        assert root.path == "RootCanvas"

        if root.children:
            child = root.children[0]
            assert child.path.startswith("RootCanvas/")

    def test_node_is_ui(self):
        """Test is_ui property detection."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
        hierarchy = build_hierarchy(doc)

        root = hierarchy.find("RootCanvas")
        if root:
            # RootCanvas uses RectTransform (class_id 224)
            assert root.is_ui

    def test_get_component(self):
        """Test getting components from a node."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
        hierarchy = build_hierarchy(doc)

        root = hierarchy.find("RootCanvas")
        if root:
            # Should have MonoBehaviour component
            mono = root.get_component("MonoBehaviour")
            assert mono is not None
            assert mono.class_id == 114

    def test_get_components(self):
        """Test getting all components from a node."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
        hierarchy = build_hierarchy(doc)

        root = hierarchy.find("RootCanvas")
        if root:
            all_components = root.get_components()
            assert len(all_components) >= 1


class TestPrefabInstanceNode:
    """Test PrefabInstance-specific functionality."""

    def test_prefab_instance_source_guid(self):
        """Test source_guid property."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
        hierarchy = build_hierarchy(doc)

        prefab_instances = [node for node in hierarchy.iter_all() if node.is_prefab_instance]
        assert len(prefab_instances) >= 1

        instance = prefab_instances[0]
        assert instance.source_guid != ""

    def test_prefab_instance_modifications(self):
        """Test modifications list."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
        hierarchy = build_hierarchy(doc)

        prefab_instances = [node for node in hierarchy.iter_all() if node.is_prefab_instance]
        if prefab_instances:
            instance = prefab_instances[0]
            # Should have modifications (position, name)
            assert len(instance.modifications) >= 1


class TestReferenceResolution:
    """Test reference resolution utilities."""

    def test_get_prefab_instance_for_stripped_transform(self):
        """Test resolving stripped transform to PrefabInstance."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
        hierarchy = build_hierarchy(doc)

        # Get a stripped transform ID
        if hierarchy._stripped_transforms:
            stripped_id = list(hierarchy._stripped_transforms.keys())[0]
            prefab_id = hierarchy.get_prefab_instance_for(stripped_id)
            assert prefab_id != 0

    def test_get_prefab_instance_for_stripped_gameobject(self):
        """Test resolving stripped GameObject to PrefabInstance."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
        hierarchy = build_hierarchy(doc)

        # Get a stripped GameObject ID
        if hierarchy._stripped_game_objects:
            stripped_id = list(hierarchy._stripped_game_objects.keys())[0]
            prefab_id = hierarchy.get_prefab_instance_for(stripped_id)
            assert prefab_id != 0

    def test_get_stripped_objects_for_prefab(self):
        """Test getting stripped objects for a PrefabInstance."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
        hierarchy = build_hierarchy(doc)

        if hierarchy._prefab_instances:
            prefab_id = list(hierarchy._prefab_instances.keys())[0]
            stripped_ids = hierarchy.get_stripped_objects_for(prefab_id)
            assert len(stripped_ids) >= 1

    def test_resolve_game_object(self):
        """Test resolving fileID to HierarchyNode."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
        hierarchy = build_hierarchy(doc)

        # Resolve regular GameObject
        node = hierarchy.resolve_game_object(100000)
        assert node is not None
        assert node.name == "RootCanvas"

        # Resolve stripped object -> should return PrefabInstance
        if hierarchy._stripped_transforms:
            stripped_id = list(hierarchy._stripped_transforms.keys())[0]
            resolved = hierarchy.resolve_game_object(stripped_id)
            assert resolved is not None
            assert resolved.is_prefab_instance


class TestStandaloneFunctions:
    """Test standalone utility functions."""

    def test_resolve_game_object_for_component(self):
        """Test resolving component to GameObject."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")

        # MonoBehaviour component ID 114000
        go_id = resolve_game_object_for_component(doc, 114000)
        assert go_id == 100000

    def test_resolve_game_object_for_component_on_stripped(self):
        """Test resolving component on stripped GameObject."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")

        # CanvasRenderer component on stripped GO
        go_id = resolve_game_object_for_component(doc, 2745004045164926116)
        # Should return PrefabInstance ID, not stripped GO ID
        assert go_id != 0
        obj = doc.get_by_file_id(go_id)
        if obj:
            assert obj.class_id == 1001  # PrefabInstance

    def test_get_prefab_instance_for_stripped(self):
        """Test standalone get_prefab_instance_for_stripped."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")

        # Stripped transform ID from fixture
        prefab_id = get_prefab_instance_for_stripped(doc, 603920067861314518)
        assert prefab_id == 7876467245726119373

    def test_get_stripped_objects_for_prefab_standalone(self):
        """Test standalone get_stripped_objects_for_prefab."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")

        # PrefabInstance ID from fixture
        stripped_ids = get_stripped_objects_for_prefab(doc, 7876467245726119373)
        assert len(stripped_ids) >= 2  # At least transform and gameobject


class TestAddPrefabInstance:
    """Test adding new PrefabInstances."""

    def test_add_prefab_instance_to_root(self):
        """Test adding a PrefabInstance at root level."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
        hierarchy = build_hierarchy(doc)

        initial_count = len(hierarchy.root_objects)

        node = hierarchy.add_prefab_instance(
            source_guid="test_guid_12345678901234567890",
            name="TestPrefab",
            source_root_transform_id=12345,
            source_root_go_id=67890,
        )

        assert node is not None
        assert node.is_prefab_instance
        assert node.name == "TestPrefab"
        assert node.source_guid == "test_guid_12345678901234567890"
        assert len(hierarchy.root_objects) == initial_count + 1

    def test_add_prefab_instance_with_parent(self):
        """Test adding a PrefabInstance with a parent."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
        hierarchy = build_hierarchy(doc)

        root = hierarchy.find("RootCanvas")
        assert root is not None

        initial_children = len(root.children)

        node = hierarchy.add_prefab_instance(
            source_guid="child_guid_12345678901234567890",
            parent=root,
            name="ChildPrefab",
            position=(100, 50, 0),
            source_root_transform_id=11111,
            source_root_go_id=22222,
            is_ui=True,
        )

        assert node is not None
        assert node.parent == root
        assert len(root.children) == initial_children + 1
        assert node.is_ui

    def test_add_prefab_instance_creates_stripped_objects(self):
        """Test that adding PrefabInstance creates stripped objects."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
        hierarchy = build_hierarchy(doc)

        initial_stripped_count = len(hierarchy._stripped_transforms)

        node = hierarchy.add_prefab_instance(
            source_guid="new_guid_12345678901234567890",
            name="NewPrefab",
            source_root_transform_id=99999,
            source_root_go_id=88888,
        )

        assert node is not None
        assert len(hierarchy._stripped_transforms) == initial_stripped_count + 1

    def test_add_prefab_instance_updates_document(self):
        """Test that adding PrefabInstance updates the document."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
        hierarchy = build_hierarchy(doc)

        initial_object_count = len(doc.objects)

        node = hierarchy.add_prefab_instance(
            source_guid="doc_test_guid_12345678901234567890",
            name="DocTestPrefab",
            source_root_transform_id=77777,
            source_root_go_id=66666,
        )

        # Should add: PrefabInstance, stripped Transform, stripped GameObject
        assert len(doc.objects) == initial_object_count + 3

        # Verify PrefabInstance was added
        prefab_obj = doc.get_by_file_id(node.file_id)
        assert prefab_obj is not None
        assert prefab_obj.class_id == 1001


class TestSetProperty:
    """Test setting properties on hierarchy nodes."""

    def test_set_property_on_regular_node(self):
        """Test setting property on a regular GameObject."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
        hierarchy = build_hierarchy(doc)

        root = hierarchy.find("RootCanvas")
        assert root is not None

        result = root.set_property("m_Name", "NewName")
        assert result is True

        # Verify change in document
        obj = doc.get_by_file_id(root.file_id)
        content = obj.get_content()
        assert content["m_Name"] == "NewName"

    def test_get_property(self):
        """Test getting property from a node."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
        hierarchy = build_hierarchy(doc)

        root = hierarchy.find("RootCanvas")
        assert root is not None

        name = root.get_property("m_Name")
        assert name == "RootCanvas"

    def test_get_property_returns_modified_value_for_prefab_instance(self):
        """Test that get_property returns modified value for PrefabInstance."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
        hierarchy = build_hierarchy(doc)

        # Find PrefabInstance node
        prefab_instances = [node for node in hierarchy.iter_all() if node.is_prefab_instance]
        assert len(prefab_instances) >= 1

        instance = prefab_instances[0]
        # The name should be from modifications (set in the prefab)
        name = instance.get_property("m_Name")
        assert name is not None
        # Name should be "MyButton" from modifications in nested_prefab.prefab
        assert name == "MyButton"

        # Also test position values from modifications
        pos_x = instance.get_property("m_AnchoredPosition.x")
        assert pos_x == 100
        pos_y = instance.get_property("m_AnchoredPosition.y")
        assert pos_y == 50

    def test_set_property_get_property_consistency_for_prefab_instance(self):
        """Test that get_property returns value set by set_property for PrefabInstance."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
        hierarchy = build_hierarchy(doc)

        # Find PrefabInstance node
        prefab_instances = [node for node in hierarchy.iter_all() if node.is_prefab_instance]
        assert len(prefab_instances) >= 1

        instance = prefab_instances[0]

        # Set a new property value
        result = instance.set_property("m_LocalPosition.x", 100)
        assert result is True

        # get_property should return the same value
        value = instance.get_property("m_LocalPosition.x")
        assert value == 100

        # Set existing property to a new value
        result = instance.set_property("m_Name", "NewBoardName")
        assert result is True

        # get_property should return the updated value
        name = instance.get_property("m_Name")
        assert name == "NewBoardName"

    def test_get_property_returns_transform_properties(self):
        """Test that get_property can access Transform/RectTransform properties."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
        hierarchy = build_hierarchy(doc)

        root = hierarchy.find("RootCanvas")
        assert root is not None
        assert root.is_ui is True

        # RectTransform properties should be accessible
        anchored_pos = root.get_property("m_AnchoredPosition")
        assert anchored_pos == {"x": 0, "y": 0}

        size_delta = root.get_property("m_SizeDelta")
        assert size_delta == {"x": 0, "y": 0}

        local_pos = root.get_property("m_LocalPosition")
        assert local_pos == {"x": 0, "y": 0, "z": 0}

    def test_prefab_instance_is_ui_detection(self):
        """Test that PrefabInstance nodes correctly detect is_ui from stripped RectTransform."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
        hierarchy = build_hierarchy(doc)

        # Find PrefabInstance nodes
        prefab_instances = [node for node in hierarchy.iter_all() if node.is_prefab_instance]
        assert len(prefab_instances) >= 1

        # All PrefabInstances in nested_prefab.prefab use RectTransform
        for instance in prefab_instances:
            assert instance.is_ui is True, f"{instance.name} should have is_ui=True"

    def test_get_property_rect_transform_from_modifications(self):
        """Test that PrefabInstance RectTransform values come from modifications."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
        hierarchy = build_hierarchy(doc)

        # Find first PrefabInstance (MyButton)
        prefab_instances = [node for node in hierarchy.iter_all() if node.is_prefab_instance]
        instance = prefab_instances[0]

        # These values are set in modifications
        pos_x = instance.get_property("m_AnchoredPosition.x")
        pos_y = instance.get_property("m_AnchoredPosition.y")
        assert pos_x == 100
        assert pos_y == 50


class TestHierarchyClass:
    """Test Hierarchy class methods."""

    def test_hierarchy_build_classmethod(self):
        """Test Hierarchy.build() classmethod."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
        hierarchy = Hierarchy.build(doc)

        assert isinstance(hierarchy, Hierarchy)
        assert hierarchy._document is doc


class TestComponentInfo:
    """Test ComponentInfo dataclass."""

    def test_component_info_creation(self):
        """Test creating ComponentInfo."""
        info = ComponentInfo(
            file_id=12345,
            class_id=114,
            class_name="MonoBehaviour",
            data={"m_Enabled": 1},
        )

        assert info.file_id == 12345
        assert info.class_id == 114
        assert info.type_name == "MonoBehaviour"
        assert info.is_on_stripped_object is False

    def test_component_info_on_stripped(self):
        """Test ComponentInfo on stripped object."""
        info = ComponentInfo(
            file_id=12345,
            class_id=222,
            class_name="CanvasRenderer",
            data={},
            is_on_stripped_object=True,
        )

        assert info.is_on_stripped_object is True

    def test_component_info_modifications_field(self):
        """Test ComponentInfo with modifications field."""
        modifications = [
            {
                "target": {"fileID": 12345, "guid": "test_guid"},
                "propertyPath": "m_Enabled",
                "value": 0,
                "objectReference": {"fileID": 0},
            }
        ]
        info = ComponentInfo(
            file_id=12345,
            class_id=114,
            class_name="MonoBehaviour",
            data={"m_Enabled": 1},
            modifications=modifications,
        )

        assert info.modifications is not None
        assert len(info.modifications) == 1
        assert info.modifications[0]["propertyPath"] == "m_Enabled"

    def test_component_info_get_effective_property_with_modification(self):
        """Test get_effective_property returns modified value."""
        modifications = [
            {
                "target": {"fileID": 12345, "guid": "test_guid"},
                "propertyPath": "m_Enabled",
                "value": 0,
                "objectReference": {"fileID": 0},
            }
        ]
        info = ComponentInfo(
            file_id=12345,
            class_id=114,
            class_name="MonoBehaviour",
            data={"m_Enabled": 1, "m_Script": {"fileID": 11500000}},
            modifications=modifications,
        )

        # Modified property should return modified value
        assert info.get_effective_property("m_Enabled") == 0

        # Non-modified property should return original value
        script = info.get_effective_property("m_Script")
        assert script == {"fileID": 11500000}

    def test_component_info_get_effective_property_without_modification(self):
        """Test get_effective_property returns original value when no modifications."""
        info = ComponentInfo(
            file_id=12345,
            class_id=114,
            class_name="MonoBehaviour",
            data={"m_Enabled": 1, "m_Color": {"r": 1, "g": 0.5}},
            modifications=None,
        )

        assert info.get_effective_property("m_Enabled") == 1
        assert info.get_effective_property("m_Color.r") == 1

    def test_component_info_get_effective_property_with_object_reference(self):
        """Test get_effective_property returns objectReference when fileID is set."""
        modifications = [
            {
                "target": {"fileID": 12345, "guid": "test_guid"},
                "propertyPath": "m_Target",
                "value": "",
                "objectReference": {"fileID": 67890},
            }
        ]
        info = ComponentInfo(
            file_id=12345,
            class_id=114,
            class_name="MonoBehaviour",
            data={"m_Target": {"fileID": 0}},
            modifications=modifications,
        )

        # Should return objectReference when it has a fileID
        target = info.get_effective_property("m_Target")
        assert target == {"fileID": 67890}


class TestLLMFriendlyAPI:
    """Test LLM-friendly API features."""

    def test_component_info_script_fields(self):
        """Test ComponentInfo with script_guid and script_name."""
        info = ComponentInfo(
            file_id=12345,
            class_id=114,
            class_name="MonoBehaviour",
            data={"m_Script": {"fileID": 11500000, "guid": "test_guid"}},
            script_guid="test_guid",
            script_name="PlayerController",
        )

        assert info.script_guid == "test_guid"
        assert info.script_name == "PlayerController"
        # type_name should return script_name for MonoBehaviour
        assert info.type_name == "PlayerController"

    def test_component_info_type_name_fallback(self):
        """Test type_name falls back to class_name when no script_name."""
        info = ComponentInfo(
            file_id=12345,
            class_id=114,
            class_name="MonoBehaviour",
            data={},
            script_guid="test_guid",
            script_name=None,  # No resolved name
        )

        assert info.type_name == "MonoBehaviour"

    def test_hierarchy_node_nested_prefab_fields(self):
        """Test HierarchyNode nested prefab fields."""
        node = HierarchyNode(
            file_id=12345,
            name="TestNode",
            transform_id=67890,
            is_prefab_instance=True,
            source_guid="source_guid_123",
        )

        assert node.is_from_nested_prefab is False
        assert node.nested_prefab_loaded is False

    def test_hierarchy_node_from_nested_prefab(self):
        """Test HierarchyNode marked as from nested prefab."""
        node = HierarchyNode(
            file_id=12345,
            name="NestedChild",
            transform_id=67890,
            is_from_nested_prefab=True,
        )

        assert node.is_from_nested_prefab is True

    def test_build_hierarchy_with_guid_index_none(self):
        """Test build_hierarchy works without guid_index."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
        hierarchy = build_hierarchy(doc)

        assert hierarchy is not None
        assert hierarchy.guid_index is None

    def test_hierarchy_has_project_root_field(self):
        """Test Hierarchy has project_root field."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
        hierarchy = build_hierarchy(doc)

        # Should have project_root field (may be None)
        assert hasattr(hierarchy, "project_root")

    def test_hierarchy_nodes_have_hierarchy_reference(self):
        """Test that nodes have _hierarchy reference set."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
        hierarchy = build_hierarchy(doc)

        # All nodes should have _hierarchy reference
        for node in hierarchy.iter_all():
            assert node._hierarchy is hierarchy

    def test_load_source_prefab_non_prefab_instance(self):
        """Test load_source_prefab returns False for non-PrefabInstance."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
        hierarchy = build_hierarchy(doc)

        root = hierarchy.find("RootCanvas")
        assert root is not None
        assert not root.is_prefab_instance

        # Should return False for non-PrefabInstance
        result = root.load_source_prefab()
        assert result is False

    def test_load_source_prefab_no_guid_index(self):
        """Test load_source_prefab returns False without guid_index."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
        hierarchy = build_hierarchy(doc)

        prefab_instances = [node for node in hierarchy.iter_all() if node.is_prefab_instance]
        if prefab_instances:
            node = prefab_instances[0]
            # Without guid_index and project_root, should return False
            result = node.load_source_prefab()
            assert result is False

    def test_load_all_nested_prefabs_no_guid_index(self):
        """Test load_all_nested_prefabs returns 0 without guid_index."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
        hierarchy = build_hierarchy(doc)

        # Without guid_index, should return 0
        count = hierarchy.load_all_nested_prefabs()
        assert count == 0


class TestGUIDIndexResolution:
    """Test GUID index name resolution features."""

    def test_guid_index_resolve_name(self):
        """Test GUIDIndex.resolve_name method."""
        from unityflow.asset_tracker import GUIDIndex

        index = GUIDIndex()
        index.guid_to_path["test_guid"] = Path("Assets/Scripts/PlayerController.cs")

        name = index.resolve_name("test_guid")
        assert name == "PlayerController"

    def test_guid_index_resolve_name_not_found(self):
        """Test GUIDIndex.resolve_name returns None for unknown GUID."""
        from unityflow.asset_tracker import GUIDIndex

        index = GUIDIndex()
        name = index.resolve_name("nonexistent_guid")
        assert name is None

    def test_guid_index_resolve_path(self):
        """Test GUIDIndex.resolve_path method."""
        from unityflow.asset_tracker import GUIDIndex

        index = GUIDIndex()
        index.guid_to_path["test_guid"] = Path("Assets/Prefabs/MyPrefab.prefab")

        path = index.resolve_path("test_guid")
        assert path == Path("Assets/Prefabs/MyPrefab.prefab")

    def test_guid_index_resolve_path_not_found(self):
        """Test GUIDIndex.resolve_path returns None for unknown GUID."""
        from unityflow.asset_tracker import GUIDIndex

        index = GUIDIndex()
        path = index.resolve_path("nonexistent_guid")
        assert path is None


class TestChildrenSortOrder:
    """Test that children are sorted according to Transform's m_Children order."""

    def test_children_sorted_by_m_children_order(self):
        """Test that children match Unity Editor order based on m_Children."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "children_order.prefab")
        hierarchy = build_hierarchy(doc)

        # Find Canvas node
        canvas = hierarchy.find("Canvas")
        assert canvas is not None
        assert len(canvas.children) == 3

        # Children should be in m_Children order: Header, Content, Footer
        # NOT in document traversal order: Footer, Header, Content
        child_names = [c.name for c in canvas.children]
        assert child_names == [
            "Header",
            "Content",
            "Footer",
        ], f"Expected ['Header', 'Content', 'Footer'] but got {child_names}"

    def test_children_order_find_by_path(self):
        """Test that find works correctly with sorted children."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "children_order.prefab")
        hierarchy = build_hierarchy(doc)

        # Should find correct child by index
        header = hierarchy.find("Canvas/Header")
        assert header is not None
        assert header.name == "Header"

        content = hierarchy.find("Canvas/Content")
        assert content is not None
        assert content.name == "Content"

        footer = hierarchy.find("Canvas/Footer")
        assert footer is not None
        assert footer.name == "Footer"

    def test_children_order_with_index_notation(self):
        """Test that index notation works correctly with sorted children."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "children_order.prefab")
        hierarchy = build_hierarchy(doc)

        canvas = hierarchy.find("Canvas")
        assert canvas is not None

        # First child (index 0) should be Header
        first = canvas.children[0]
        assert first.name == "Header"

        # Second child (index 1) should be Content
        second = canvas.children[1]
        assert second.name == "Content"

        # Third child (index 2) should be Footer
        third = canvas.children[2]
        assert third.name == "Footer"


class TestNestedPrefabCaching:
    """Test nested prefab hierarchy caching."""

    def test_hierarchy_has_nested_prefab_cache(self):
        """Test that Hierarchy has _nested_prefab_cache field."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
        hierarchy = build_hierarchy(doc)

        # Should have the cache field
        assert hasattr(hierarchy, "_nested_prefab_cache")
        assert isinstance(hierarchy._nested_prefab_cache, dict)
        # Cache should be empty initially
        assert len(hierarchy._nested_prefab_cache) == 0

    def test_get_or_load_nested_hierarchy_caches_result(self):
        """Test that _get_or_load_nested_hierarchy caches the result."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Assets").mkdir()

            # Create a simple prefab
            prefab_content = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!1 &100000
GameObject:
  m_Name: TestRoot
  m_Component:
  - component: {fileID: 400000}
--- !u!4 &400000
Transform:
  m_GameObject: {fileID: 100000}
  m_Father: {fileID: 0}
  m_Children: []
"""
            prefab_path = project_root / "Assets" / "TestPrefab.prefab"
            prefab_path.write_text(prefab_content)

            # Create parent hierarchy
            doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
            hierarchy = build_hierarchy(doc)

            # Load nested hierarchy
            source_guid = "test_guid_for_caching"
            result1 = hierarchy._get_or_load_nested_hierarchy(source_guid, prefab_path, None)

            assert result1 is not None
            assert source_guid in hierarchy._nested_prefab_cache

            # Load again - should return cached result
            result2 = hierarchy._get_or_load_nested_hierarchy(source_guid, prefab_path, None)

            # Should be the exact same object (cached)
            assert result1 is result2

    def test_nested_prefab_cache_different_guids(self):
        """Test that different GUIDs create different cache entries."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Assets").mkdir()

            # Create two prefabs
            for name in ["Prefab1", "Prefab2"]:
                prefab_content = f"""%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!1 &100000
GameObject:
  m_Name: {name}
  m_Component:
  - component: {{fileID: 400000}}
--- !u!4 &400000
Transform:
  m_GameObject: {{fileID: 100000}}
  m_Father: {{fileID: 0}}
  m_Children: []
"""
                (project_root / "Assets" / f"{name}.prefab").write_text(prefab_content)

            # Create parent hierarchy
            doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
            hierarchy = build_hierarchy(doc)

            # Load both prefabs
            result1 = hierarchy._get_or_load_nested_hierarchy("guid1", project_root / "Assets" / "Prefab1.prefab", None)
            result2 = hierarchy._get_or_load_nested_hierarchy("guid2", project_root / "Assets" / "Prefab2.prefab", None)

            # Should have 2 cache entries
            assert len(hierarchy._nested_prefab_cache) == 2
            assert "guid1" in hierarchy._nested_prefab_cache
            assert "guid2" in hierarchy._nested_prefab_cache

            # Results should be different hierarchies
            assert result1 is not result2

    def test_nested_prefab_cache_returns_none_on_error(self):
        """Test that _get_or_load_nested_hierarchy returns None on error."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "nested_prefab.prefab")
        hierarchy = build_hierarchy(doc)

        # Try to load nonexistent file
        result = hierarchy._get_or_load_nested_hierarchy(
            "nonexistent_guid",
            Path("/nonexistent/path/to/prefab.prefab"),
            None,
        )

        assert result is None
        # Should not be cached on error
        assert "nonexistent_guid" not in hierarchy._nested_prefab_cache

    def test_load_source_prefab_uses_cache(self):
        """Test that load_source_prefab uses hierarchy cache."""
        import tempfile

        from unityflow.asset_tracker import GUIDIndex

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Assets").mkdir()

            # Create a source prefab
            source_guid = "abc123def45678901234567890123456"
            prefab_content = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!1 &100000
GameObject:
  m_Name: SourceRoot
  m_Component:
  - component: {fileID: 400000}
--- !u!4 &400000
Transform:
  m_GameObject: {fileID: 100000}
  m_Father: {fileID: 0}
  m_Children: []
"""
            prefab_path = project_root / "Assets" / "SourcePrefab.prefab"
            prefab_path.write_text(prefab_content)

            # Create GUID index
            guid_index = GUIDIndex(project_root=project_root)
            guid_index.guid_to_path[source_guid] = Path("Assets/SourcePrefab.prefab")

            # Create parent prefab with PrefabInstance
            parent_content = f"""%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!1 &100000
GameObject:
  m_Name: ParentRoot
  m_Component:
  - component: {{fileID: 400000}}
--- !u!4 &400000
Transform:
  m_GameObject: {{fileID: 100000}}
  m_Father: {{fileID: 0}}
  m_Children:
  - {{fileID: 500000}}
  - {{fileID: 600000}}
--- !u!1001 &200000
PrefabInstance:
  m_ObjectHideFlags: 0
  m_SourcePrefab: {{fileID: 100100000, guid: {source_guid}, type: 3}}
  m_Modification:
    m_TransformParent: {{fileID: 400000}}
    m_Modifications:
    - target: {{fileID: 100000, guid: {source_guid}}}
      propertyPath: m_Name
      value: Instance1
      objectReference: {{fileID: 0}}
--- !u!4 &500000 stripped
Transform:
  m_CorrespondingSourceObject: {{fileID: 400000, guid: {source_guid}}}
  m_PrefabInstance: {{fileID: 200000}}
--- !u!1001 &300000
PrefabInstance:
  m_ObjectHideFlags: 0
  m_SourcePrefab: {{fileID: 100100000, guid: {source_guid}, type: 3}}
  m_Modification:
    m_TransformParent: {{fileID: 400000}}
    m_Modifications:
    - target: {{fileID: 100000, guid: {source_guid}}}
      propertyPath: m_Name
      value: Instance2
      objectReference: {{fileID: 0}}
--- !u!4 &600000 stripped
Transform:
  m_CorrespondingSourceObject: {{fileID: 400000, guid: {source_guid}}}
  m_PrefabInstance: {{fileID: 300000}}
"""
            parent_path = project_root / "Assets" / "ParentPrefab.prefab"
            parent_path.write_text(parent_content)

            # Load parent hierarchy
            parent_doc = UnityYAMLDocument.load(parent_path)
            hierarchy = build_hierarchy(parent_doc, guid_index=guid_index, project_root=project_root)

            # Find the two PrefabInstance nodes
            prefab_instances = [node for node in hierarchy.iter_all() if node.is_prefab_instance]
            assert len(prefab_instances) == 2

            # Load first instance
            result1 = prefab_instances[0].load_source_prefab()
            assert result1 is True
            assert prefab_instances[0].nested_prefab_loaded is True

            # Cache should have one entry
            assert len(hierarchy._nested_prefab_cache) == 1
            assert source_guid in hierarchy._nested_prefab_cache

            # Load second instance - should use cache
            result2 = prefab_instances[1].load_source_prefab()
            assert result2 is True
            assert prefab_instances[1].nested_prefab_loaded is True

            # Cache should still have one entry (same GUID)
            assert len(hierarchy._nested_prefab_cache) == 1

"""High-level Hierarchy API for Unity Prefabs and Scenes.

This module provides an abstraction layer for Unity's Nested Prefab structure,
including stripped objects and PrefabInstance relationships, allowing users to
work with hierarchies without understanding Unity's internal representation.

Key Concepts:
- Stripped objects: Placeholder references to objects inside nested prefabs
- PrefabInstance: Reference to an instantiated prefab with property overrides
- m_Modifications: Property overrides applied to nested prefab instances

Example:
    >>> doc = UnityYAMLDocument.load("file.prefab")
    >>> hierarchy = Hierarchy.build(doc)
    >>> for node in hierarchy.root_objects:
    ...     print(node.name)
    ...     if node.is_prefab_instance:
    ...         print(f"  Nested prefab: {node.source_guid}")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Iterator

from .parser import (
    CLASS_IDS,
    UnityYAMLObject,
    create_game_object,
    create_rect_transform,
    create_transform,
    generate_file_id,
)

if TYPE_CHECKING:
    from .parser import UnityYAMLDocument


@dataclass
class ComponentInfo:
    """Information about a component attached to a GameObject."""

    file_id: int
    class_id: int
    class_name: str
    data: dict[str, Any]
    is_on_stripped_object: bool = False

    @property
    def type_name(self) -> str:
        """Get the component type name."""
        return self.class_name


@dataclass
class HierarchyNode:
    """Represents a node in the GameObject hierarchy.

    A HierarchyNode can represent either:
    - A regular GameObject with its Transform and components
    - A PrefabInstance (nested prefab) with its modifications

    Attributes:
        file_id: The fileID of this node's primary object (GameObject or PrefabInstance)
        name: The name of this object
        transform_id: The fileID of the associated Transform/RectTransform
        parent: Parent node (None for root objects)
        children: List of child nodes
        components: List of components attached to this object
        is_prefab_instance: Whether this node represents a nested prefab
        source_guid: GUID of the source prefab (only for PrefabInstance nodes)
        is_stripped: Whether the underlying object is stripped
        prefab_instance_id: For stripped objects, the PrefabInstance they belong to
    """

    file_id: int
    name: str
    transform_id: int
    is_ui: bool = False
    parent: HierarchyNode | None = None
    children: list[HierarchyNode] = field(default_factory=list)
    components: list[ComponentInfo] = field(default_factory=list)
    is_prefab_instance: bool = False
    source_guid: str = ""
    source_file_id: int = 0
    is_stripped: bool = False
    prefab_instance_id: int = 0
    modifications: list[dict[str, Any]] = field(default_factory=list)
    _document: UnityYAMLDocument | None = field(default=None, repr=False)

    def find(self, path: str) -> HierarchyNode | None:
        """Find a descendant node by path.

        Args:
            path: Path like "Panel/Button" (relative to this node)

        Returns:
            The found node, or None if not found
        """
        if not path:
            return self

        parts = path.split("/")
        name = parts[0]
        rest = "/".join(parts[1:]) if len(parts) > 1 else ""

        # Handle index notation like "Button[1]"
        index = 0
        if "[" in name and name.endswith("]"):
            bracket_pos = name.index("[")
            index = int(name[bracket_pos + 1 : -1])
            name = name[:bracket_pos]

        # Find matching children
        matches = [c for c in self.children if c.name == name]
        if index < len(matches):
            found = matches[index]
            return found.find(rest) if rest else found

        return None

    def get_component(
        self, type_name: str, index: int = 0
    ) -> ComponentInfo | None:
        """Get a component by type name.

        Args:
            type_name: Component type like "MonoBehaviour", "Image", etc.
            index: Index if multiple components of same type exist

        Returns:
            The component info, or None if not found
        """
        matches = [c for c in self.components if c.class_name == type_name]
        return matches[index] if index < len(matches) else None

    def get_components(self, type_name: str | None = None) -> list[ComponentInfo]:
        """Get all components, optionally filtered by type.

        Args:
            type_name: Optional type name to filter by

        Returns:
            List of matching components
        """
        if type_name is None:
            return list(self.components)
        return [c for c in self.components if c.class_name == type_name]

    @property
    def path(self) -> str:
        """Get the full path from root to this node."""
        if self.parent is None:
            return self.name
        return f"{self.parent.path}/{self.name}"

    def iter_descendants(self) -> Iterator[HierarchyNode]:
        """Iterate over all descendant nodes (depth-first)."""
        for child in self.children:
            yield child
            yield from child.iter_descendants()

    def get_property(self, property_path: str) -> Any | None:
        """Get a property value from this node's GameObject or Transform.

        Args:
            property_path: Property path like "m_Name" or "m_LocalPosition.x"

        Returns:
            The property value, or None if not found
        """
        if self._document is None:
            return None

        obj = self._document.get_by_file_id(self.file_id)
        if obj is None:
            return None

        content = obj.get_content()
        if content is None:
            return None

        # Navigate nested properties
        parts = property_path.split(".")
        value = content
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return None
        return value

    def set_property(self, property_path: str, value: Any) -> bool:
        """Set a property value on this node's GameObject.

        For PrefabInstance nodes, this adds an entry to m_Modifications.

        Args:
            property_path: Property path like "m_Name" or "m_LocalPosition.x"
            value: The new value

        Returns:
            True if successful, False otherwise
        """
        if self._document is None:
            return False

        if self.is_prefab_instance and self.prefab_instance_id:
            # Add to m_Modifications
            prefab_instance = self._document.get_by_file_id(self.prefab_instance_id)
            if prefab_instance is None:
                return False

            content = prefab_instance.get_content()
            if content is None:
                return False

            modification = content.get("m_Modification", {})
            modifications = modification.get("m_Modifications", [])

            # Find or create modification entry
            target_found = False
            for mod in modifications:
                target = mod.get("target", {})
                if (
                    target.get("fileID") == self.source_file_id
                    and mod.get("propertyPath") == property_path
                ):
                    mod["value"] = value
                    target_found = True
                    break

            if not target_found:
                modifications.append(
                    {
                        "target": {
                            "fileID": self.source_file_id,
                            "guid": self.source_guid,
                        },
                        "propertyPath": property_path,
                        "value": value,
                        "objectReference": {"fileID": 0},
                    }
                )
                modification["m_Modifications"] = modifications
                content["m_Modification"] = modification

            return True

        # Regular object - direct modification
        obj = self._document.get_by_file_id(self.file_id)
        if obj is None:
            return False

        content = obj.get_content()
        if content is None:
            return False

        # Navigate to parent and set final property
        parts = property_path.split(".")
        target = content
        for part in parts[:-1]:
            if isinstance(target, dict):
                if part not in target:
                    target[part] = {}
                target = target[part]
            else:
                return False

        if isinstance(target, dict):
            target[parts[-1]] = value
            return True
        return False


@dataclass
class Hierarchy:
    """Represents the complete hierarchy of a Unity YAML document.

    Provides methods for traversing, querying, and modifying the hierarchy
    with automatic handling of stripped objects and PrefabInstance relationships.
    """

    root_objects: list[HierarchyNode] = field(default_factory=list)
    _document: UnityYAMLDocument | None = field(default=None, repr=False)
    _nodes_by_file_id: dict[int, HierarchyNode] = field(
        default_factory=dict, repr=False
    )
    _stripped_transforms: dict[int, int] = field(default_factory=dict, repr=False)
    _stripped_game_objects: dict[int, int] = field(default_factory=dict, repr=False)
    _prefab_instances: dict[int, list[int]] = field(default_factory=dict, repr=False)

    @classmethod
    def build(cls, doc: UnityYAMLDocument) -> Hierarchy:
        """Build a hierarchy from a UnityYAMLDocument.

        This method:
        1. Builds indexes for stripped objects and PrefabInstances
        2. Constructs the transform hierarchy (parent-child relationships)
        3. Links components to their GameObjects
        4. Resolves stripped object references to PrefabInstances

        Args:
            doc: The Unity YAML document to build hierarchy from

        Returns:
            A Hierarchy instance with the complete object tree
        """
        hierarchy = cls(_document=doc)
        hierarchy._build_indexes(doc)
        hierarchy._build_nodes(doc)
        hierarchy._link_hierarchy()
        return hierarchy

    def _build_indexes(self, doc: UnityYAMLDocument) -> None:
        """Build lookup indexes for efficient resolution."""
        # Index stripped objects
        for obj in doc.objects:
            if obj.stripped:
                content = obj.get_content()
                if content is None:
                    continue

                prefab_ref = content.get("m_PrefabInstance", {})
                prefab_id = (
                    prefab_ref.get("fileID", 0)
                    if isinstance(prefab_ref, dict)
                    else 0
                )

                if prefab_id:
                    # Track stripped object -> PrefabInstance mapping
                    if obj.class_id in (4, 224):  # Transform or RectTransform
                        self._stripped_transforms[obj.file_id] = prefab_id
                    elif obj.class_id == 1:  # GameObject
                        self._stripped_game_objects[obj.file_id] = prefab_id

                    # Track PrefabInstance -> stripped objects mapping
                    if prefab_id not in self._prefab_instances:
                        self._prefab_instances[prefab_id] = []
                    self._prefab_instances[prefab_id].append(obj.file_id)

    def _build_nodes(self, doc: UnityYAMLDocument) -> None:
        """Build HierarchyNode objects for each GameObject and PrefabInstance."""
        # Build transform -> GameObject mapping
        transform_to_go: dict[int, int] = {}
        go_to_transform: dict[int, int] = {}

        for obj in doc.objects:
            if obj.class_id in (4, 224) and not obj.stripped:
                content = obj.get_content()
                if content:
                    go_ref = content.get("m_GameObject", {})
                    go_id = (
                        go_ref.get("fileID", 0) if isinstance(go_ref, dict) else 0
                    )
                    if go_id:
                        transform_to_go[obj.file_id] = go_id
                        go_to_transform[go_id] = obj.file_id

        # Create nodes for regular GameObjects
        for obj in doc.objects:
            if obj.class_id == 1 and not obj.stripped:
                content = obj.get_content()
                if content is None:
                    continue

                name = content.get("m_Name", "")
                transform_id = go_to_transform.get(obj.file_id, 0)

                # Determine if UI
                is_ui = False
                if transform_id:
                    transform_obj = doc.get_by_file_id(transform_id)
                    if transform_obj and transform_obj.class_id == 224:
                        is_ui = True

                node = HierarchyNode(
                    file_id=obj.file_id,
                    name=name,
                    transform_id=transform_id,
                    is_ui=is_ui,
                    _document=doc,
                )
                self._nodes_by_file_id[obj.file_id] = node

                # Collect components
                components = content.get("m_Component", [])
                for comp_entry in components:
                    if isinstance(comp_entry, dict):
                        comp_ref = comp_entry.get("component", {})
                        comp_id = (
                            comp_ref.get("fileID", 0)
                            if isinstance(comp_ref, dict)
                            else 0
                        )
                        if comp_id and comp_id != transform_id:
                            comp_obj = doc.get_by_file_id(comp_id)
                            if comp_obj:
                                node.components.append(
                                    ComponentInfo(
                                        file_id=comp_id,
                                        class_id=comp_obj.class_id,
                                        class_name=comp_obj.class_name,
                                        data=comp_obj.get_content() or {},
                                    )
                                )

        # Create nodes for PrefabInstances
        for obj in doc.objects:
            if obj.class_id == 1001:  # PrefabInstance
                content = obj.get_content()
                if content is None:
                    continue

                # Get source prefab info
                source = content.get("m_SourcePrefab", {})
                source_guid = source.get("guid", "") if isinstance(source, dict) else ""
                source_file_id = (
                    source.get("fileID", 0) if isinstance(source, dict) else 0
                )

                # Get name from modifications
                modification = content.get("m_Modification", {})
                modifications = modification.get("m_Modifications", [])

                name = ""
                for mod in modifications:
                    if mod.get("propertyPath") == "m_Name":
                        name = str(mod.get("value", ""))
                        break

                if not name:
                    # Try to get name from root stripped object
                    name = f"PrefabInstance_{obj.file_id}"

                # Find the root transform of this PrefabInstance
                transform_id = 0
                stripped_ids = self._prefab_instances.get(obj.file_id, [])
                for stripped_id in stripped_ids:
                    stripped_obj = doc.get_by_file_id(stripped_id)
                    if stripped_obj and stripped_obj.class_id in (4, 224):
                        # Check if this is the root (parent is outside the prefab)
                        transform_id = stripped_id
                        break

                node = HierarchyNode(
                    file_id=obj.file_id,
                    name=name,
                    transform_id=transform_id,
                    is_prefab_instance=True,
                    source_guid=source_guid,
                    source_file_id=source_file_id,
                    modifications=modifications,
                    _document=doc,
                )

                self._nodes_by_file_id[obj.file_id] = node

                # Collect components on stripped GameObjects in this prefab
                for stripped_id in stripped_ids:
                    if stripped_id in self._stripped_game_objects:
                        # Find components referencing this stripped GameObject
                        for comp_obj in doc.objects:
                            if comp_obj.class_id not in (
                                1,
                                4,
                                224,
                                1001,
                            ) and not comp_obj.stripped:
                                comp_content = comp_obj.get_content()
                                if comp_content:
                                    go_ref = comp_content.get("m_GameObject", {})
                                    go_id = (
                                        go_ref.get("fileID", 0)
                                        if isinstance(go_ref, dict)
                                        else 0
                                    )
                                    if go_id == stripped_id:
                                        node.components.append(
                                            ComponentInfo(
                                                file_id=comp_obj.file_id,
                                                class_id=comp_obj.class_id,
                                                class_name=comp_obj.class_name,
                                                data=comp_content,
                                                is_on_stripped_object=True,
                                            )
                                        )

    def _link_hierarchy(self) -> None:
        """Link parent-child relationships and identify root objects."""
        if self._document is None:
            return

        doc = self._document

        # Build transform parent-child map
        transform_parents: dict[int, int] = {}  # child_transform -> parent_transform

        for obj in doc.objects:
            if obj.class_id in (4, 224):  # Transform or RectTransform
                content = obj.get_content()
                if content:
                    father = content.get("m_Father", {})
                    father_id = (
                        father.get("fileID", 0) if isinstance(father, dict) else 0
                    )
                    if father_id:
                        transform_parents[obj.file_id] = father_id

        # Also check PrefabInstance m_TransformParent
        for obj in doc.objects:
            if obj.class_id == 1001:
                content = obj.get_content()
                if content:
                    modification = content.get("m_Modification", {})
                    parent_ref = modification.get("m_TransformParent", {})
                    parent_id = (
                        parent_ref.get("fileID", 0)
                        if isinstance(parent_ref, dict)
                        else 0
                    )

                    # Find the root stripped transform for this PrefabInstance
                    stripped_ids = self._prefab_instances.get(obj.file_id, [])
                    for stripped_id in stripped_ids:
                        if stripped_id in self._stripped_transforms:
                            transform_parents[stripped_id] = parent_id
                            break

        # Build transform -> node mapping
        transform_to_node: dict[int, HierarchyNode] = {}
        for node in self._nodes_by_file_id.values():
            if node.transform_id:
                transform_to_node[node.transform_id] = node

        # Link parent-child relationships
        for node in self._nodes_by_file_id.values():
            if node.transform_id and node.transform_id in transform_parents:
                parent_transform_id = transform_parents[node.transform_id]
                parent_node = transform_to_node.get(parent_transform_id)
                if parent_node:
                    node.parent = parent_node
                    parent_node.children.append(node)

        # Collect root objects
        for node in self._nodes_by_file_id.values():
            if node.parent is None:
                self.root_objects.append(node)

    def find(self, path: str) -> HierarchyNode | None:
        """Find a node by full path from root.

        Args:
            path: Full path like "Canvas/Panel/Button"

        Returns:
            The found node, or None if not found
        """
        if not path:
            return None

        parts = path.split("/")
        root_name = parts[0]
        rest = "/".join(parts[1:]) if len(parts) > 1 else ""

        # Handle index notation
        index = 0
        if "[" in root_name and root_name.endswith("]"):
            bracket_pos = root_name.index("[")
            index = int(root_name[bracket_pos + 1 : -1])
            root_name = root_name[:bracket_pos]

        # Find matching root
        matches = [r for r in self.root_objects if r.name == root_name]
        if index < len(matches):
            root = matches[index]
            return root.find(rest) if rest else root

        return None

    def get_by_file_id(self, file_id: int) -> HierarchyNode | None:
        """Get a node by its fileID.

        Args:
            file_id: The fileID to look up

        Returns:
            The node, or None if not found
        """
        return self._nodes_by_file_id.get(file_id)

    def iter_all(self) -> Iterator[HierarchyNode]:
        """Iterate over all nodes in the hierarchy."""
        for root in self.root_objects:
            yield root
            yield from root.iter_descendants()

    def get_prefab_instance_for(self, stripped_file_id: int) -> int:
        """Get the PrefabInstance ID for a stripped object.

        Args:
            stripped_file_id: FileID of a stripped Transform or GameObject

        Returns:
            FileID of the owning PrefabInstance, or 0 if not found
        """
        if stripped_file_id in self._stripped_transforms:
            return self._stripped_transforms[stripped_file_id]
        if stripped_file_id in self._stripped_game_objects:
            return self._stripped_game_objects[stripped_file_id]
        return 0

    def get_stripped_objects_for(self, prefab_instance_id: int) -> list[int]:
        """Get all stripped object IDs belonging to a PrefabInstance.

        Args:
            prefab_instance_id: FileID of the PrefabInstance

        Returns:
            List of stripped object fileIDs
        """
        return self._prefab_instances.get(prefab_instance_id, [])

    def resolve_game_object(self, file_id: int) -> HierarchyNode | None:
        """Resolve a fileID to its effective HierarchyNode.

        For regular objects, returns the node directly.
        For stripped objects, returns the owning PrefabInstance node.
        For components on stripped objects, returns the PrefabInstance node.

        Args:
            file_id: FileID of a GameObject, component, or stripped object

        Returns:
            The resolved HierarchyNode, or None if not found
        """
        # Direct lookup
        if file_id in self._nodes_by_file_id:
            return self._nodes_by_file_id[file_id]

        # Check if it's a stripped object
        if file_id in self._stripped_transforms:
            prefab_id = self._stripped_transforms[file_id]
            return self._nodes_by_file_id.get(prefab_id)

        if file_id in self._stripped_game_objects:
            prefab_id = self._stripped_game_objects[file_id]
            return self._nodes_by_file_id.get(prefab_id)

        # Check if it's a component
        if self._document:
            obj = self._document.get_by_file_id(file_id)
            if obj and obj.class_id not in (1, 4, 224, 1001):
                content = obj.get_content()
                if content:
                    go_ref = content.get("m_GameObject", {})
                    go_id = (
                        go_ref.get("fileID", 0) if isinstance(go_ref, dict) else 0
                    )
                    if go_id:
                        return self.resolve_game_object(go_id)

        return None

    def add_prefab_instance(
        self,
        source_guid: str,
        parent: HierarchyNode | None = None,
        name: str | None = None,
        position: tuple[float, float, float] = (0, 0, 0),
        source_root_transform_id: int = 0,
        source_root_go_id: int = 0,
        is_ui: bool = False,
    ) -> HierarchyNode | None:
        """Add a new PrefabInstance to the hierarchy.

        This method creates:
        1. A PrefabInstance entry with m_Modification
        2. Stripped Transform/RectTransform entry
        3. Stripped GameObject entry (if source IDs provided)

        Args:
            source_guid: GUID of the source prefab
            parent: Parent node to attach to (None for root)
            name: Override name for the instance
            position: Local position (x, y, z)
            source_root_transform_id: FileID of root Transform in source prefab
            source_root_go_id: FileID of root GameObject in source prefab
            is_ui: Whether to use RectTransform

        Returns:
            The created HierarchyNode, or None if failed
        """
        if self._document is None:
            return None

        doc = self._document

        # Generate fileIDs
        prefab_instance_id = generate_file_id()
        stripped_transform_id = generate_file_id()
        stripped_go_id = generate_file_id() if source_root_go_id else 0

        # Get parent transform ID
        parent_transform_id = parent.transform_id if parent else 0

        # Build modifications list
        modifications: list[dict[str, Any]] = []

        # Position modification
        if source_root_transform_id:
            if position[0] != 0:
                modifications.append(
                    {
                        "target": {"fileID": source_root_transform_id, "guid": source_guid},
                        "propertyPath": "m_LocalPosition.x",
                        "value": position[0],
                        "objectReference": {"fileID": 0},
                    }
                )
            if position[1] != 0:
                modifications.append(
                    {
                        "target": {"fileID": source_root_transform_id, "guid": source_guid},
                        "propertyPath": "m_LocalPosition.y",
                        "value": position[1],
                        "objectReference": {"fileID": 0},
                    }
                )
            if position[2] != 0:
                modifications.append(
                    {
                        "target": {"fileID": source_root_transform_id, "guid": source_guid},
                        "propertyPath": "m_LocalPosition.z",
                        "value": position[2],
                        "objectReference": {"fileID": 0},
                    }
                )

        # Name modification
        if name and source_root_go_id:
            modifications.append(
                {
                    "target": {"fileID": source_root_go_id, "guid": source_guid},
                    "propertyPath": "m_Name",
                    "value": name,
                    "objectReference": {"fileID": 0},
                }
            )

        # Create PrefabInstance object
        prefab_instance_data = {
            "PrefabInstance": {
                "m_ObjectHideFlags": 0,
                "serializedVersion": 2,
                "m_Modification": {
                    "serializedVersion": 3,
                    "m_TransformParent": {"fileID": parent_transform_id},
                    "m_Modifications": modifications,
                    "m_RemovedComponents": [],
                    "m_RemovedGameObjects": [],
                    "m_AddedGameObjects": [],
                    "m_AddedComponents": [],
                },
                "m_SourcePrefab": {
                    "fileID": 100100000,
                    "guid": source_guid,
                    "type": 3,
                },
            }
        }
        prefab_instance_obj = UnityYAMLObject(
            class_id=1001,
            file_id=prefab_instance_id,
            data=prefab_instance_data,
        )
        doc.add_object(prefab_instance_obj)

        # Create stripped Transform
        transform_class_id = 224 if is_ui else 4
        transform_root_key = "RectTransform" if is_ui else "Transform"
        stripped_transform_data = {
            transform_root_key: {
                "m_CorrespondingSourceObject": {
                    "fileID": source_root_transform_id,
                    "guid": source_guid,
                },
                "m_PrefabInstance": {"fileID": prefab_instance_id},
            }
        }
        stripped_transform_obj = UnityYAMLObject(
            class_id=transform_class_id,
            file_id=stripped_transform_id,
            data=stripped_transform_data,
            stripped=True,
        )
        doc.add_object(stripped_transform_obj)

        # Create stripped GameObject if source ID provided
        if source_root_go_id:
            stripped_go_data = {
                "GameObject": {
                    "m_CorrespondingSourceObject": {
                        "fileID": source_root_go_id,
                        "guid": source_guid,
                    },
                    "m_PrefabInstance": {"fileID": prefab_instance_id},
                }
            }
            stripped_go_obj = UnityYAMLObject(
                class_id=1,
                file_id=stripped_go_id,
                data=stripped_go_data,
                stripped=True,
            )
            doc.add_object(stripped_go_obj)

        # Update parent's m_Children
        if parent_transform_id:
            parent_transform = doc.get_by_file_id(parent_transform_id)
            if parent_transform:
                content = parent_transform.get_content()
                if content:
                    children = content.get("m_Children", [])
                    children.append({"fileID": stripped_transform_id})
                    content["m_Children"] = children

        # Update indexes
        self._stripped_transforms[stripped_transform_id] = prefab_instance_id
        if source_root_go_id:
            self._stripped_game_objects[stripped_go_id] = prefab_instance_id
        self._prefab_instances[prefab_instance_id] = [stripped_transform_id]
        if source_root_go_id:
            self._prefab_instances[prefab_instance_id].append(stripped_go_id)

        # Create and register node
        node = HierarchyNode(
            file_id=prefab_instance_id,
            name=name or f"PrefabInstance_{prefab_instance_id}",
            transform_id=stripped_transform_id,
            is_ui=is_ui,
            is_prefab_instance=True,
            source_guid=source_guid,
            source_file_id=100100000,
            modifications=modifications,
            parent=parent,
            _document=doc,
        )

        if parent:
            parent.children.append(node)
        else:
            self.root_objects.append(node)

        self._nodes_by_file_id[prefab_instance_id] = node

        return node


def build_hierarchy(doc: UnityYAMLDocument) -> Hierarchy:
    """Build a hierarchy from a UnityYAMLDocument.

    Convenience function that calls Hierarchy.build().

    Args:
        doc: The Unity YAML document

    Returns:
        A Hierarchy instance
    """
    return Hierarchy.build(doc)


def resolve_game_object_for_component(
    doc: UnityYAMLDocument, component_file_id: int
) -> int:
    """Resolve a component to its owning GameObject, handling stripped objects.

    Args:
        doc: The Unity YAML document
        component_file_id: FileID of the component

    Returns:
        FileID of the owning GameObject (or PrefabInstance if stripped)
    """
    comp = doc.get_by_file_id(component_file_id)
    if comp is None:
        return 0

    content = comp.get_content()
    if content is None:
        return 0

    go_ref = content.get("m_GameObject", {})
    go_id = go_ref.get("fileID", 0) if isinstance(go_ref, dict) else 0

    if not go_id:
        return 0

    # Check if the referenced GameObject is stripped
    go = doc.get_by_file_id(go_id)
    if go and go.stripped:
        # Return the PrefabInstance instead
        go_content = go.get_content()
        if go_content:
            prefab_ref = go_content.get("m_PrefabInstance", {})
            prefab_id = (
                prefab_ref.get("fileID", 0) if isinstance(prefab_ref, dict) else 0
            )
            if prefab_id:
                return prefab_id

    return go_id


def get_prefab_instance_for_stripped(doc: UnityYAMLDocument, file_id: int) -> int:
    """Get the PrefabInstance ID for a stripped object.

    Args:
        doc: The Unity YAML document
        file_id: FileID of the stripped object

    Returns:
        FileID of the owning PrefabInstance, or 0 if not stripped
    """
    obj = doc.get_by_file_id(file_id)
    if obj is None or not obj.stripped:
        return 0

    content = obj.get_content()
    if content is None:
        return 0

    prefab_ref = content.get("m_PrefabInstance", {})
    return prefab_ref.get("fileID", 0) if isinstance(prefab_ref, dict) else 0


def get_stripped_objects_for_prefab(doc: UnityYAMLDocument, prefab_instance_id: int) -> list[int]:
    """Get all stripped objects belonging to a PrefabInstance.

    Args:
        doc: The Unity YAML document
        prefab_instance_id: FileID of the PrefabInstance

    Returns:
        List of stripped object fileIDs
    """
    result = []
    for obj in doc.objects:
        if obj.stripped:
            content = obj.get_content()
            if content:
                prefab_ref = content.get("m_PrefabInstance", {})
                if isinstance(prefab_ref, dict):
                    if prefab_ref.get("fileID") == prefab_instance_id:
                        result.append(obj.file_id)
    return result

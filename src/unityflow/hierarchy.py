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

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .parser import (
    UnityYAMLObject,
    generate_file_id,
)

if TYPE_CHECKING:
    from .asset_tracker import GUIDIndex
    from .parser import UnityYAMLDocument


@dataclass
class ComponentInfo:
    """Information about a component attached to a GameObject.

    For MonoBehaviour components, script_guid and script_name provide
    the resolved script information when a GUIDIndex is available.

    For components on PrefabInstance nodes, modifications contains the
    property overrides from the PrefabInstance's m_Modifications that
    target this component. Use get_effective_property() to get the
    effective value with modifications applied.

    Attributes:
        file_id: The fileID of this component in the document
        class_id: Unity's ClassID (e.g., 114 for MonoBehaviour)
        class_name: Human-readable class name from ClassID
        data: Full component data dictionary
        is_on_stripped_object: Whether this component is on a stripped GameObject
        script_guid: GUID of the script (only for MonoBehaviour, class_id=114)
        script_name: Resolved script name (only when GUIDIndex provided)
        modifications: Property overrides targeting this component (PrefabInstance only)

    Example:
        >>> comp = node.get_component("MonoBehaviour")
        >>> print(comp.script_name)  # "PlayerController"
        >>> print(comp.script_guid)  # "f4afdcb1cbadf954ba8b1cf465429e17"
        >>> # For PrefabInstance components with modifications:
        >>> value = comp.get_effective_property("m_Enabled")
    """

    file_id: int
    class_id: int
    class_name: str
    data: dict[str, Any]
    is_on_stripped_object: bool = False
    script_guid: str | None = None
    script_name: str | None = None
    modifications: list[dict[str, Any]] | None = None

    @property
    def type_name(self) -> str:
        """Get the component type name.

        For MonoBehaviour components with resolved script names,
        returns the script name. Otherwise returns the class_name.
        """
        if self.script_name:
            return self.script_name
        return self.class_name

    def get_effective_property(self, property_path: str) -> Any | None:
        """Get a property value with modifications applied.

        For components with modifications (typically from PrefabInstance),
        this returns the modified value if it exists, otherwise falls back
        to the original data.

        Args:
            property_path: Property path like "m_Enabled" or "m_Color.r"

        Returns:
            The effective property value, or None if not found
        """
        # Check modifications first
        if self.modifications:
            for mod in self.modifications:
                if mod.get("propertyPath") == property_path:
                    # If objectReference has a fileID, return that
                    obj_ref = mod.get("objectReference", {})
                    if isinstance(obj_ref, dict) and obj_ref.get("fileID", 0) != 0:
                        return obj_ref
                    return mod.get("value")

        # Fall back to original data
        parts = property_path.split(".")
        value = self.data
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return None
        return value


@dataclass
class HierarchyNode:
    """Represents a node in the GameObject hierarchy.

    A HierarchyNode can represent either:
    - A regular GameObject with its Transform and components
    - A PrefabInstance (nested prefab) with its modifications

    For PrefabInstance nodes, the source prefab content can be loaded using
    load_source_prefab() to access the internal structure of the nested prefab.

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
        is_from_nested_prefab: Whether this node was loaded from a nested prefab
        nested_prefab_loaded: Whether nested prefab content has been loaded

    Example:
        >>> # Load nested prefab content for a PrefabInstance
        >>> node = hierarchy.find("board_CoreUpgrade")
        >>> if node.is_prefab_instance:
        ...     node.load_source_prefab(project_root="/path/to/project")
        ...     print(node.children)  # Now shows internal structure
        ...     print(node.nested_prefab_loaded)  # True
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
    is_from_nested_prefab: bool = False
    nested_prefab_loaded: bool = False
    _document: UnityYAMLDocument | None = field(default=None, repr=False)
    _hierarchy: Hierarchy | None = field(default=None, repr=False)

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

    def get_component(self, type_name: str, index: int = 0) -> ComponentInfo | None:
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

        For PrefabInstance nodes, this returns the effective value by checking
        modifications first. This ensures get_property() returns the same value
        that was set via set_property(), providing API consistency.

        Args:
            property_path: Property path like "m_Name" or "m_LocalPosition.x"

        Returns:
            The property value, or None if not found
        """
        # For PrefabInstance, check modifications first for effective value
        if self.is_prefab_instance and self.modifications:
            for mod in self.modifications:
                target = mod.get("target", {})
                # Match by source_guid (same prefab) and propertyPath
                # target.fileID is the fileID within the source prefab, not the prefab asset
                if target.get("guid") == self.source_guid and mod.get("propertyPath") == property_path:
                    # If objectReference has a fileID, return that
                    obj_ref = mod.get("objectReference", {})
                    if isinstance(obj_ref, dict) and obj_ref.get("fileID", 0) != 0:
                        return obj_ref
                    # Otherwise return the value
                    return mod.get("value")

        if self._document is None:
            return None

        # Try GameObject first
        obj = self._document.get_by_file_id(self.file_id)
        if obj is not None:
            content = obj.get_content()
            if content is not None:
                # Navigate nested properties
                parts = property_path.split(".")
                value = content
                found = True
                for part in parts:
                    if isinstance(value, dict) and part in value:
                        value = value[part]
                    else:
                        found = False
                        break
                if found:
                    return value

        # Try Transform/RectTransform if not found in GameObject
        if self.transform_id:
            transform_obj = self._document.get_by_file_id(self.transform_id)
            if transform_obj is not None:
                content = transform_obj.get_content()
                if content is not None:
                    parts = property_path.split(".")
                    value = content
                    for part in parts:
                        if isinstance(value, dict) and part in value:
                            value = value[part]
                        else:
                            return None
                    return value

        return None

    def set_property(self, property_path: str, value: Any) -> bool:
        """Set a property value on this node's GameObject.

        For PrefabInstance nodes, this adds an entry to m_Modifications.
        Both the document and the node's modifications list are updated
        to ensure get_property() returns the same value (API consistency).

        Args:
            property_path: Property path like "m_Name" or "m_LocalPosition.x"
            value: The new value

        Returns:
            True if successful, False otherwise
        """
        if self._document is None:
            return False

        # For PrefabInstance nodes, use file_id as the PrefabInstance ID
        # (prefab_instance_id is only set for stripped objects pointing to a PrefabInstance)
        prefab_id = self.prefab_instance_id if self.prefab_instance_id else self.file_id
        if self.is_prefab_instance:
            # Add to m_Modifications in document
            prefab_instance = self._document.get_by_file_id(prefab_id)
            if prefab_instance is None:
                return False

            content = prefab_instance.get_content()
            if content is None:
                return False

            modification = content.get("m_Modification", {})
            modifications = modification.get("m_Modifications", [])

            # Find or create modification entry in document
            # Match by source_guid and propertyPath (fileID within source may vary)
            target_found = False
            for mod in modifications:
                target = mod.get("target", {})
                if target.get("guid") == self.source_guid and mod.get("propertyPath") == property_path:
                    mod["value"] = value
                    target_found = True
                    break

            if not target_found:
                new_mod = {
                    "target": {
                        "fileID": self.source_file_id,
                        "guid": self.source_guid,
                    },
                    "propertyPath": property_path,
                    "value": value,
                    "objectReference": {"fileID": 0},
                }
                modifications.append(new_mod)
                modification["m_Modifications"] = modifications
                content["m_Modification"] = modification

            # Also update node's modifications list for get_property() consistency
            node_target_found = False
            for mod in self.modifications:
                target = mod.get("target", {})
                if target.get("guid") == self.source_guid and mod.get("propertyPath") == property_path:
                    mod["value"] = value
                    node_target_found = True
                    break

            if not node_target_found:
                self.modifications.append(
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

    def load_source_prefab(
        self,
        project_root: Path | str | None = None,
        guid_index: GUIDIndex | None = None,
        _loading_prefabs: set[str] | None = None,
    ) -> bool:
        """Load the source prefab content for a PrefabInstance node.

        This method loads the internal structure of a nested prefab,
        making children and components from the source prefab accessible.

        Uses caching at the Hierarchy level to avoid re-loading and re-parsing
        the same prefab when it's referenced by multiple PrefabInstance nodes.
        For example, if 'board_Upgrade' is used 10 times, it's only loaded once.

        Args:
            project_root: Path to Unity project root. Required if guid_index
                is not provided.
            guid_index: Optional GUIDIndex for resolving GUIDs and script names.
                If not provided, will try to get from _hierarchy or build a
                minimal index from project_root.
            _loading_prefabs: Internal set to prevent circular references.

        Returns:
            True if the prefab was loaded successfully, False otherwise.

        Example:
            >>> node = hierarchy.find("board_CoreUpgrade")
            >>> if node.is_prefab_instance:
            ...     node.load_source_prefab("/path/to/unity/project")
            ...     for child in node.children:
            ...         print(child.name)  # Shows internal structure
        """
        if not self.is_prefab_instance or not self.source_guid:
            return False

        if self.nested_prefab_loaded:
            return True  # Already loaded

        # Initialize loading set for circular reference prevention
        if _loading_prefabs is None:
            _loading_prefabs = set()

        # Check for circular reference
        if self.source_guid in _loading_prefabs:
            return False  # Skip to prevent infinite recursion

        _loading_prefabs.add(self.source_guid)

        try:
            # Resolve project_root if needed
            if project_root is not None:
                project_root = Path(project_root)

            # Get or build guid_index
            if guid_index is None and self._hierarchy is not None:
                guid_index = self._hierarchy.guid_index

            if guid_index is None and project_root is not None:
                # Import here to avoid circular dependency
                from .asset_tracker import build_guid_index

                guid_index = build_guid_index(project_root)

            if guid_index is None:
                return False

            # Resolve source prefab path
            source_path = guid_index.get_path(self.source_guid)
            if source_path is None:
                return False

            # Make path absolute if needed
            resolved_project_root = project_root
            if resolved_project_root is None and self._hierarchy is not None:
                resolved_project_root = self._hierarchy.project_root

            if resolved_project_root is not None and not source_path.is_absolute():
                source_path = resolved_project_root / source_path

            if not source_path.exists():
                return False

            # Get cached hierarchy or load and cache it
            # This is the key optimization: same prefab used N times = 1 load + (N-1) cache hits
            if self._hierarchy is not None:
                source_hierarchy = self._hierarchy._get_or_load_nested_hierarchy(
                    self.source_guid,
                    source_path,
                    guid_index,
                )
            else:
                # No parent hierarchy for caching, load directly
                from .parser import UnityYAMLDocument

                source_doc = UnityYAMLDocument.load_auto(source_path)
                source_hierarchy = Hierarchy.build(source_doc, guid_index=guid_index)

            if source_hierarchy is None:
                return False

            # Merge root objects from source as children of this node
            # Note: Nodes are copied (not shared) so each PrefabInstance has its own tree
            for source_root in source_hierarchy.root_objects:
                self._merge_nested_node(source_root, guid_index, _loading_prefabs)

            self.nested_prefab_loaded = True
            return True

        finally:
            _loading_prefabs.discard(self.source_guid)

    def _merge_nested_node(
        self,
        source_node: HierarchyNode,
        guid_index: GUIDIndex | None,
        loading_prefabs: set[str],
    ) -> None:
        """Merge a node from nested prefab into this node's children.

        This method also applies PrefabInstance modifications to components
        so that ComponentInfo.get_effective_property() returns correct values.

        Args:
            source_node: The node from the source prefab to merge
            guid_index: GUIDIndex for script resolution
            loading_prefabs: Set of GUIDs being loaded (for circular reference prevention)
        """
        # Group modifications by target fileID for component linking
        mods_by_target: dict[int, list[dict[str, Any]]] = {}
        for mod in self.modifications:
            target = mod.get("target", {})
            target_id = target.get("fileID", 0)
            if target_id:
                if target_id not in mods_by_target:
                    mods_by_target[target_id] = []
                mods_by_target[target_id].append(mod)

        # Copy components with modifications linked
        merged_components = []
        for comp in source_node.components:
            comp_mods = mods_by_target.get(comp.file_id)
            merged_components.append(
                ComponentInfo(
                    file_id=comp.file_id,
                    class_id=comp.class_id,
                    class_name=comp.class_name,
                    data=comp.data,
                    is_on_stripped_object=comp.is_on_stripped_object,
                    script_guid=comp.script_guid,
                    script_name=comp.script_name,
                    modifications=comp_mods,
                )
            )

        # Create a copy of the node marked as from nested prefab
        merged_node = HierarchyNode(
            file_id=source_node.file_id,
            name=source_node.name,
            transform_id=source_node.transform_id,
            is_ui=source_node.is_ui,
            parent=self,
            children=[],
            components=merged_components,
            is_prefab_instance=source_node.is_prefab_instance,
            source_guid=source_node.source_guid,
            source_file_id=source_node.source_file_id,
            is_stripped=source_node.is_stripped,
            prefab_instance_id=source_node.prefab_instance_id,
            modifications=list(source_node.modifications),
            is_from_nested_prefab=True,
            nested_prefab_loaded=source_node.nested_prefab_loaded,
            _document=source_node._document,
            _hierarchy=self._hierarchy,
        )

        self.children.append(merged_node)

        # Recursively merge children with inherited modifications
        for child in source_node.children:
            merged_node._merge_nested_child(child, guid_index, loading_prefabs, mods_by_target)

    def _merge_nested_child(
        self,
        source_child: HierarchyNode,
        guid_index: GUIDIndex | None,
        loading_prefabs: set[str],
        mods_by_target: dict[int, list[dict[str, Any]]] | None = None,
    ) -> None:
        """Recursively merge child nodes from nested prefab.

        Args:
            source_child: The child node from source prefab
            guid_index: GUIDIndex for script resolution
            loading_prefabs: Set of GUIDs being loaded (for circular reference prevention)
            mods_by_target: Modifications grouped by target fileID (from parent PrefabInstance)
        """
        # Copy components with modifications linked
        merged_components = []
        for comp in source_child.components:
            comp_mods = mods_by_target.get(comp.file_id) if mods_by_target else None
            merged_components.append(
                ComponentInfo(
                    file_id=comp.file_id,
                    class_id=comp.class_id,
                    class_name=comp.class_name,
                    data=comp.data,
                    is_on_stripped_object=comp.is_on_stripped_object,
                    script_guid=comp.script_guid,
                    script_name=comp.script_name,
                    modifications=comp_mods,
                )
            )

        merged_child = HierarchyNode(
            file_id=source_child.file_id,
            name=source_child.name,
            transform_id=source_child.transform_id,
            is_ui=source_child.is_ui,
            parent=self,
            children=[],
            components=merged_components,
            is_prefab_instance=source_child.is_prefab_instance,
            source_guid=source_child.source_guid,
            source_file_id=source_child.source_file_id,
            is_stripped=source_child.is_stripped,
            prefab_instance_id=source_child.prefab_instance_id,
            modifications=list(source_child.modifications),
            is_from_nested_prefab=True,
            nested_prefab_loaded=source_child.nested_prefab_loaded,
            _document=source_child._document,
            _hierarchy=self._hierarchy,
        )

        self.children.append(merged_child)

        # Recursively merge grandchildren
        for grandchild in source_child.children:
            merged_child._merge_nested_child(grandchild, guid_index, loading_prefabs, mods_by_target)


@dataclass
class Hierarchy:
    """Represents the complete hierarchy of a Unity YAML document.

    Provides methods for traversing, querying, and modifying the hierarchy
    with automatic handling of stripped objects and PrefabInstance relationships.

    Supports loading nested prefab content to make the internal structure of
    PrefabInstances accessible for LLM-friendly navigation.

    Attributes:
        root_objects: List of root-level HierarchyNodes
        guid_index: Optional GUIDIndex for resolving script names
        project_root: Optional project root for loading nested prefabs

    Example:
        >>> from unityflow import build_guid_index, build_hierarchy
        >>> guid_index = build_guid_index("/path/to/unity/project")
        >>> hierarchy = build_hierarchy(
        ...     doc,
        ...     guid_index=guid_index,
        ...     project_root="/path/to/unity/project",
        ...     load_nested_prefabs=True,  # Auto-load nested prefab content
        ... )
        >>> for node in hierarchy.iter_all():
        ...     for comp in node.components:
        ...         # MonoBehaviour now shows script name
        ...         print(comp.type_name)  # "PlayerController" instead of "MonoBehaviour"
        ...     if node.is_prefab_instance:
        ...         # Nested prefab children are now accessible
        ...         for child in node.children:
        ...             print(f"  Nested child: {child.name}")
    """

    root_objects: list[HierarchyNode] = field(default_factory=list)
    guid_index: GUIDIndex | None = field(default=None, repr=False)
    project_root: Path | None = field(default=None, repr=False)
    _document: UnityYAMLDocument | None = field(default=None, repr=False)
    _nodes_by_file_id: dict[int, HierarchyNode] = field(default_factory=dict, repr=False)
    _stripped_transforms: dict[int, int] = field(default_factory=dict, repr=False)
    _stripped_game_objects: dict[int, int] = field(default_factory=dict, repr=False)
    _prefab_instances: dict[int, list[int]] = field(default_factory=dict, repr=False)
    # Cache for loaded nested prefab hierarchies (guid -> Hierarchy)
    # This prevents re-loading and re-parsing the same prefab multiple times
    _nested_prefab_cache: dict[str, Hierarchy] = field(default_factory=dict, repr=False)

    @classmethod
    def build(
        cls,
        doc: UnityYAMLDocument,
        guid_index: GUIDIndex | None = None,
        project_root: Path | str | None = None,
        load_nested_prefabs: bool = False,
    ) -> Hierarchy:
        """Build a hierarchy from a UnityYAMLDocument.

        This method:
        1. Builds indexes for stripped objects and PrefabInstances
        2. Constructs the transform hierarchy (parent-child relationships)
        3. Links components to their GameObjects
        4. Resolves stripped object references to PrefabInstances
        5. Optionally resolves MonoBehaviour script names using guid_index
        6. Optionally loads nested prefab content

        Args:
            doc: The Unity YAML document to build hierarchy from
            guid_index: Optional GUIDIndex for resolving script names.
                When provided, MonoBehaviour components will have their
                script_guid and script_name fields populated.
            project_root: Optional path to Unity project root. Required for
                loading nested prefabs if guid_index doesn't have project_root set.
            load_nested_prefabs: If True, automatically loads the content of
                all nested prefabs (PrefabInstances) so their internal structure
                is accessible through the children property.

        Returns:
            A Hierarchy instance with the complete object tree

        Example:
            >>> guid_index = build_guid_index("/path/to/project")
            >>> hierarchy = Hierarchy.build(
            ...     doc,
            ...     guid_index=guid_index,
            ...     load_nested_prefabs=True,
            ... )
            >>> # Access nested prefab content directly
            >>> prefab_node = hierarchy.find("MyPrefabInstance")
            >>> print(prefab_node.children)  # Shows internal structure
        """
        # Resolve project_root
        resolved_project_root: Path | None = None
        if project_root is not None:
            resolved_project_root = Path(project_root)
        elif guid_index is not None and guid_index.project_root is not None:
            resolved_project_root = guid_index.project_root

        hierarchy = cls(
            _document=doc,
            guid_index=guid_index,
            project_root=resolved_project_root,
        )
        hierarchy._build_indexes(doc)
        hierarchy._build_nodes(doc)
        hierarchy._link_hierarchy()
        hierarchy._set_hierarchy_references()

        # Batch resolve script names (O(1) query instead of O(N))
        hierarchy._batch_resolve_script_names()

        # Optionally load nested prefabs
        if load_nested_prefabs:
            hierarchy.load_all_nested_prefabs()

        return hierarchy

    def _set_hierarchy_references(self) -> None:
        """Set _hierarchy reference on all nodes for nested prefab loading."""
        for node in self.iter_all():
            node._hierarchy = self

    def _get_or_load_nested_hierarchy(
        self,
        source_guid: str,
        source_path: Path,
        guid_index: GUIDIndex | None,
    ) -> Hierarchy | None:
        """Get cached hierarchy or load and cache a nested prefab.

        This method provides caching for nested prefab hierarchies to avoid
        re-loading and re-parsing the same prefab multiple times when it's
        referenced by multiple PrefabInstance nodes.

        Args:
            source_guid: GUID of the source prefab
            source_path: Path to the source prefab file
            guid_index: GUIDIndex for script name resolution

        Returns:
            Cached or newly loaded Hierarchy, or None if loading failed
        """
        # Check cache first
        if source_guid in self._nested_prefab_cache:
            return self._nested_prefab_cache[source_guid]

        # Load and parse the source prefab
        try:
            from .parser import UnityYAMLDocument

            source_doc = UnityYAMLDocument.load_auto(source_path)

            # Build hierarchy for the source prefab
            # Use same guid_index for consistent script name resolution
            source_hierarchy = Hierarchy.build(source_doc, guid_index=guid_index)

            # Cache the hierarchy
            self._nested_prefab_cache[source_guid] = source_hierarchy
            return source_hierarchy
        except Exception:
            return None

    def _build_indexes(self, doc: UnityYAMLDocument) -> None:
        """Build lookup indexes for efficient resolution."""
        # Index stripped objects
        for obj in doc.objects:
            if obj.stripped:
                content = obj.get_content()
                if content is None:
                    continue

                prefab_ref = content.get("m_PrefabInstance", {})
                prefab_id = prefab_ref.get("fileID", 0) if isinstance(prefab_ref, dict) else 0

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

    def _create_component_info(
        self,
        comp_obj: UnityYAMLObject,
        comp_content: dict[str, Any],
        is_on_stripped_object: bool = False,
    ) -> ComponentInfo:
        """Create a ComponentInfo, extracting script GUID for MonoBehaviour.

        For MonoBehaviour components (class_id=114), extracts the script GUID
        from m_Script. Script name resolution is deferred to _batch_resolve_script_names
        for better performance (single batch query instead of N individual queries).

        Args:
            comp_obj: The component's UnityYAMLObject
            comp_content: The component's data dictionary
            is_on_stripped_object: Whether component is on a stripped object

        Returns:
            ComponentInfo with script_guid populated for MonoBehaviour
            (script_name will be resolved later via batch_resolve_script_names)
        """
        script_guid: str | None = None

        # For MonoBehaviour (class_id=114), extract script GUID
        # Script name resolution is deferred to _batch_resolve_script_names
        if comp_obj.class_id == 114:
            script_ref = comp_content.get("m_Script", {})
            if isinstance(script_ref, dict):
                script_guid = script_ref.get("guid")

        return ComponentInfo(
            file_id=comp_obj.file_id,
            class_id=comp_obj.class_id,
            class_name=comp_obj.class_name,
            data=comp_content,
            is_on_stripped_object=is_on_stripped_object,
            script_guid=script_guid,
            script_name=None,  # Resolved later via _batch_resolve_script_names
        )

    def _batch_resolve_script_names(self) -> None:
        """Batch resolve all script GUIDs to names using a single query.

        This method collects all script GUIDs from MonoBehaviour components
        across all nodes and resolves them in a single batch query, which is
        significantly faster than resolving each GUID individually.

        Performance improvement: O(1) query instead of O(N) queries.
        Typical: 1600ms -> 80ms for prefabs with 100+ MonoBehaviour components.
        """
        if not self.guid_index:
            return

        # Collect all script GUIDs from all components
        all_guids: set[str] = set()
        for node in self.iter_all():
            for comp in node.components:
                if comp.script_guid:
                    all_guids.add(comp.script_guid)

        if not all_guids:
            return

        # Batch resolve all GUIDs at once
        resolved_names = self.guid_index.batch_resolve_names(all_guids)

        # Update component script_name fields
        for node in self.iter_all():
            for comp in node.components:
                if comp.script_guid and comp.script_guid in resolved_names:
                    # ComponentInfo is a dataclass, need to use object.__setattr__
                    # if it's frozen, but it's not frozen, so direct assignment works
                    comp.script_name = resolved_names[comp.script_guid]

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
                    go_id = go_ref.get("fileID", 0) if isinstance(go_ref, dict) else 0
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
                        comp_id = comp_ref.get("fileID", 0) if isinstance(comp_ref, dict) else 0
                        if comp_id and comp_id != transform_id:
                            comp_obj = doc.get_by_file_id(comp_id)
                            if comp_obj:
                                comp_content = comp_obj.get_content() or {}
                                node.components.append(self._create_component_info(comp_obj, comp_content))

        # Create nodes for PrefabInstances
        for obj in doc.objects:
            if obj.class_id == 1001:  # PrefabInstance
                content = obj.get_content()
                if content is None:
                    continue

                # Get source prefab info
                source = content.get("m_SourcePrefab", {})
                source_guid = source.get("guid", "") if isinstance(source, dict) else ""
                source_file_id = source.get("fileID", 0) if isinstance(source, dict) else 0

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
                is_ui = False
                stripped_ids = self._prefab_instances.get(obj.file_id, [])
                for stripped_id in stripped_ids:
                    stripped_obj = doc.get_by_file_id(stripped_id)
                    if stripped_obj and stripped_obj.class_id in (4, 224):
                        # Check if this is the root (parent is outside the prefab)
                        transform_id = stripped_id
                        # RectTransform (224) means UI
                        is_ui = stripped_obj.class_id == 224
                        break

                node = HierarchyNode(
                    file_id=obj.file_id,
                    name=name,
                    transform_id=transform_id,
                    is_ui=is_ui,
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
                            if (
                                comp_obj.class_id
                                not in (
                                    1,
                                    4,
                                    224,
                                    1001,
                                )
                                and not comp_obj.stripped
                            ):
                                comp_content = comp_obj.get_content()
                                if comp_content:
                                    go_ref = comp_content.get("m_GameObject", {})
                                    go_id = go_ref.get("fileID", 0) if isinstance(go_ref, dict) else 0
                                    if go_id == stripped_id:
                                        node.components.append(
                                            self._create_component_info(
                                                comp_obj,
                                                comp_content,
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
                    father_id = father.get("fileID", 0) if isinstance(father, dict) else 0
                    if father_id:
                        transform_parents[obj.file_id] = father_id

        # Also check PrefabInstance m_TransformParent
        for obj in doc.objects:
            if obj.class_id == 1001:
                content = obj.get_content()
                if content:
                    modification = content.get("m_Modification", {})
                    parent_ref = modification.get("m_TransformParent", {})
                    parent_id = parent_ref.get("fileID", 0) if isinstance(parent_ref, dict) else 0

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

        # Sort children based on Transform's m_Children order
        self._sort_children_by_transform_order(doc)

        # Collect root objects
        for node in self._nodes_by_file_id.values():
            if node.parent is None:
                self.root_objects.append(node)

    def _sort_children_by_transform_order(self, doc: UnityYAMLDocument) -> None:
        """Sort children of each node based on Transform's m_Children order.

        Unity Editor displays children in the order specified by the parent
        Transform's m_Children array. This method ensures HierarchyNode.children
        matches that order.

        Args:
            doc: The Unity YAML document
        """
        for node in self._nodes_by_file_id.values():
            if not node.children or not node.transform_id:
                continue

            transform_obj = doc.get_by_file_id(node.transform_id)
            if transform_obj is None:
                continue

            content = transform_obj.get_content()
            if content is None:
                continue

            m_children = content.get("m_Children", [])
            if not m_children:
                continue

            # Build order map: child_transform_id -> index
            order_map: dict[int, int] = {}
            for idx, child_ref in enumerate(m_children):
                if isinstance(child_ref, dict):
                    child_id = child_ref.get("fileID", 0)
                    if child_id:
                        order_map[child_id] = idx

            # Sort children by their transform_id's position in m_Children
            # Nodes not in m_Children go to the end
            node.children.sort(key=lambda c: order_map.get(c.transform_id, len(m_children)))

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

    def load_all_nested_prefabs(
        self,
        recursive: bool = True,
    ) -> int:
        """Load all nested prefab content in the hierarchy.

        This method finds all PrefabInstance nodes and loads their source
        prefab content, making the internal structure accessible through
        the children property.

        Args:
            recursive: If True (default), also loads nested prefabs within
                the loaded prefabs (up to circular reference detection).

        Returns:
            The number of prefabs successfully loaded.

        Example:
            >>> hierarchy = build_hierarchy(doc, guid_index=guid_index)
            >>> count = hierarchy.load_all_nested_prefabs()
            >>> print(f"Loaded {count} nested prefabs")
            >>>
            >>> # Now all PrefabInstance nodes have children populated
            >>> for node in hierarchy.iter_all():
            ...     if node.is_prefab_instance and node.nested_prefab_loaded:
            ...         print(f"{node.name}: {len(node.children)} children")
        """
        if self.guid_index is None and self.project_root is None:
            return 0

        loaded_count = 0
        loading_prefabs: set[str] = set()

        # Find all PrefabInstance nodes
        prefab_nodes = [node for node in self.iter_all() if node.is_prefab_instance and not node.nested_prefab_loaded]

        for node in prefab_nodes:
            if node.load_source_prefab(
                project_root=self.project_root,
                guid_index=self.guid_index,
                _loading_prefabs=loading_prefabs,
            ):
                loaded_count += 1

                # Recursively load nested prefabs in the newly loaded content
                if recursive:
                    loaded_count += self._load_nested_in_children(node, loading_prefabs)

        return loaded_count

    def _load_nested_in_children(
        self,
        node: HierarchyNode,
        loading_prefabs: set[str],
    ) -> int:
        """Recursively load nested prefabs in children.

        Args:
            node: The node whose children to check
            loading_prefabs: Set of GUIDs being loaded (for circular reference prevention)

        Returns:
            Number of additional prefabs loaded
        """
        loaded_count = 0

        for child in node.children:
            if child.is_prefab_instance and not child.nested_prefab_loaded:
                if child.load_source_prefab(
                    project_root=self.project_root,
                    guid_index=self.guid_index,
                    _loading_prefabs=loading_prefabs,
                ):
                    loaded_count += 1
                    loaded_count += self._load_nested_in_children(child, loading_prefabs)
            elif child.children:
                loaded_count += self._load_nested_in_children(child, loading_prefabs)

        return loaded_count

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
                    go_id = go_ref.get("fileID", 0) if isinstance(go_ref, dict) else 0
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


def build_hierarchy(
    doc: UnityYAMLDocument,
    guid_index: GUIDIndex | None = None,
    project_root: Path | str | None = None,
    load_nested_prefabs: bool = False,
) -> Hierarchy:
    """Build a hierarchy from a UnityYAMLDocument.

    Convenience function that calls Hierarchy.build().

    This is the main entry point for building LLM-friendly hierarchies with:
    - Automatic script name resolution for MonoBehaviour components
    - Optional nested prefab content loading

    Args:
        doc: The Unity YAML document
        guid_index: Optional GUIDIndex for resolving script names.
            When provided, MonoBehaviour components will have their
            script_guid and script_name fields populated.
        project_root: Optional path to Unity project root. Required for
            loading nested prefabs if guid_index doesn't have project_root set.
        load_nested_prefabs: If True, automatically loads the content of
            all nested prefabs (PrefabInstances) so their internal structure
            is accessible through the children property.

    Returns:
        A Hierarchy instance

    Example:
        >>> from unityflow import build_guid_index, build_hierarchy, UnityYAMLDocument
        >>> guid_index = build_guid_index("/path/to/unity/project")
        >>> doc = UnityYAMLDocument.load("MyPrefab.prefab")
        >>>
        >>> # Basic usage with script name resolution
        >>> hierarchy = build_hierarchy(doc, guid_index=guid_index)
        >>> for node in hierarchy.iter_all():
        ...     for comp in node.components:
        ...         if comp.script_name:
        ...             print(f"{node.name}: {comp.script_name}")
        >>>
        >>> # Full LLM-friendly usage with nested prefab loading
        >>> hierarchy = build_hierarchy(
        ...     doc,
        ...     guid_index=guid_index,
        ...     load_nested_prefabs=True,
        ... )
        >>> # Now PrefabInstances show their internal structure
        >>> prefab = hierarchy.find("board_CoreUpgrade")
        >>> if prefab and prefab.is_prefab_instance:
        ...     for child in prefab.children:
        ...         print(f"  {child.name}")
    """
    return Hierarchy.build(
        doc,
        guid_index=guid_index,
        project_root=project_root,
        load_nested_prefabs=load_nested_prefabs,
    )


def resolve_game_object_for_component(doc: UnityYAMLDocument, component_file_id: int) -> int:
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
            prefab_id = prefab_ref.get("fileID", 0) if isinstance(prefab_ref, dict) else 0
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

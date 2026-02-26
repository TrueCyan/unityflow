"""Semantic diff for Unity YAML files.

Provides property-level diff by comparing Unity YAML documents
semantically rather than as text lines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from unityflow.hierarchy import Hierarchy, HierarchyNode
    from unityflow.parser import UnityYAMLDocument, UnityYAMLObject

MatchKey = tuple[str, str, str, int]


class ChangeType(Enum):
    """Type of change detected in a property."""

    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"


@dataclass
class PropertyChange:
    """Property-level change information.

    Represents a single property change between two Unity YAML documents.
    """

    # Location information
    file_id: int
    """fileID of the object containing this property."""

    class_name: str
    """Class name of the object (e.g., 'Transform', 'MonoBehaviour')."""

    property_path: str
    """Dot-separated path to the property (e.g., 'm_LocalPosition.x')."""

    # Change information
    change_type: ChangeType
    """Type of change (added, removed, modified)."""

    old_value: Any | None
    """Value in the left/old document (None if added)."""

    new_value: Any | None
    """Value in the right/new document (None if removed)."""

    # Optional context
    game_object_name: str | None = None
    """Name of the GameObject this component belongs to (if available)."""

    hierarchy_path: str | None = None
    """Hierarchy path of the object (e.g., 'Root/Child')."""

    @property
    def full_path(self) -> str:
        """Full path including class name and property path."""
        return f"{self.class_name}.{self.property_path}"

    def __repr__(self) -> str:
        return f"PropertyChange({self.change_type.value}: {self.full_path})"


@dataclass
class ObjectChange:
    """Object-level change information.

    Represents an entire object (GameObject, Component, etc.) being added or removed.
    """

    file_id: int
    """fileID of the added/removed object."""

    class_name: str
    """Class name of the object."""

    change_type: ChangeType
    """Type of change (added or removed only)."""

    data: dict[str, Any] | None = None
    """Object data (available for added objects)."""

    game_object_name: str | None = None
    """Name of the GameObject (if this is a GameObject or its component)."""

    hierarchy_path: str | None = None
    """Hierarchy path of the object (e.g., 'Root/Child')."""

    def __repr__(self) -> str:
        return f"ObjectChange({self.change_type.value}: {self.class_name} fileID={self.file_id})"


@dataclass
class SemanticDiffResult:
    """Result of a semantic diff operation.

    Contains all changes between two Unity YAML documents at both
    object and property levels.
    """

    property_changes: list[PropertyChange] = field(default_factory=list)
    """List of property-level changes."""

    object_changes: list[ObjectChange] = field(default_factory=list)
    """List of object-level changes (added/removed objects)."""

    @property
    def has_changes(self) -> bool:
        """Whether any changes were detected."""
        return len(self.property_changes) > 0 or len(self.object_changes) > 0

    @property
    def added_count(self) -> int:
        """Count of added properties and objects."""
        prop_count = sum(1 for c in self.property_changes if c.change_type == ChangeType.ADDED)
        obj_count = sum(1 for c in self.object_changes if c.change_type == ChangeType.ADDED)
        return prop_count + obj_count

    @property
    def removed_count(self) -> int:
        """Count of removed properties and objects."""
        prop_count = sum(1 for c in self.property_changes if c.change_type == ChangeType.REMOVED)
        obj_count = sum(1 for c in self.object_changes if c.change_type == ChangeType.REMOVED)
        return prop_count + obj_count

    @property
    def modified_count(self) -> int:
        """Count of modified properties."""
        return sum(1 for c in self.property_changes if c.change_type == ChangeType.MODIFIED)

    def get_changes_for_object(self, file_id: int) -> list[PropertyChange]:
        """Get all property changes for a specific object."""
        return [c for c in self.property_changes if c.file_id == file_id]


def _get_game_object_name(doc: UnityYAMLDocument, obj: UnityYAMLObject) -> str | None:
    """Get the GameObject name for an object or its component."""
    # If this is a GameObject, get its name directly
    if obj.class_name == "GameObject":
        content = obj.get_content()
        if content:
            return content.get("m_Name")
        return None

    # For components, find the parent GameObject
    content = obj.get_content()
    if content and "m_GameObject" in content:
        go_ref = content["m_GameObject"]
        if isinstance(go_ref, dict) and "fileID" in go_ref:
            go_id = go_ref["fileID"]
            go_obj = doc.get_by_file_id(go_id)
            if go_obj:
                go_content = go_obj.get_content()
                if go_content:
                    return go_content.get("m_Name")

    return None


def _disambiguated_node_name(node: HierarchyNode, siblings: list[HierarchyNode]) -> str:
    same_name = [s for s in siblings if s.name == node.name]
    if len(same_name) > 1:
        idx = same_name.index(node)
        return f"{node.name}[{idx}]"
    return node.name


def _build_match_map(
    doc: UnityYAMLDocument,
    hierarchy: Hierarchy,
) -> tuple[dict[MatchKey, int], dict[int, MatchKey]]:
    key_to_id: dict[MatchKey, int] = {}
    id_to_key: dict[int, MatchKey] = {}
    path_cache: dict[int, str] = {}

    def _node_path(node: HierarchyNode) -> str:
        if node.file_id in path_cache:
            return path_cache[node.file_id]

        siblings = hierarchy.root_objects if node.parent is None else node.parent.children
        name = _disambiguated_node_name(node, siblings)

        if node.parent is None:
            result = name
        else:
            result = f"{_node_path(node.parent)}/{name}"

        path_cache[node.file_id] = result
        return result

    def _register(key: MatchKey, file_id: int) -> None:
        key_to_id[key] = file_id
        id_to_key[file_id] = key

    for node in hierarchy.iter_all():
        path = _node_path(node)

        node_class = "PrefabInstance" if node.is_prefab_instance else "GameObject"
        _register((path, node_class, "", 0), node.file_id)

        if node.transform_id:
            transform_class = "RectTransform" if node.is_ui else "Transform"
            _register((path, transform_class, "", 0), node.transform_id)

        type_counts: dict[tuple[str, str], int] = {}
        for comp in node.components:
            type_name = comp.type_name
            guid = comp.script_guid or ""
            idx = type_counts.get((type_name, guid), 0)
            type_counts[(type_name, guid)] = idx + 1
            _register((path, type_name, guid, idx), comp.file_id)

    return key_to_id, id_to_key


def _compare_values(
    old_value: Any,
    new_value: Any,
    path: str,
    file_id: int,
    class_name: str,
    game_object_name: str | None,
    changes: list[PropertyChange],
) -> None:
    """Recursively compare two values and collect changes.

    Args:
        old_value: Value from the old/left document
        new_value: Value from the new/right document
        path: Current property path
        file_id: fileID of the containing object
        class_name: Class name of the containing object
        game_object_name: Name of the parent GameObject
        changes: List to append changes to
    """
    # Both None or equal - no change
    if old_value == new_value:
        return

    # Handle None cases
    if old_value is None:
        changes.append(
            PropertyChange(
                file_id=file_id,
                class_name=class_name,
                property_path=path,
                change_type=ChangeType.ADDED,
                old_value=None,
                new_value=new_value,
                game_object_name=game_object_name,
            )
        )
        return

    if new_value is None:
        changes.append(
            PropertyChange(
                file_id=file_id,
                class_name=class_name,
                property_path=path,
                change_type=ChangeType.REMOVED,
                old_value=old_value,
                new_value=None,
                game_object_name=game_object_name,
            )
        )
        return

    # Both are dicts - recurse
    if isinstance(old_value, dict) and isinstance(new_value, dict):
        all_keys = set(old_value.keys()) | set(new_value.keys())
        for key in sorted(all_keys):
            child_path = f"{path}.{key}" if path else key
            _compare_values(
                old_value.get(key),
                new_value.get(key),
                child_path,
                file_id,
                class_name,
                game_object_name,
                changes,
            )
        return

    # Both are lists - compare element by element
    if isinstance(old_value, list) and isinstance(new_value, list):
        # For fileID reference lists (like m_Children), compare by fileID
        if _is_file_id_list(old_value) and _is_file_id_list(new_value):
            _compare_file_id_lists(old_value, new_value, path, file_id, class_name, game_object_name, changes)
            return

        if _is_modification_list(old_value) and _is_modification_list(new_value):
            _compare_modification_lists(old_value, new_value, path, file_id, class_name, game_object_name, changes)
            return

        # For other lists, compare by index
        max_len = max(len(old_value), len(new_value))
        for i in range(max_len):
            child_path = f"{path}[{i}]"
            old_item = old_value[i] if i < len(old_value) else None
            new_item = new_value[i] if i < len(new_value) else None
            _compare_values(
                old_item,
                new_item,
                child_path,
                file_id,
                class_name,
                game_object_name,
                changes,
            )
        return

    # Different types or primitive values that differ
    changes.append(
        PropertyChange(
            file_id=file_id,
            class_name=class_name,
            property_path=path,
            change_type=ChangeType.MODIFIED,
            old_value=old_value,
            new_value=new_value,
            game_object_name=game_object_name,
        )
    )


def _is_file_id_list(value: list[Any]) -> bool:
    """Check if a list contains only fileID references."""
    if not value:
        return False
    return all(isinstance(item, dict) and "fileID" in item and len(item) == 1 for item in value)


def _is_modification_list(value: list[Any]) -> bool:
    if not value:
        return True
    return all(isinstance(item, dict) and "target" in item and "propertyPath" in item for item in value)


def _modification_key(mod: dict[str, Any]) -> tuple[int, str]:
    target = mod.get("target", {})
    file_id = target.get("fileID", 0) if isinstance(target, dict) else 0
    return (file_id, mod.get("propertyPath", ""))


def _compare_modification_lists(
    old_list: list[dict[str, Any]],
    new_list: list[dict[str, Any]],
    path: str,
    file_id: int,
    class_name: str,
    game_object_name: str | None,
    changes: list[PropertyChange],
) -> None:
    old_by_key = {_modification_key(m): m for m in old_list}
    new_by_key = {_modification_key(m): m for m in new_list}

    all_keys = set(old_by_key.keys()) | set(new_by_key.keys())
    for key in sorted(all_keys):
        old_mod = old_by_key.get(key)
        new_mod = new_by_key.get(key)
        key_label = f"target.fileID={key[0]},propertyPath={key[1]}"

        if old_mod is None:
            changes.append(
                PropertyChange(
                    file_id=file_id,
                    class_name=class_name,
                    property_path=f"{path}[{key_label}]",
                    change_type=ChangeType.ADDED,
                    old_value=None,
                    new_value=new_mod,
                    game_object_name=game_object_name,
                )
            )
        elif new_mod is None:
            changes.append(
                PropertyChange(
                    file_id=file_id,
                    class_name=class_name,
                    property_path=f"{path}[{key_label}]",
                    change_type=ChangeType.REMOVED,
                    old_value=old_mod,
                    new_value=None,
                    game_object_name=game_object_name,
                )
            )
        elif old_mod != new_mod:
            _compare_values(
                old_mod,
                new_mod,
                f"{path}[{key_label}]",
                file_id,
                class_name,
                game_object_name,
                changes,
            )


def _compare_file_id_lists(
    old_list: list[dict[str, Any]],
    new_list: list[dict[str, Any]],
    path: str,
    file_id: int,
    class_name: str,
    game_object_name: str | None,
    changes: list[PropertyChange],
) -> None:
    """Compare lists of fileID references (like m_Children).

    Order is ignored - only additions and removals are tracked.
    """
    old_ids = {item["fileID"] for item in old_list}
    new_ids = {item["fileID"] for item in new_list}

    added_ids = new_ids - old_ids
    removed_ids = old_ids - new_ids

    for added_id in sorted(added_ids):
        changes.append(
            PropertyChange(
                file_id=file_id,
                class_name=class_name,
                property_path=f"{path}[fileID={added_id}]",
                change_type=ChangeType.ADDED,
                old_value=None,
                new_value={"fileID": added_id},
                game_object_name=game_object_name,
            )
        )

    for removed_id in sorted(removed_ids):
        changes.append(
            PropertyChange(
                file_id=file_id,
                class_name=class_name,
                property_path=f"{path}[fileID={removed_id}]",
                change_type=ChangeType.REMOVED,
                old_value={"fileID": removed_id},
                new_value=None,
                game_object_name=game_object_name,
            )
        )


def _remap_file_ids(data: Any, remap: dict[int, int]) -> Any:
    if isinstance(data, dict):
        if "fileID" in data and len(data) == 1:
            old_id = data["fileID"]
            return {"fileID": remap.get(old_id, old_id)}
        return {k: _remap_file_ids(v, remap) for k, v in data.items()}
    if isinstance(data, list):
        return [_remap_file_ids(item, remap) for item in data]
    return data


def _compare_matched_objects(
    left_doc: UnityYAMLDocument,
    right_doc: UnityYAMLDocument,
    left_file_id: int,
    right_file_id: int,
    hierarchy_path: str | None,
    result: SemanticDiffResult,
    fileid_remap: dict[int, int] | None = None,
) -> None:
    left_obj = left_doc.get_by_file_id(left_file_id)
    right_obj = right_doc.get_by_file_id(right_file_id)

    if left_obj is None or right_obj is None:
        return

    left_content = left_obj.get_content() or {}
    right_content = right_obj.get_content() or {}

    if fileid_remap:
        left_content = _remap_file_ids(left_content, fileid_remap)

    game_object_name = _get_game_object_name(right_doc, right_obj)

    start = len(result.property_changes)
    _compare_values(
        left_content,
        right_content,
        "",
        right_file_id,
        left_obj.class_name,
        game_object_name,
        result.property_changes,
    )
    for change in result.property_changes[start:]:
        change.hierarchy_path = hierarchy_path


def semantic_diff(
    left_doc: UnityYAMLDocument,
    right_doc: UnityYAMLDocument,
    project_root: str | Path | None = None,
) -> SemanticDiffResult:
    """Perform a semantic 2-way diff between two Unity YAML documents.

    Compares documents at the property level, identifying:
    - Added/removed objects (GameObjects, Components, etc.)
    - Added/removed/modified properties within objects

    Uses hierarchy path matching to pair objects by their position in the
    GameObject tree, so structurally identical prefabs with different fileIDs
    produce property-level diffs instead of wholesale add/remove.

    Args:
        left_doc: The left/old/base document
        right_doc: The right/new/modified document
        project_root: Unity project root for normalization (optional)

    Returns:
        SemanticDiffResult containing all detected changes
    """
    if project_root is not None:
        from unityflow.normalizer import UnityPrefabNormalizer

        normalizer = UnityPrefabNormalizer(project_root=project_root)
        normalizer.normalize_document(left_doc)
        normalizer.normalize_document(right_doc)

    from unityflow.asset_tracker import get_lazy_guid_index
    from unityflow.hierarchy import Hierarchy

    guid_index = None
    if project_root:
        guid_index = get_lazy_guid_index(Path(project_root), include_packages=True)

    result = SemanticDiffResult()

    left_hierarchy = Hierarchy.build(left_doc, guid_index=guid_index)
    right_hierarchy = Hierarchy.build(right_doc, guid_index=guid_index)

    left_key_to_id, left_id_to_key = _build_match_map(left_doc, left_hierarchy)
    right_key_to_id, right_id_to_key = _build_match_map(right_doc, right_hierarchy)

    left_keys = set(left_key_to_id.keys())
    right_keys = set(right_key_to_id.keys())

    matched_keys = left_keys & right_keys
    removed_keys = left_keys - right_keys
    added_keys = right_keys - left_keys

    left_unmatched_by_id = {left_key_to_id[k]: k for k in removed_keys}
    right_unmatched_by_id = {right_key_to_id[k]: k for k in added_keys}
    fileid_rematched = set(left_unmatched_by_id.keys()) & set(right_unmatched_by_id.keys())
    for file_id in fileid_rematched:
        removed_keys.discard(left_unmatched_by_id[file_id])
        added_keys.discard(right_unmatched_by_id[file_id])

    for key in sorted(removed_keys):
        file_id = left_key_to_id[key]
        obj = left_doc.get_by_file_id(file_id)
        if obj:
            result.object_changes.append(
                ObjectChange(
                    file_id=file_id,
                    class_name=key[1],
                    change_type=ChangeType.REMOVED,
                    data=obj.data,
                    game_object_name=_get_game_object_name(left_doc, obj),
                    hierarchy_path=key[0],
                )
            )

    for key in sorted(added_keys):
        file_id = right_key_to_id[key]
        obj = right_doc.get_by_file_id(file_id)
        if obj:
            result.object_changes.append(
                ObjectChange(
                    file_id=file_id,
                    class_name=key[1],
                    change_type=ChangeType.ADDED,
                    data=obj.data,
                    game_object_name=_get_game_object_name(right_doc, obj),
                    hierarchy_path=key[0],
                )
            )

    fileid_remap: dict[int, int] = {}
    for key in matched_keys:
        fileid_remap[left_key_to_id[key]] = right_key_to_id[key]

    for key in sorted(matched_keys):
        left_file_id = left_key_to_id[key]
        right_file_id = right_key_to_id[key]
        _compare_matched_objects(left_doc, right_doc, left_file_id, right_file_id, key[0], result, fileid_remap)

    for file_id in sorted(fileid_rematched):
        right_key = right_unmatched_by_id[file_id]
        _compare_matched_objects(left_doc, right_doc, file_id, file_id, right_key[0], result)

    left_all_ids = left_doc.get_all_file_ids()
    right_all_ids = right_doc.get_all_file_ids()

    left_mapped_ids = set(left_id_to_key.keys())
    right_mapped_ids = set(right_id_to_key.keys())

    left_unmapped = left_all_ids - left_mapped_ids
    right_unmapped = right_all_ids - right_mapped_ids

    common_unmapped = left_unmapped & right_unmapped
    removed_unmapped = left_unmapped - right_unmapped
    added_unmapped = right_unmapped - left_unmapped

    for file_id in sorted(removed_unmapped):
        obj = left_doc.get_by_file_id(file_id)
        if obj:
            result.object_changes.append(
                ObjectChange(
                    file_id=file_id,
                    class_name=obj.class_name,
                    change_type=ChangeType.REMOVED,
                    data=obj.data,
                    game_object_name=_get_game_object_name(left_doc, obj),
                )
            )

    for file_id in sorted(added_unmapped):
        obj = right_doc.get_by_file_id(file_id)
        if obj:
            result.object_changes.append(
                ObjectChange(
                    file_id=file_id,
                    class_name=obj.class_name,
                    change_type=ChangeType.ADDED,
                    data=obj.data,
                    game_object_name=_get_game_object_name(right_doc, obj),
                )
            )

    for file_id in sorted(common_unmapped):
        _compare_matched_objects(left_doc, right_doc, file_id, file_id, None, result)

    return result

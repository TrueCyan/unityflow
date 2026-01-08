"""Semantic diff for Unity YAML files.

Provides property-level diff by comparing Unity YAML documents
semantically rather than as text lines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from unityflow.parser import UnityYAMLDocument, UnityYAMLObject


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


def semantic_diff(
    left_doc: UnityYAMLDocument,
    right_doc: UnityYAMLDocument,
) -> SemanticDiffResult:
    """Perform a semantic 2-way diff between two Unity YAML documents.

    Compares documents at the property level, identifying:
    - Added/removed objects (GameObjects, Components, etc.)
    - Added/removed/modified properties within objects

    Args:
        left_doc: The left/old/base document
        right_doc: The right/new/modified document

    Returns:
        SemanticDiffResult containing all detected changes
    """
    result = SemanticDiffResult()

    # Collect all fileIDs
    left_ids = left_doc.get_all_file_ids()
    right_ids = right_doc.get_all_file_ids()

    # Find added and removed objects
    added_ids = right_ids - left_ids
    removed_ids = left_ids - right_ids
    common_ids = left_ids & right_ids

    # Process removed objects
    for file_id in sorted(removed_ids):
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

    # Process added objects
    for file_id in sorted(added_ids):
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

    # Compare common objects
    for file_id in sorted(common_ids):
        left_obj = left_doc.get_by_file_id(file_id)
        right_obj = right_doc.get_by_file_id(file_id)

        if left_obj is None or right_obj is None:
            continue

        # Get content under root key
        left_content = left_obj.get_content() or {}
        right_content = right_obj.get_content() or {}

        # Get GameObject name for context
        game_object_name = _get_game_object_name(right_doc, right_obj)

        # Compare all properties
        _compare_values(
            left_content,
            right_content,
            "",
            file_id,
            left_obj.class_name,
            game_object_name,
            result.property_changes,
        )

    return result

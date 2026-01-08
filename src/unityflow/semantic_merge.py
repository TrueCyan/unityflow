"""Semantic three-way merge for Unity YAML files.

Provides property-level merge by comparing Unity YAML documents
semantically rather than as text lines. This enables accurate
conflict detection at the property level.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from unityflow.parser import UnityYAMLDocument, UnityYAMLObject


class ConflictType(Enum):
    """Type of conflict detected during merge."""

    BOTH_MODIFIED = "both_modified"
    """Both sides modified the same property to different values."""

    DELETE_MODIFY = "delete_modify"
    """One side deleted, the other modified."""

    BOTH_ADDED = "both_added"
    """Both sides added the same property with different values."""

    OBJECT_CONFLICT = "object_conflict"
    """Object-level conflict (e.g., both added same fileID)."""


@dataclass
class PropertyConflict:
    """Property-level conflict information.

    Represents a conflict where both ours and theirs changed the same
    property from the base version to different values.
    """

    # Location information
    file_id: int
    """fileID of the object containing this property."""

    class_name: str
    """Class name of the object (e.g., 'Transform', 'MonoBehaviour')."""

    property_path: str
    """Dot-separated path to the property (e.g., 'm_LocalPosition.x')."""

    # Value information
    base_value: Any | None
    """Value in the base document."""

    ours_value: Any | None
    """Value in our document."""

    theirs_value: Any | None
    """Value in their document."""

    # Conflict type
    conflict_type: ConflictType
    """Type of conflict."""

    # Optional context
    game_object_name: str | None = None
    """Name of the GameObject this component belongs to (if available)."""

    @property
    def full_path(self) -> str:
        """Full path including class name and property path."""
        return f"{self.class_name}.{self.property_path}"

    def __repr__(self) -> str:
        return f"PropertyConflict({self.conflict_type.value}: {self.full_path})"


@dataclass
class ObjectConflict:
    """Object-level conflict information."""

    file_id: int
    """fileID of the conflicting object."""

    class_name: str
    """Class name of the object."""

    conflict_type: ConflictType
    """Type of conflict."""

    description: str
    """Human-readable description of the conflict."""

    def __repr__(self) -> str:
        return f"ObjectConflict({self.conflict_type.value}: {self.class_name} fileID={self.file_id})"


@dataclass
class AutoMergedChange:
    """Information about an automatically merged change."""

    file_id: int
    """fileID of the affected object."""

    class_name: str
    """Class name of the object."""

    property_path: str
    """Path to the property that was merged."""

    source: str
    """Which side the change came from ('ours' or 'theirs')."""

    value: Any
    """The value that was applied."""

    def __repr__(self) -> str:
        return f"AutoMergedChange({self.source}: {self.class_name}.{self.property_path})"


@dataclass
class SemanticMergeResult:
    """Result of a semantic three-way merge operation.

    Contains the merged document and information about conflicts
    and auto-merged changes.
    """

    merged_document: UnityYAMLDocument
    """The merged document (may contain unresolved conflicts)."""

    property_conflicts: list[PropertyConflict] = field(default_factory=list)
    """List of property-level conflicts."""

    object_conflicts: list[ObjectConflict] = field(default_factory=list)
    """List of object-level conflicts."""

    auto_merged: list[AutoMergedChange] = field(default_factory=list)
    """List of changes that were automatically merged."""

    @property
    def has_conflicts(self) -> bool:
        """Whether any conflicts were detected."""
        return len(self.property_conflicts) > 0 or len(self.object_conflicts) > 0

    @property
    def conflict_count(self) -> int:
        """Total number of conflicts."""
        return len(self.property_conflicts) + len(self.object_conflicts)

    @property
    def conflicts(self) -> list[PropertyConflict | ObjectConflict]:
        """All conflicts (property and object level)."""
        return self.property_conflicts + self.object_conflicts  # type: ignore[return-value]

    def get_conflicts_for_object(self, file_id: int) -> list[PropertyConflict]:
        """Get all property conflicts for a specific object."""
        return [c for c in self.property_conflicts if c.file_id == file_id]


def _get_game_object_name(doc: UnityYAMLDocument, obj: UnityYAMLObject) -> str | None:
    """Get the GameObject name for an object or its component."""
    if obj.class_name == "GameObject":
        content = obj.get_content()
        if content:
            return content.get("m_Name")
        return None

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


def _deep_copy_document(doc: UnityYAMLDocument) -> UnityYAMLDocument:
    """Create a deep copy of a document."""
    from unityflow.parser import UnityYAMLDocument, UnityYAMLObject

    new_doc = UnityYAMLDocument()
    new_doc.source_path = doc.source_path

    for obj in doc.objects:
        new_obj = UnityYAMLObject(
            class_id=obj.class_id,
            file_id=obj.file_id,
            data=copy.deepcopy(obj.data),
            stripped=obj.stripped,
        )
        new_doc.objects.append(new_obj)

    return new_doc


def _set_nested_value(data: dict[str, Any], path: str, value: Any) -> bool:
    """Set a value at a nested path in a dictionary.

    Args:
        data: The dictionary to modify
        path: Dot-separated path (e.g., 'm_LocalPosition.x')
        value: The value to set

    Returns:
        True if successful, False if path was invalid
    """
    if not path:
        return False

    parts = path.split(".")
    current = data

    # Navigate to the parent of the target
    for part in parts[:-1]:
        # Handle array index notation like "items[0]"
        if "[" in part:
            key, idx_str = part.rstrip("]").split("[")
            if key not in current or not isinstance(current[key], list):
                return False
            try:
                idx = int(idx_str)
                current = current[key][idx]
            except (ValueError, IndexError):
                return False
        else:
            if part not in current or not isinstance(current[part], dict):
                return False
            current = current[part]

    # Set the final value
    final_key = parts[-1]
    if "[" in final_key:
        key, idx_str = final_key.rstrip("]").split("[")
        if key not in current or not isinstance(current[key], list):
            return False
        try:
            idx = int(idx_str)
            current[key][idx] = value
            return True
        except (ValueError, IndexError):
            return False
    else:
        current[final_key] = value
        return True


def _get_nested_value(data: dict[str, Any], path: str) -> tuple[Any, bool]:
    """Get a value at a nested path in a dictionary.

    Args:
        data: The dictionary to read from
        path: Dot-separated path (e.g., 'm_LocalPosition.x')

    Returns:
        Tuple of (value, found) where found is True if the path exists
    """
    if not path:
        return data, True

    parts = path.split(".")
    current = data

    for part in parts:
        if not isinstance(current, dict):
            return None, False

        # Handle array index notation
        if "[" in part:
            key, idx_str = part.rstrip("]").split("[")
            if key not in current or not isinstance(current[key], list):
                return None, False
            try:
                idx = int(idx_str)
                current = current[key][idx]
            except (ValueError, IndexError):
                return None, False
        else:
            if part not in current:
                return None, False
            current = current[part]

    return current, True


def _merge_values(
    base_value: Any,
    ours_value: Any,
    theirs_value: Any,
    path: str,
    file_id: int,
    class_name: str,
    game_object_name: str | None,
    conflicts: list[PropertyConflict],
    auto_merged: list[AutoMergedChange],
) -> Any:
    """Recursively merge three values and collect conflicts.

    Returns the merged value (prefers ours in case of conflict).
    """
    # Fast path: all equal
    if base_value == ours_value == theirs_value:
        return base_value

    # Only ours changed
    if base_value == theirs_value and base_value != ours_value:
        auto_merged.append(
            AutoMergedChange(
                file_id=file_id,
                class_name=class_name,
                property_path=path,
                source="ours",
                value=ours_value,
            )
        )
        return ours_value

    # Only theirs changed
    if base_value == ours_value and base_value != theirs_value:
        auto_merged.append(
            AutoMergedChange(
                file_id=file_id,
                class_name=class_name,
                property_path=path,
                source="theirs",
                value=theirs_value,
            )
        )
        return theirs_value

    # Both changed to same value
    if ours_value == theirs_value:
        auto_merged.append(
            AutoMergedChange(
                file_id=file_id,
                class_name=class_name,
                property_path=path,
                source="both",
                value=ours_value,
            )
        )
        return ours_value

    # Both changed to different values - potential conflict

    # If all three are dicts, recurse
    if isinstance(base_value, dict) and isinstance(ours_value, dict) and isinstance(theirs_value, dict):
        merged = {}
        all_keys = set(base_value.keys()) | set(ours_value.keys()) | set(theirs_value.keys())
        for key in sorted(all_keys):
            child_path = f"{path}.{key}" if path else key
            merged[key] = _merge_values(
                base_value.get(key),
                ours_value.get(key),
                theirs_value.get(key),
                child_path,
                file_id,
                class_name,
                game_object_name,
                conflicts,
                auto_merged,
            )
        return merged

    # If all three are lists of fileID refs, merge by set union
    if (
        isinstance(base_value, list)
        and isinstance(ours_value, list)
        and isinstance(theirs_value, list)
        and _is_file_id_list(base_value)
        and _is_file_id_list(ours_value)
        and _is_file_id_list(theirs_value)
    ):
        return _merge_file_id_lists(
            base_value,
            ours_value,
            theirs_value,
            path,
            file_id,
            class_name,
            auto_merged,
        )

    # If all three are lists, merge element by element
    if isinstance(base_value, list) and isinstance(ours_value, list) and isinstance(theirs_value, list):
        return _merge_lists(
            base_value,
            ours_value,
            theirs_value,
            path,
            file_id,
            class_name,
            game_object_name,
            conflicts,
            auto_merged,
        )

    # Conflict: both changed to different values
    conflict_type = ConflictType.BOTH_MODIFIED
    if base_value is None:
        conflict_type = ConflictType.BOTH_ADDED
    elif ours_value is None or theirs_value is None:
        conflict_type = ConflictType.DELETE_MODIFY

    conflicts.append(
        PropertyConflict(
            file_id=file_id,
            class_name=class_name,
            property_path=path,
            base_value=base_value,
            ours_value=ours_value,
            theirs_value=theirs_value,
            conflict_type=conflict_type,
            game_object_name=game_object_name,
        )
    )

    # Default to ours in case of conflict
    return ours_value


def _is_file_id_list(value: list[Any]) -> bool:
    """Check if a list contains only fileID references."""
    if not value:
        return True  # Empty list is compatible
    return all(isinstance(item, dict) and "fileID" in item and len(item) == 1 for item in value)


def _merge_file_id_lists(
    base_list: list[dict[str, Any]],
    ours_list: list[dict[str, Any]],
    theirs_list: list[dict[str, Any]],
    path: str,
    file_id: int,
    class_name: str,
    auto_merged: list[AutoMergedChange],
) -> list[dict[str, Any]]:
    """Merge lists of fileID references (like m_Children).

    Uses set-based merging: additions from both sides are included,
    deletions from both sides are applied.
    """
    base_ids = {item["fileID"] for item in base_list}
    ours_ids = {item["fileID"] for item in ours_list}
    theirs_ids = {item["fileID"] for item in theirs_list}

    # Start with base
    result_ids = set(base_ids)

    # Add items added by ours
    ours_added = ours_ids - base_ids
    result_ids |= ours_added
    for added_id in ours_added:
        auto_merged.append(
            AutoMergedChange(
                file_id=file_id,
                class_name=class_name,
                property_path=f"{path}[fileID={added_id}]",
                source="ours",
                value={"fileID": added_id},
            )
        )

    # Add items added by theirs
    theirs_added = theirs_ids - base_ids
    result_ids |= theirs_added
    for added_id in theirs_added:
        if added_id not in ours_added:  # Don't double-count
            auto_merged.append(
                AutoMergedChange(
                    file_id=file_id,
                    class_name=class_name,
                    property_path=f"{path}[fileID={added_id}]",
                    source="theirs",
                    value={"fileID": added_id},
                )
            )

    # Remove items removed by ours
    ours_removed = base_ids - ours_ids
    result_ids -= ours_removed

    # Remove items removed by theirs
    theirs_removed = base_ids - theirs_ids
    result_ids -= theirs_removed

    # Preserve order from ours where possible, then add theirs additions
    result = []
    for item in ours_list:
        if item["fileID"] in result_ids:
            result.append(item)
            result_ids.discard(item["fileID"])

    # Add any remaining (from theirs additions)
    for remaining_id in sorted(result_ids):
        result.append({"fileID": remaining_id})

    return result


def _merge_lists(
    base_list: list[Any],
    ours_list: list[Any],
    theirs_list: list[Any],
    path: str,
    file_id: int,
    class_name: str,
    game_object_name: str | None,
    conflicts: list[PropertyConflict],
    auto_merged: list[AutoMergedChange],
) -> list[Any]:
    """Merge generic lists element by element."""
    max_len = max(len(base_list), len(ours_list), len(theirs_list))
    result = []

    for i in range(max_len):
        base_item = base_list[i] if i < len(base_list) else None
        ours_item = ours_list[i] if i < len(ours_list) else None
        theirs_item = theirs_list[i] if i < len(theirs_list) else None

        child_path = f"{path}[{i}]"
        merged_item = _merge_values(
            base_item,
            ours_item,
            theirs_item,
            child_path,
            file_id,
            class_name,
            game_object_name,
            conflicts,
            auto_merged,
        )
        if merged_item is not None:
            result.append(merged_item)

    return result


def semantic_three_way_merge(
    base_doc: UnityYAMLDocument,
    ours_doc: UnityYAMLDocument,
    theirs_doc: UnityYAMLDocument,
) -> SemanticMergeResult:
    """Perform a semantic three-way merge of Unity YAML documents.

    Compares documents at the property level, enabling:
    - Accurate conflict detection at property level
    - Automatic merging of non-conflicting changes
    - Detailed conflict information for UI display

    Args:
        base_doc: The common ancestor document
        ours_doc: Our version (current branch)
        theirs_doc: Their version (branch being merged)

    Returns:
        SemanticMergeResult containing merged document and conflict info
    """
    # Start with a copy of ours as the base for merging
    merged_doc = _deep_copy_document(ours_doc)

    result = SemanticMergeResult(merged_document=merged_doc)

    # Collect all fileIDs from all three documents
    base_ids = base_doc.get_all_file_ids()
    ours_ids = ours_doc.get_all_file_ids()
    theirs_ids = theirs_doc.get_all_file_ids()
    all_ids = base_ids | ours_ids | theirs_ids

    # Process each object
    for file_id in sorted(all_ids):
        base_obj = base_doc.get_by_file_id(file_id)
        ours_obj = ours_doc.get_by_file_id(file_id)
        theirs_obj = theirs_doc.get_by_file_id(file_id)

        # Determine object presence in each version
        in_base = base_obj is not None
        in_ours = ours_obj is not None
        in_theirs = theirs_obj is not None

        # Case 1: Object in all three - compare properties
        if in_base and in_ours and in_theirs:
            _merge_object_properties(
                base_obj,
                ours_obj,
                theirs_obj,
                merged_doc,
                result,
            )

        # Case 2: Object added by theirs only
        elif not in_base and not in_ours and in_theirs:
            # Add to merged document
            from unityflow.parser import UnityYAMLObject

            new_obj = UnityYAMLObject(
                class_id=theirs_obj.class_id,
                file_id=theirs_obj.file_id,
                data=copy.deepcopy(theirs_obj.data),
                stripped=theirs_obj.stripped,
            )
            merged_doc.add_object(new_obj)
            result.auto_merged.append(
                AutoMergedChange(
                    file_id=file_id,
                    class_name=theirs_obj.class_name,
                    property_path="",
                    source="theirs",
                    value="<object added>",
                )
            )

        # Case 3: Object added by ours only - already in merged
        elif not in_base and in_ours and not in_theirs:
            result.auto_merged.append(
                AutoMergedChange(
                    file_id=file_id,
                    class_name=ours_obj.class_name,
                    property_path="",
                    source="ours",
                    value="<object added>",
                )
            )

        # Case 4: Object deleted by theirs only
        elif in_base and in_ours and not in_theirs:
            # Remove from merged document
            merged_doc.remove_object(file_id)
            result.auto_merged.append(
                AutoMergedChange(
                    file_id=file_id,
                    class_name=base_obj.class_name,
                    property_path="",
                    source="theirs",
                    value="<object removed>",
                )
            )

        # Case 5: Object deleted by ours only - already not in merged
        elif in_base and not in_ours and in_theirs:
            result.auto_merged.append(
                AutoMergedChange(
                    file_id=file_id,
                    class_name=base_obj.class_name,
                    property_path="",
                    source="ours",
                    value="<object removed>",
                )
            )

        # Case 6: Both added same fileID (rare but possible)
        elif not in_base and in_ours and in_theirs:
            if ours_obj.data != theirs_obj.data:
                result.object_conflicts.append(
                    ObjectConflict(
                        file_id=file_id,
                        class_name=ours_obj.class_name,
                        conflict_type=ConflictType.OBJECT_CONFLICT,
                        description="Both sides added object with same fileID",
                    )
                )
            # Keep ours version (already in merged)

        # Case 7: Both deleted - already not in merged
        elif in_base and not in_ours and not in_theirs:
            pass  # Nothing to do

    return result


def _merge_object_properties(
    base_obj: UnityYAMLObject,
    ours_obj: UnityYAMLObject,
    theirs_obj: UnityYAMLObject,
    merged_doc: UnityYAMLDocument,
    result: SemanticMergeResult,
) -> None:
    """Merge properties of a single object."""
    # Get the merged object from the document
    merged_obj = merged_doc.get_by_file_id(base_obj.file_id)
    if merged_obj is None:
        return

    # Get content under root key
    base_content = base_obj.get_content() or {}
    ours_content = ours_obj.get_content() or {}
    theirs_content = theirs_obj.get_content() or {}

    # Get GameObject name for context
    game_object_name = _get_game_object_name(merged_doc, merged_obj)

    # Merge all properties
    merged_content = _merge_values(
        base_content,
        ours_content,
        theirs_content,
        "",
        base_obj.file_id,
        base_obj.class_name,
        game_object_name,
        result.property_conflicts,
        result.auto_merged,
    )

    # Update the merged object
    root_key = merged_obj.root_key
    if root_key:
        merged_obj.data[root_key] = merged_content


def apply_resolution(
    merged_doc: UnityYAMLDocument,
    conflict: PropertyConflict,
    resolution: str | Any,
) -> bool:
    """Apply a conflict resolution to the merged document.

    Args:
        merged_doc: The document to modify
        conflict: The conflict to resolve
        resolution: Resolution method:
            - "ours": Use ours_value
            - "theirs": Use theirs_value
            - "base": Use base_value
            - Any other value: Use as custom value

    Returns:
        True if resolution was applied, False if failed
    """
    obj = merged_doc.get_by_file_id(conflict.file_id)
    if obj is None:
        return False

    # Determine the value to apply
    if resolution == "ours":
        value = conflict.ours_value
    elif resolution == "theirs":
        value = conflict.theirs_value
    elif resolution == "base":
        value = conflict.base_value
    else:
        value = resolution

    # Get the content dict
    content = obj.get_content()
    if content is None:
        return False

    # Apply the value
    return _set_nested_value(content, conflict.property_path, value)


def apply_all_resolutions(
    merged_doc: UnityYAMLDocument,
    conflicts: list[PropertyConflict],
    default_resolution: str = "ours",
) -> int:
    """Apply a default resolution to all conflicts.

    Args:
        merged_doc: The document to modify
        conflicts: List of conflicts to resolve
        default_resolution: Default resolution ("ours", "theirs", or "base")

    Returns:
        Number of successfully resolved conflicts
    """
    resolved = 0
    for conflict in conflicts:
        if apply_resolution(merged_doc, conflict, default_resolution):
            resolved += 1
    return resolved

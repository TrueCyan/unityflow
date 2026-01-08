"""Unity YAML Parser.

Handles Unity's custom YAML 1.1 dialect with:
- Custom tag namespace (!u! -> tag:unity3d.com,2011:)
- Multi-document files with !u!{ClassID} &{fileID} anchors
- Fast parsing using rapidyaml backend
"""

from __future__ import annotations

import json
import random
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from unityflow.fast_parser import (
    LARGE_FILE_THRESHOLD,
    ProgressCallback,
    fast_dump_unity_object,
    fast_parse_unity_yaml,
    get_file_stats,
    iter_dump_unity_object,
    iter_parse_unity_yaml,
    stream_parse_unity_yaml_file,
)

# Unity YAML header pattern
UNITY_HEADER = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
"""

# Pattern to match Unity document headers: --- !u!{ClassID} &{fileID}
# Note: fileID can be negative (Unity uses 64-bit signed integers)
DOCUMENT_HEADER_PATTERN = re.compile(r"^--- !u!(\d+) &(-?\d+)(?: stripped)?$", re.MULTILINE)


def _load_class_ids() -> dict[int, str]:
    """Load Unity ClassIDs from JSON file.

    The JSON file is generated from Unity's official ClassIDReference documentation.
    Falls back to a minimal built-in set if the JSON file is not found.

    Returns:
        Dictionary mapping class ID (int) to class name (str)
    """
    try:
        # Use importlib.resources for package data (Python 3.9+)
        from importlib.resources import files

        data_file = files("unityflow.data").joinpath("class_ids.json")
        with data_file.open(encoding="utf-8") as f:
            data = json.load(f)
            # Convert string keys to int (JSON only supports string keys)
            return {int(k): v for k, v in data.items()}
    except (ImportError, FileNotFoundError, json.JSONDecodeError, OSError, ValueError, TypeError):
        pass

    # Fallback: minimal built-in set for essential types
    return {
        1: "GameObject",
        4: "Transform",
        114: "MonoBehaviour",
        115: "MonoScript",
        224: "RectTransform",
        1001: "PrefabInstance",
    }


# Unity ClassIDs - loaded from data/class_ids.json
# Reference: https://docs.unity3d.com/Manual/ClassIDReference.html (Unity 6.3 LTS)
CLASS_IDS: dict[int, str] = _load_class_ids()


def get_parser_backend() -> str:
    """Get the current parser backend name."""
    return "rapidyaml"


@dataclass
class UnityYAMLObject:
    """Represents a single Unity YAML document/object."""

    class_id: int
    file_id: int
    data: dict[str, Any]
    stripped: bool = False

    @property
    def class_name(self) -> str:
        """Get the human-readable class name for this object."""
        return CLASS_IDS.get(self.class_id, f"Unknown({self.class_id})")

    @property
    def root_key(self) -> str | None:
        """Get the root key of the document (e.g., 'GameObject', 'Transform')."""
        if self.data:
            keys = list(self.data.keys())
            return keys[0] if keys else None
        return None

    def get_content(self) -> dict[str, Any] | None:
        """Get the content under the root key."""
        root = self.root_key
        if root and root in self.data:
            return self.data[root]
        return None

    def __repr__(self) -> str:
        return f"UnityYAMLObject(class={self.class_name}, fileID={self.file_id})"


@dataclass
class UnityYAMLDocument:
    """Represents a complete Unity YAML file with multiple objects."""

    objects: list[UnityYAMLObject] = field(default_factory=list)
    source_path: Path | None = None

    def __iter__(self) -> Iterator[UnityYAMLObject]:
        return iter(self.objects)

    def __len__(self) -> int:
        return len(self.objects)

    def get_by_file_id(self, file_id: int) -> UnityYAMLObject | None:
        """Find an object by its fileID."""
        for obj in self.objects:
            if obj.file_id == file_id:
                return obj
        return None

    def get_by_class_id(self, class_id: int) -> list[UnityYAMLObject]:
        """Find all objects of a specific class type."""
        return [obj for obj in self.objects if obj.class_id == class_id]

    def get_game_objects(self) -> list[UnityYAMLObject]:
        """Get all GameObject objects."""
        return self.get_by_class_id(1)

    def get_transforms(self) -> list[UnityYAMLObject]:
        """Get all Transform objects."""
        return self.get_by_class_id(4)

    def get_prefab_instances(self) -> list[UnityYAMLObject]:
        """Get all PrefabInstance objects."""
        return self.get_by_class_id(1001)

    def get_rect_transforms(self) -> list[UnityYAMLObject]:
        """Get all RectTransform objects."""
        return self.get_by_class_id(224)

    def get_all_file_ids(self) -> set[int]:
        """Get all fileIDs in this document."""
        return {obj.file_id for obj in self.objects}

    def add_object(self, obj: UnityYAMLObject) -> None:
        """Add a new object to the document.

        Args:
            obj: The UnityYAMLObject to add
        """
        self.objects.append(obj)

    def remove_object(self, file_id: int) -> bool:
        """Remove an object by its fileID.

        Args:
            file_id: The fileID of the object to remove

        Returns:
            True if removed, False if not found
        """
        for i, obj in enumerate(self.objects):
            if obj.file_id == file_id:
                self.objects.pop(i)
                return True
        return False

    def generate_unique_file_id(self) -> int:
        """Generate a unique fileID for this document.

        Returns:
            A fileID that doesn't conflict with existing objects
        """
        existing = self.get_all_file_ids()
        return generate_file_id(existing)

    @classmethod
    def load(
        cls,
        path: str | Path,
        progress_callback: ProgressCallback | None = None,
    ) -> UnityYAMLDocument:
        """Load a Unity YAML file from disk.

        Args:
            path: Path to the Unity YAML file
            progress_callback: Optional callback for progress reporting

        Returns:
            Parsed UnityYAMLDocument
        """
        path = Path(path)
        content = path.read_text(encoding="utf-8")
        doc = cls.parse(content, progress_callback)
        doc.source_path = path
        return doc

    @classmethod
    def load_streaming(
        cls,
        path: str | Path,
        progress_callback: ProgressCallback | None = None,
    ) -> UnityYAMLDocument:
        """Load a large Unity YAML file using streaming mode.

        This method is optimized for large files (10MB+) and uses less memory
        by processing the file in chunks.

        Args:
            path: Path to the Unity YAML file
            progress_callback: Optional callback for progress reporting (bytes_read, total_bytes)

        Returns:
            Parsed UnityYAMLDocument
        """
        path = Path(path)
        doc = cls()
        doc.source_path = path

        for class_id, file_id, stripped, data in stream_parse_unity_yaml_file(
            path, progress_callback=progress_callback
        ):
            obj = UnityYAMLObject(
                class_id=class_id,
                file_id=file_id,
                data=data,
                stripped=stripped,
            )
            doc.objects.append(obj)

        return doc

    @classmethod
    def load_auto(
        cls,
        path: str | Path,
        progress_callback: ProgressCallback | None = None,
    ) -> UnityYAMLDocument:
        """Load a Unity YAML file, automatically choosing the best method.

        For files smaller than 10MB, uses the standard load method.
        For larger files, uses streaming mode for better memory efficiency.

        Args:
            path: Path to the Unity YAML file
            progress_callback: Optional callback for progress reporting

        Returns:
            Parsed UnityYAMLDocument
        """
        path = Path(path)
        file_size = path.stat().st_size

        if file_size >= LARGE_FILE_THRESHOLD:
            return cls.load_streaming(path, progress_callback)
        else:
            return cls.load(path, progress_callback)

    @classmethod
    def parse(
        cls,
        content: str,
        progress_callback: ProgressCallback | None = None,
    ) -> UnityYAMLDocument:
        """Parse Unity YAML content from a string.

        Args:
            content: Unity YAML content string
            progress_callback: Optional callback for progress reporting

        Returns:
            Parsed UnityYAMLDocument
        """
        doc = cls()

        parsed = fast_parse_unity_yaml(content, progress_callback)

        for class_id, file_id, stripped, data in parsed:
            obj = UnityYAMLObject(
                class_id=class_id,
                file_id=file_id,
                data=data,
                stripped=stripped,
            )
            doc.objects.append(obj)

        return doc

    @classmethod
    def iter_parse(
        cls,
        content: str,
        progress_callback: ProgressCallback | None = None,
    ) -> Iterator[UnityYAMLObject]:
        """Parse Unity YAML content, yielding objects one at a time.

        This is a memory-efficient generator version for processing large content.

        Args:
            content: Unity YAML content string
            progress_callback: Optional callback for progress reporting

        Yields:
            UnityYAMLObject instances
        """
        for class_id, file_id, stripped, data in iter_parse_unity_yaml(content, progress_callback):
            yield UnityYAMLObject(
                class_id=class_id,
                file_id=file_id,
                data=data,
                stripped=stripped,
            )

    def dump(self) -> str:
        """Serialize the document back to Unity YAML format."""
        output_lines = [UNITY_HEADER.rstrip()]

        for obj in self.objects:
            # Write document header
            header = f"--- !u!{obj.class_id} &{obj.file_id}"
            if obj.stripped:
                header += " stripped"
            output_lines.append(header)

            # Serialize document content
            if obj.data:
                content = fast_dump_unity_object(obj.data)
                if content:
                    output_lines.append(content)

        # Unity uses LF line endings
        return "\n".join(output_lines) + "\n"

    def iter_dump(self) -> Iterator[str]:
        """Serialize the document, yielding lines one at a time.

        This is a memory-efficient generator version for large documents.

        Yields:
            YAML lines as strings
        """
        yield UNITY_HEADER.rstrip()

        for obj in self.objects:
            # Write document header
            header = f"--- !u!{obj.class_id} &{obj.file_id}"
            if obj.stripped:
                header += " stripped"
            yield header

            # Serialize document content
            if obj.data:
                yield from iter_dump_unity_object(obj.data)

    def save(self, path: str | Path) -> None:
        """Save the document to a file."""
        path = Path(path)
        content = self.dump()
        path.write_text(content, encoding="utf-8", newline="\n")

    def save_streaming(self, path: str | Path) -> None:
        """Save the document to a file using streaming mode.

        This is more memory-efficient for large documents as it writes
        line by line instead of building the entire content in memory.

        Args:
            path: Output file path
        """
        path = Path(path)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            for line in self.iter_dump():
                f.write(line)
                f.write("\n")

    @staticmethod
    def get_stats(path: str | Path) -> dict[str, Any]:
        """Get statistics about a Unity YAML file without fully parsing it.

        This is a fast operation that only scans document headers.

        Args:
            path: Path to the Unity YAML file

        Returns:
            Dictionary with file statistics including:
            - file_size: Size in bytes
            - file_size_mb: Size in megabytes
            - document_count: Number of YAML documents
            - class_counts: Count of each class type
            - is_large_file: Whether the file exceeds the large file threshold
        """
        return get_file_stats(path)


def parse_file_reference(ref: dict[str, Any] | None) -> tuple[int, str | None, int | None] | None:
    """Parse a Unity file reference.

    Args:
        ref: A dictionary with fileID, optional guid, and optional type

    Returns:
        Tuple of (fileID, guid, type) or None if invalid
    """
    if ref is None:
        return None
    if not isinstance(ref, dict):
        return None

    file_id = ref.get("fileID")
    if file_id is None:
        return None

    guid = ref.get("guid")
    ref_type = ref.get("type")

    return (int(file_id), guid, ref_type)


def create_file_reference(
    file_id: int,
    guid: str | None = None,
    ref_type: int | None = None,
) -> dict[str, Any]:
    """Create a Unity file reference.

    Args:
        file_id: The local file ID
        guid: Optional GUID for external references
        ref_type: Optional type (usually 2 for assets, 3 for scripts)

    Returns:
        Dictionary with the reference
    """
    ref: dict[str, Any] = {"fileID": file_id}
    if guid is not None:
        ref["guid"] = guid
    if ref_type is not None:
        ref["type"] = ref_type
    return ref


# Global counter for fileID generation (ensures uniqueness within a session)
_file_id_counter = 0


def generate_file_id(existing_ids: set[int] | None = None) -> int:
    """Generate a unique fileID for a new Unity object.

    Unity uses large integers for fileIDs. This function generates IDs
    that are unique and follow Unity's conventions.

    Args:
        existing_ids: Optional set of existing fileIDs to avoid collisions

    Returns:
        A unique fileID (large positive integer)
    """
    global _file_id_counter
    _file_id_counter += 1

    # Generate a unique ID based on timestamp + counter + random
    # Unity typically uses large numbers (10+ digits)
    timestamp_part = int(time.time() * 1000) % 10000000000
    random_part = random.randint(1000000, 9999999)
    file_id = timestamp_part * 10000000 + random_part + _file_id_counter

    # Ensure uniqueness if existing_ids provided
    if existing_ids:
        while file_id in existing_ids:
            _file_id_counter += 1
            random_part = random.randint(1000000, 9999999)
            file_id = timestamp_part * 10000000 + random_part + _file_id_counter

    return file_id


def create_game_object(
    name: str,
    file_id: int | None = None,
    layer: int = 0,
    tag: str = "Untagged",
    is_active: bool = True,
    components: list[int] | None = None,
) -> UnityYAMLObject:
    """Create a new GameObject object.

    Args:
        name: Name of the GameObject
        file_id: Optional fileID (generated if not provided)
        layer: Layer number (default: 0)
        tag: Tag string (default: "Untagged")
        is_active: Whether the object is active (default: True)
        components: List of component fileIDs

    Returns:
        UnityYAMLObject representing the GameObject
    """
    if file_id is None:
        file_id = generate_file_id()

    content = {
        "m_ObjectHideFlags": 0,
        "m_CorrespondingSourceObject": {"fileID": 0},
        "m_PrefabInstance": {"fileID": 0},
        "m_PrefabAsset": {"fileID": 0},
        "serializedVersion": 6,
        "m_Component": [{"component": {"fileID": c}} for c in (components or [])],
        "m_Layer": layer,
        "m_Name": name,
        "m_TagString": tag,
        "m_Icon": {"fileID": 0},
        "m_NavMeshLayer": 0,
        "m_StaticEditorFlags": 0,
        "m_IsActive": 1 if is_active else 0,
    }

    return UnityYAMLObject(
        class_id=1,
        file_id=file_id,
        data={"GameObject": content},
        stripped=False,
    )


def create_transform(
    game_object_id: int,
    file_id: int | None = None,
    position: dict[str, float] | None = None,
    rotation: dict[str, float] | None = None,
    scale: dict[str, float] | None = None,
    parent_id: int = 0,
    children_ids: list[int] | None = None,
) -> UnityYAMLObject:
    """Create a new Transform component.

    Args:
        game_object_id: fileID of the parent GameObject
        file_id: Optional fileID (generated if not provided)
        position: Local position {x, y, z} (default: origin)
        rotation: Local rotation quaternion {x, y, z, w} (default: identity)
        scale: Local scale {x, y, z} (default: 1,1,1)
        parent_id: fileID of parent Transform (0 for root)
        children_ids: List of children Transform fileIDs

    Returns:
        UnityYAMLObject representing the Transform
    """
    if file_id is None:
        file_id = generate_file_id()

    content = {
        "m_ObjectHideFlags": 0,
        "m_CorrespondingSourceObject": {"fileID": 0},
        "m_PrefabInstance": {"fileID": 0},
        "m_PrefabAsset": {"fileID": 0},
        "m_GameObject": {"fileID": game_object_id},
        "serializedVersion": 2,
        "m_LocalRotation": rotation or {"x": 0, "y": 0, "z": 0, "w": 1},
        "m_LocalPosition": position or {"x": 0, "y": 0, "z": 0},
        "m_LocalScale": scale or {"x": 1, "y": 1, "z": 1},
        "m_ConstrainProportionsScale": 0,
        "m_Children": [{"fileID": c} for c in (children_ids or [])],
        "m_Father": {"fileID": parent_id},
        "m_LocalEulerAnglesHint": {"x": 0, "y": 0, "z": 0},
    }

    return UnityYAMLObject(
        class_id=4,
        file_id=file_id,
        data={"Transform": content},
        stripped=False,
    )


def create_rect_transform(
    game_object_id: int,
    file_id: int | None = None,
    position: dict[str, float] | None = None,
    rotation: dict[str, float] | None = None,
    scale: dict[str, float] | None = None,
    parent_id: int = 0,
    children_ids: list[int] | None = None,
    anchor_min: dict[str, float] | None = None,
    anchor_max: dict[str, float] | None = None,
    anchored_position: dict[str, float] | None = None,
    size_delta: dict[str, float] | None = None,
    pivot: dict[str, float] | None = None,
) -> UnityYAMLObject:
    """Create a new RectTransform component for UI elements.

    Args:
        game_object_id: fileID of the parent GameObject
        file_id: Optional fileID (generated if not provided)
        position: Local position {x, y, z} (default: origin)
        rotation: Local rotation quaternion {x, y, z, w} (default: identity)
        scale: Local scale {x, y, z} (default: 1,1,1)
        parent_id: fileID of parent RectTransform (0 for root)
        children_ids: List of children RectTransform fileIDs
        anchor_min: Anchor min point {x, y} (default: {0.5, 0.5})
        anchor_max: Anchor max point {x, y} (default: {0.5, 0.5})
        anchored_position: Position relative to anchors {x, y} (default: origin)
        size_delta: Size delta from anchored rect {x, y} (default: {100, 100})
        pivot: Pivot point {x, y} (default: center {0.5, 0.5})

    Returns:
        UnityYAMLObject representing the RectTransform
    """
    if file_id is None:
        file_id = generate_file_id()

    content = {
        "m_ObjectHideFlags": 0,
        "m_CorrespondingSourceObject": {"fileID": 0},
        "m_PrefabInstance": {"fileID": 0},
        "m_PrefabAsset": {"fileID": 0},
        "m_GameObject": {"fileID": game_object_id},
        "m_LocalRotation": rotation or {"x": 0, "y": 0, "z": 0, "w": 1},
        "m_LocalPosition": position or {"x": 0, "y": 0, "z": 0},
        "m_LocalScale": scale or {"x": 1, "y": 1, "z": 1},
        "m_ConstrainProportionsScale": 0,
        "m_Children": [{"fileID": c} for c in (children_ids or [])],
        "m_Father": {"fileID": parent_id},
        "m_LocalEulerAnglesHint": {"x": 0, "y": 0, "z": 0},
        "m_AnchorMin": anchor_min or {"x": 0.5, "y": 0.5},
        "m_AnchorMax": anchor_max or {"x": 0.5, "y": 0.5},
        "m_AnchoredPosition": anchored_position or {"x": 0, "y": 0},
        "m_SizeDelta": size_delta or {"x": 100, "y": 100},
        "m_Pivot": pivot or {"x": 0.5, "y": 0.5},
    }

    return UnityYAMLObject(
        class_id=224,
        file_id=file_id,
        data={"RectTransform": content},
        stripped=False,
    )


def create_mono_behaviour(
    game_object_id: int,
    script_guid: str,
    file_id: int | None = None,
    enabled: bool = True,
    properties: dict[str, Any] | None = None,
) -> UnityYAMLObject:
    """Create a new MonoBehaviour component.

    Args:
        game_object_id: fileID of the parent GameObject
        script_guid: GUID of the script asset
        file_id: Optional fileID (generated if not provided)
        enabled: Whether the component is enabled (default: True)
        properties: Custom serialized fields

    Returns:
        UnityYAMLObject representing the MonoBehaviour
    """
    if file_id is None:
        file_id = generate_file_id()

    content = {
        "m_ObjectHideFlags": 0,
        "m_CorrespondingSourceObject": {"fileID": 0},
        "m_PrefabInstance": {"fileID": 0},
        "m_PrefabAsset": {"fileID": 0},
        "m_GameObject": {"fileID": game_object_id},
        "m_Enabled": 1 if enabled else 0,
        "m_EditorHideFlags": 0,
        "m_Script": {"fileID": 11500000, "guid": script_guid, "type": 3},
        "m_EditorClassIdentifier": "",
    }

    # Add custom properties
    if properties:
        content.update(properties)

    return UnityYAMLObject(
        class_id=114,
        file_id=file_id,
        data={"MonoBehaviour": content},
        stripped=False,
    )

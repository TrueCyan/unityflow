"""Unity YAML Parser.

Handles Unity's custom YAML 1.1 dialect with:
- Custom tag namespace (!u! -> tag:unity3d.com,2011:)
- Multi-document files with !u!{ClassID} &{fileID} anchors
- Fast parsing using rapidyaml backend
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from prefab_tool.fast_parser import (
    LARGE_FILE_THRESHOLD,
    ProgressCallback,
    fast_parse_unity_yaml,
    fast_dump_unity_object,
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
DOCUMENT_HEADER_PATTERN = re.compile(
    r"^--- !u!(\d+) &(\d+)(?: stripped)?$", re.MULTILINE
)

# Common Unity ClassIDs
CLASS_IDS = {
    1: "GameObject",
    4: "Transform",
    20: "Camera",
    23: "MeshRenderer",
    33: "MeshFilter",
    54: "Rigidbody",
    65: "BoxCollider",
    82: "AudioSource",
    114: "MonoBehaviour",
    124: "Behaviour",
    212: "SpriteRenderer",
    222: "CanvasRenderer",
    223: "Canvas",
    224: "RectTransform",
    225: "CanvasGroup",
    1001: "PrefabInstance",
}


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
        for class_id, file_id, stripped, data in iter_parse_unity_yaml(
            content, progress_callback
        ):
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

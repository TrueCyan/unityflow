"""Unity YAML Parser.

Handles Unity's custom YAML 1.1 dialect with:
- Custom tag namespace (!u! -> tag:unity3d.com,2011:)
- Multi-document files with !u!{ClassID} &{fileID} anchors
- Preserves formatting for round-trip fidelity
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap


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


@dataclass
class UnityYAMLObject:
    """Represents a single Unity YAML document/object."""

    class_id: int
    file_id: int
    data: CommentedMap
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
    def load(cls, path: str | Path) -> UnityYAMLDocument:
        """Load a Unity YAML file from disk."""
        path = Path(path)
        content = path.read_text(encoding="utf-8")
        doc = cls.parse(content)
        doc.source_path = path
        return doc

    @classmethod
    def parse(cls, content: str) -> UnityYAMLDocument:
        """Parse Unity YAML content from a string."""
        doc = cls()

        # Skip the header and find all document boundaries
        lines = content.split("\n")

        # Find all document start positions
        doc_starts: list[tuple[int, int, int, bool]] = []  # (line_idx, class_id, file_id, stripped)

        for i, line in enumerate(lines):
            match = DOCUMENT_HEADER_PATTERN.match(line)
            if match:
                class_id = int(match.group(1))
                file_id = int(match.group(2))
                stripped = "stripped" in line
                doc_starts.append((i, class_id, file_id, stripped))

        if not doc_starts:
            return doc

        # Parse each document
        yaml = YAML()
        yaml.preserve_quotes = True

        for idx, (start_line, class_id, file_id, stripped) in enumerate(doc_starts):
            # Determine end of this document
            if idx + 1 < len(doc_starts):
                end_line = doc_starts[idx + 1][0]
            else:
                end_line = len(lines)

            # Extract document content (skip the --- header line)
            doc_content = "\n".join(lines[start_line + 1:end_line])

            if not doc_content.strip():
                # Empty document
                obj = UnityYAMLObject(
                    class_id=class_id,
                    file_id=file_id,
                    data=CommentedMap(),
                    stripped=stripped,
                )
            else:
                try:
                    data = yaml.load(doc_content)
                    if data is None:
                        data = CommentedMap()
                    elif not isinstance(data, CommentedMap):
                        # Wrap primitive values
                        wrapped = CommentedMap()
                        wrapped["value"] = data
                        data = wrapped

                    obj = UnityYAMLObject(
                        class_id=class_id,
                        file_id=file_id,
                        data=data,
                        stripped=stripped,
                    )
                except Exception as e:
                    raise ValueError(
                        f"Failed to parse document at line {start_line + 1} "
                        f"(class_id={class_id}, file_id={file_id}): {e}"
                    ) from e

            doc.objects.append(obj)

        return doc

    def dump(self) -> str:
        """Serialize the document back to Unity YAML format."""
        yaml = YAML()
        yaml.default_flow_style = None
        yaml.preserve_quotes = True
        yaml.indent(mapping=2, sequence=2, offset=0)
        yaml.width = 1000  # Avoid line wrapping

        output_lines = [UNITY_HEADER.rstrip()]

        for obj in self.objects:
            # Write document header
            header = f"--- !u!{obj.class_id} &{obj.file_id}"
            if obj.stripped:
                header += " stripped"
            output_lines.append(header)

            # Serialize document content
            if obj.data:
                from io import StringIO
                stream = StringIO()
                yaml.dump(obj.data, stream)
                content = stream.getvalue()
                # Remove trailing newline to avoid extra blank lines
                content = content.rstrip("\n")
                if content:
                    output_lines.append(content)

        # Unity uses LF line endings
        return "\n".join(output_lines) + "\n"

    def save(self, path: str | Path) -> None:
        """Save the document to a file."""
        path = Path(path)
        content = self.dump()
        path.write_text(content, encoding="utf-8", newline="\n")


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
) -> CommentedMap:
    """Create a Unity file reference.

    Args:
        file_id: The local file ID
        guid: Optional GUID for external references
        ref_type: Optional type (usually 2 for assets, 3 for scripts)

    Returns:
        CommentedMap with the reference
    """
    ref = CommentedMap()
    ref["fileID"] = file_id
    if guid is not None:
        ref["guid"] = guid
    if ref_type is not None:
        ref["type"] = ref_type
    return ref

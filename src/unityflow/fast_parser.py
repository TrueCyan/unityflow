"""Unity YAML Parser using rapidyaml.

Provides fast parsing for Unity YAML files using the rapidyaml library.
Includes streaming support for large files and progress callbacks.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any

import ryml

# Threshold for using streaming mode (10MB)
LARGE_FILE_THRESHOLD = 10 * 1024 * 1024

# Callback type for progress reporting
ProgressCallback = Callable[[int, int], None]  # (current, total)

# Unity YAML header pattern
UNITY_HEADER = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
"""

# Pattern to match Unity document headers: --- !u!{ClassID} &{fileID}
# Note: fileID can be negative (Unity uses 64-bit signed integers)
DOCUMENT_HEADER_PATTERN = re.compile(r"^--- !u!(\d+) &(-?\d+)(?: stripped)?$", re.MULTILINE)

# Pattern to match Unity GUIDs (32 hexadecimal characters)
# This is used to prevent GUIDs like "0000000000000000e000000000000000" from being
# parsed as scientific notation floats (0e000000000000000 = 0.0)
GUID_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")


def _iter_children(tree: Any, node_id: int) -> list[int]:
    """Iterate over children of a node."""
    if not tree.has_children(node_id):
        return []
    children = []
    child = tree.first_child(node_id)
    while child != ryml.NONE:
        children.append(child)
        child = tree.next_sibling(child)
    return children


def _to_python(tree: Any, node_id: int) -> Any:
    """Convert rapidyaml tree node to Python object."""
    if tree.is_map(node_id):
        result = {}
        for child in _iter_children(tree, node_id):
            if tree.has_key(child):
                key = bytes(tree.key(child)).decode("utf-8")
            else:
                key = ""
            result[key] = _to_python(tree, child)
        return result
    elif tree.is_seq(node_id):
        return [_to_python(tree, child) for child in _iter_children(tree, node_id)]
    elif tree.has_val(node_id):
        val_mv = tree.val(node_id)
        if val_mv is None:
            return None
        val_bytes = bytes(val_mv)
        if not val_bytes:
            return ""
        val = val_bytes.decode("utf-8")

        # Handle YAML null values
        if val in ("null", "~", ""):
            return None

        # Try converting to int (but preserve strings with leading zeros)
        if val.lstrip("-").isdigit():
            # Check for leading zeros - keep as string to preserve format
            stripped = val.lstrip("-")
            if len(stripped) > 1 and stripped.startswith("0"):
                # Has leading zeros - keep as string
                return val
            try:
                return int(val)
            except ValueError:
                pass

        # Skip float conversion for GUID-like strings (32 hex chars)
        # GUIDs like "0000000000000000e000000000000000" would otherwise be
        # parsed as scientific notation (0e000000000000000 = 0.0)
        if GUID_PATTERN.match(val):
            return val

        # Try converting to float
        try:
            return float(val)
        except ValueError:
            pass

        # Return as string
        return val
    # Node has neither map, seq, nor val - treat as null
    return None


def fast_parse_yaml(content: str) -> dict[str, Any]:
    """Parse a single YAML document using rapidyaml.

    Args:
        content: YAML content string

    Returns:
        Parsed Python dictionary
    """
    tree = ryml.parse_in_arena(content.encode("utf-8"))
    return _to_python(tree, tree.root_id())


def fast_parse_unity_yaml(
    content: str,
    progress_callback: ProgressCallback | None = None,
) -> list[tuple[int, int, bool, dict[str, Any]]]:
    """Parse Unity YAML content using rapidyaml.

    Args:
        content: Unity YAML file content
        progress_callback: Optional callback for progress reporting (current, total)

    Returns:
        List of (class_id, file_id, stripped, data) tuples
    """
    lines = content.split("\n")

    # Find all document boundaries
    doc_starts: list[tuple[int, int, int, bool]] = []

    for i, line in enumerate(lines):
        match = DOCUMENT_HEADER_PATTERN.match(line)
        if match:
            class_id = int(match.group(1))
            file_id = int(match.group(2))
            stripped = "stripped" in line
            doc_starts.append((i, class_id, file_id, stripped))

    if not doc_starts:
        return []

    results = []
    total_docs = len(doc_starts)

    for idx, (start_line, class_id, file_id, stripped) in enumerate(doc_starts):
        # Report progress
        if progress_callback:
            progress_callback(idx, total_docs)

        # Determine end of this document
        if idx + 1 < len(doc_starts):
            end_line = doc_starts[idx + 1][0]
        else:
            end_line = len(lines)

        # Extract document content (skip the --- header line)
        doc_content = "\n".join(lines[start_line + 1 : end_line])

        if not doc_content.strip():
            # Empty document
            data = {}
        else:
            try:
                tree = ryml.parse_in_arena(doc_content.encode("utf-8"))
                data = _to_python(tree, tree.root_id())
                if not isinstance(data, dict):
                    data = {}
            except Exception as e:
                raise ValueError(
                    f"Failed to parse document at line {start_line + 1} "
                    f"(class_id={class_id}, file_id={file_id}): {e}"
                ) from e

        results.append((class_id, file_id, stripped, data))

    # Final progress callback
    if progress_callback:
        progress_callback(total_docs, total_docs)

    return results


def iter_parse_unity_yaml(
    content: str,
    progress_callback: ProgressCallback | None = None,
) -> Generator[tuple[int, int, bool, dict[str, Any]], None, None]:
    """Parse Unity YAML content using rapidyaml, yielding documents one at a time.

    This is a memory-efficient generator version that doesn't load all documents
    into memory at once. Useful for large files.

    Args:
        content: Unity YAML file content
        progress_callback: Optional callback for progress reporting (current, total)

    Yields:
        Tuples of (class_id, file_id, stripped, data)
    """
    lines = content.split("\n")

    # Find all document boundaries
    doc_starts: list[tuple[int, int, int, bool]] = []

    for i, line in enumerate(lines):
        match = DOCUMENT_HEADER_PATTERN.match(line)
        if match:
            class_id = int(match.group(1))
            file_id = int(match.group(2))
            stripped = "stripped" in line
            doc_starts.append((i, class_id, file_id, stripped))

    if not doc_starts:
        return

    total_docs = len(doc_starts)

    for idx, (start_line, class_id, file_id, stripped) in enumerate(doc_starts):
        # Report progress
        if progress_callback:
            progress_callback(idx, total_docs)

        # Determine end of this document
        if idx + 1 < len(doc_starts):
            end_line = doc_starts[idx + 1][0]
        else:
            end_line = len(lines)

        # Extract document content (skip the --- header line)
        doc_content = "\n".join(lines[start_line + 1 : end_line])

        if not doc_content.strip():
            # Empty document
            data = {}
        else:
            try:
                tree = ryml.parse_in_arena(doc_content.encode("utf-8"))
                data = _to_python(tree, tree.root_id())
                if not isinstance(data, dict):
                    data = {}
            except Exception as e:
                raise ValueError(
                    f"Failed to parse document at line {start_line + 1} "
                    f"(class_id={class_id}, file_id={file_id}): {e}"
                ) from e

        yield (class_id, file_id, stripped, data)

    # Final progress callback
    if progress_callback:
        progress_callback(total_docs, total_docs)


def stream_parse_unity_yaml_file(
    file_path: str | Path,
    chunk_size: int = 8 * 1024 * 1024,  # 8MB chunks
    progress_callback: ProgressCallback | None = None,
) -> Generator[tuple[int, int, bool, dict[str, Any]], None, None]:
    """Stream parse a Unity YAML file without loading it entirely into memory.

    This function is optimized for very large files (100MB+). It reads the file
    in chunks and yields documents as they are parsed.

    Args:
        file_path: Path to the Unity YAML file
        chunk_size: Size of chunks to read (default: 8MB)
        progress_callback: Optional callback for progress reporting (bytes_read, total_bytes)

    Yields:
        Tuples of (class_id, file_id, stripped, data)
    """
    file_path = Path(file_path)
    file_size = file_path.stat().st_size

    # For smaller files, use the standard approach
    if file_size < LARGE_FILE_THRESHOLD:
        content = file_path.read_text(encoding="utf-8")
        yield from iter_parse_unity_yaml(content, progress_callback)
        return

    # For large files, use streaming approach
    buffer = ""
    bytes_read = 0
    pending_doc: tuple[int, int, bool, list[str]] | None = None

    with open(file_path, encoding="utf-8") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break

            bytes_read += len(chunk.encode("utf-8"))
            buffer += chunk

            # Process complete documents in the buffer
            while True:
                # Find the next document header
                match = DOCUMENT_HEADER_PATTERN.search(buffer)
                if not match:
                    break

                # If we have a pending document, finalize it
                if pending_doc is not None:
                    class_id, file_id, stripped, doc_lines = pending_doc
                    # Everything before this match belongs to the previous document
                    doc_content = buffer[: match.start()]
                    doc_lines.append(doc_content)
                    full_content = "".join(doc_lines).strip()

                    if full_content:
                        try:
                            tree = ryml.parse_in_arena(full_content.encode("utf-8"))
                            data = _to_python(tree, tree.root_id())
                            if not isinstance(data, dict):
                                data = {}
                        except Exception:
                            data = {}
                    else:
                        data = {}

                    yield (class_id, file_id, stripped, data)

                # Start a new pending document
                class_id = int(match.group(1))
                file_id = int(match.group(2))
                stripped = "stripped" in match.group(0)

                # Move buffer past the header
                buffer = buffer[match.end() :]
                if buffer.startswith("\n"):
                    buffer = buffer[1:]

                pending_doc = (class_id, file_id, stripped, [])

            # Report progress
            if progress_callback:
                progress_callback(bytes_read, file_size)

        # Process the last document
        if pending_doc is not None:
            class_id, file_id, stripped, doc_lines = pending_doc
            doc_lines.append(buffer)
            full_content = "".join(doc_lines).strip()

            if full_content:
                try:
                    tree = ryml.parse_in_arena(full_content.encode("utf-8"))
                    data = _to_python(tree, tree.root_id())
                    if not isinstance(data, dict):
                        data = {}
                except Exception:
                    data = {}
            else:
                data = {}

            yield (class_id, file_id, stripped, data)

    # Final progress callback
    if progress_callback:
        progress_callback(file_size, file_size)


def get_file_stats(file_path: str | Path) -> dict[str, Any]:
    """Get statistics about a Unity YAML file without fully parsing it.

    This is a fast operation that only scans document headers.

    Args:
        file_path: Path to the Unity YAML file

    Returns:
        Dictionary with file statistics
    """
    file_path = Path(file_path)
    file_size = file_path.stat().st_size

    doc_count = 0
    class_counts: dict[int, int] = {}

    with open(file_path, encoding="utf-8") as f:
        for line in f:
            match = DOCUMENT_HEADER_PATTERN.match(line)
            if match:
                doc_count += 1
                class_id = int(match.group(1))
                class_counts[class_id] = class_counts.get(class_id, 0) + 1

    return {
        "file_size": file_size,
        "file_size_mb": round(file_size / (1024 * 1024), 2),
        "document_count": doc_count,
        "class_counts": class_counts,
        "is_large_file": file_size >= LARGE_FILE_THRESHOLD,
    }


def fast_dump_unity_object(data: dict[str, Any]) -> str:
    """Dump a Unity YAML object to string using fast serialization.

    This produces Unity-compatible YAML output with proper formatting.
    """
    lines: list[str] = []
    _dump_dict(data, lines, indent=0)
    return "\n".join(lines)


def _dump_dict(data: dict[str, Any], lines: list[str], indent: int) -> None:
    """Dump a dictionary to YAML lines."""
    prefix = "  " * indent

    for key, value in data.items():
        if isinstance(value, dict):
            if not value:
                lines.append(f"{prefix}{key}: {{}}")
            elif _is_flow_dict(value):
                flow = _to_flow(value)
                lines.append(f"{prefix}{key}: {flow}")
            else:
                lines.append(f"{prefix}{key}:")
                _dump_dict(value, lines, indent + 1)
        elif isinstance(value, list):
            if not value:
                lines.append(f"{prefix}{key}: []")
            else:
                lines.append(f"{prefix}{key}:")
                _dump_list(value, lines, indent)
        else:
            scalar = _format_scalar(value)
            if scalar:
                lines.append(f"{prefix}{key}: {scalar}")
            else:
                # Empty value - no space after colon
                lines.append(f"{prefix}{key}:")


def _dump_list(data: list[Any], lines: list[str], indent: int) -> None:
    """Dump a list to YAML lines."""
    prefix = "  " * indent

    for item in data:
        if isinstance(item, dict):
            if _is_flow_dict(item):
                flow = _to_flow(item)
                lines.append(f"{prefix}- {flow}")
            else:
                # Block style dict in list
                keys = list(item.keys())
                if keys:
                    first_key = keys[0]
                    first_val = item[first_key]
                    if isinstance(first_val, dict) and _is_flow_dict(first_val):
                        lines.append(f"{prefix}- {first_key}: {_to_flow(first_val)}")
                    elif isinstance(first_val, (dict, list)) and first_val:
                        lines.append(f"{prefix}- {first_key}:")
                        if isinstance(first_val, dict):
                            _dump_dict(first_val, lines, indent + 2)
                        else:
                            _dump_list(first_val, lines, indent + 1)
                    else:
                        scalar = _format_scalar(first_val)
                        if scalar:
                            lines.append(f"{prefix}- {first_key}: {scalar}")
                        else:
                            lines.append(f"{prefix}- {first_key}:")

                    # Rest of keys
                    for key in keys[1:]:
                        val = item[key]
                        inner_prefix = "  " * (indent + 1)
                        if isinstance(val, dict):
                            if not val:
                                lines.append(f"{inner_prefix}{key}: {{}}")
                            elif _is_flow_dict(val):
                                lines.append(f"{inner_prefix}{key}: {_to_flow(val)}")
                            else:
                                lines.append(f"{inner_prefix}{key}:")
                                _dump_dict(val, lines, indent + 2)
                        elif isinstance(val, list):
                            if not val:
                                lines.append(f"{inner_prefix}{key}: []")
                            else:
                                lines.append(f"{inner_prefix}{key}:")
                                _dump_list(val, lines, indent + 1)
                        else:
                            scalar = _format_scalar(val)
                            if scalar:
                                lines.append(f"{inner_prefix}{key}: {scalar}")
                            else:
                                lines.append(f"{inner_prefix}{key}:")
                else:
                    lines.append(f"{prefix}- {{}}")
        elif isinstance(item, list):
            lines.append(f"{prefix}-")
            _dump_list(item, lines, indent + 1)
        else:
            lines.append(f"{prefix}- {_format_scalar(item)}")


def _is_flow_dict(d: dict) -> bool:
    """Check if a dict should be rendered in flow style.

    Unity uses flow style for simple references like {fileID: 123}.
    """
    if not d:
        return True
    keys = set(d.keys())
    # Flow style for Unity references
    if keys <= {"fileID", "guid", "type"}:
        return True
    # Flow style for simple vectors (x, y, z, w)
    if keys <= {"x", "y", "z", "w"} and all(isinstance(v, (int, float)) for v in d.values()):
        return True
    # Flow style for colors (r, g, b, a)
    if keys <= {"r", "g", "b", "a"} and all(isinstance(v, (int, float)) for v in d.values()):
        return True
    return False


def _to_flow(d: dict) -> str:
    """Convert a dict to flow style."""
    parts = []
    for k, v in d.items():
        parts.append(f"{k}: {_format_scalar(v)}")
    return "{" + ", ".join(parts) + "}"


def _format_scalar(value: Any) -> str:
    """Format a scalar value for YAML output."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        # Preserve decimal point for floats (0.0 stays as "0.0", not "0")
        return str(value)
    if isinstance(value, str):
        # Empty string - no value after colon
        if not value:
            return ""
        if value in ("true", "false", "null", "yes", "no", "on", "off", "True", "False"):
            return f"'{value}'"
        # Standalone '-' or '~' are interpreted as null in YAML - must quote them
        if value in ("-", "~"):
            return f"'{value}'"
        # Check for special characters that require quoting
        # Note: [] don't require quoting when not at start
        needs_quote = False
        if value.startswith(("[", "{", "*", "&", "!", "|", ">", "'", '"', "%", "@", "`")):
            needs_quote = True
        elif any(c in value for c in ":\n#"):
            needs_quote = True
        elif value.startswith("- ") or value.startswith("? ") or value.startswith("-\t"):
            needs_quote = True

        if needs_quote:
            # Use single quotes, escape internal quotes
            escaped = value.replace("'", "''")
            return f"'{escaped}'"
        # Check if it looks like a number (but not strings with leading zeros)
        if not (value.lstrip("-").startswith("0") and len(value.lstrip("-")) > 1):
            try:
                float(value)
                return f"'{value}'"
            except ValueError:
                pass
        return value
    return str(value)


def iter_dump_unity_object(data: dict[str, Any]) -> Generator[str, None, None]:
    """Dump a Unity YAML object, yielding lines one at a time.

    This is a memory-efficient generator version for large objects.

    Args:
        data: Dictionary to dump

    Yields:
        YAML lines as strings
    """
    yield from _iter_dump_dict(data, indent=0)


def _iter_dump_dict(data: dict[str, Any], indent: int) -> Generator[str, None, None]:
    """Dump a dictionary to YAML lines, yielding each line."""
    prefix = "  " * indent

    for key, value in data.items():
        if isinstance(value, dict):
            if not value:
                yield f"{prefix}{key}: {{}}"
            elif _is_flow_dict(value):
                flow = _to_flow(value)
                yield f"{prefix}{key}: {flow}"
            else:
                yield f"{prefix}{key}:"
                yield from _iter_dump_dict(value, indent + 1)
        elif isinstance(value, list):
            if not value:
                yield f"{prefix}{key}: []"
            else:
                yield f"{prefix}{key}:"
                yield from _iter_dump_list(value, indent)
        else:
            scalar = _format_scalar(value)
            if scalar:
                yield f"{prefix}{key}: {scalar}"
            else:
                yield f"{prefix}{key}:"


def _iter_dump_list(data: list[Any], indent: int) -> Generator[str, None, None]:
    """Dump a list to YAML lines, yielding each line."""
    prefix = "  " * indent

    for item in data:
        if isinstance(item, dict):
            if _is_flow_dict(item):
                flow = _to_flow(item)
                yield f"{prefix}- {flow}"
            else:
                keys = list(item.keys())
                if keys:
                    first_key = keys[0]
                    first_val = item[first_key]
                    if isinstance(first_val, dict) and _is_flow_dict(first_val):
                        yield f"{prefix}- {first_key}: {_to_flow(first_val)}"
                    elif isinstance(first_val, (dict, list)) and first_val:
                        yield f"{prefix}- {first_key}:"
                        if isinstance(first_val, dict):
                            yield from _iter_dump_dict(first_val, indent + 2)
                        else:
                            yield from _iter_dump_list(first_val, indent + 1)
                    else:
                        scalar = _format_scalar(first_val)
                        if scalar:
                            yield f"{prefix}- {first_key}: {scalar}"
                        else:
                            yield f"{prefix}- {first_key}:"

                    for key in keys[1:]:
                        val = item[key]
                        inner_prefix = "  " * (indent + 1)
                        if isinstance(val, dict):
                            if not val:
                                yield f"{inner_prefix}{key}: {{}}"
                            elif _is_flow_dict(val):
                                yield f"{inner_prefix}{key}: {_to_flow(val)}"
                            else:
                                yield f"{inner_prefix}{key}:"
                                yield from _iter_dump_dict(val, indent + 2)
                        elif isinstance(val, list):
                            if not val:
                                yield f"{inner_prefix}{key}: []"
                            else:
                                yield f"{inner_prefix}{key}:"
                                yield from _iter_dump_list(val, indent + 1)
                        else:
                            scalar = _format_scalar(val)
                            if scalar:
                                yield f"{inner_prefix}{key}: {scalar}"
                            else:
                                yield f"{inner_prefix}{key}:"
                else:
                    yield f"{prefix}- {{}}"
        elif isinstance(item, list):
            yield f"{prefix}-"
            yield from _iter_dump_list(item, indent + 1)
        else:
            yield f"{prefix}- {_format_scalar(item)}"

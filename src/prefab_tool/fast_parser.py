"""Unity YAML Parser using rapidyaml.

Provides fast parsing for Unity YAML files using the rapidyaml library.
"""

from __future__ import annotations

import re
from typing import Any

import ryml

# Unity YAML header pattern
UNITY_HEADER = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
"""

# Pattern to match Unity document headers: --- !u!{ClassID} &{fileID}
DOCUMENT_HEADER_PATTERN = re.compile(
    r"^--- !u!(\d+) &(\d+)(?: stripped)?$", re.MULTILINE
)


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
                key = bytes(tree.key(child)).decode('utf-8')
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
        val = val_bytes.decode('utf-8')

        # Handle YAML null values
        if val in ("null", "~", ""):
            return None

        # Try converting to int (but preserve strings with leading zeros)
        if val.lstrip('-').isdigit():
            # Check for leading zeros - keep as string to preserve format
            stripped = val.lstrip('-')
            if len(stripped) > 1 and stripped.startswith('0'):
                # Has leading zeros - keep as string
                return val
            try:
                return int(val)
            except ValueError:
                pass

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
    tree = ryml.parse_in_arena(content.encode('utf-8'))
    return _to_python(tree, tree.root_id())


def fast_parse_unity_yaml(content: str) -> list[tuple[int, int, bool, dict[str, Any]]]:
    """Parse Unity YAML content using rapidyaml.

    Args:
        content: Unity YAML file content

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
            data = {}
        else:
            try:
                tree = ryml.parse_in_arena(doc_content.encode('utf-8'))
                data = _to_python(tree, tree.root_id())
                if data is None:
                    data = {}
            except Exception as e:
                raise ValueError(
                    f"Failed to parse document at line {start_line + 1} "
                    f"(class_id={class_id}, file_id={file_id}): {e}"
                ) from e

        results.append((class_id, file_id, stripped, data))

    return results


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
    if keys <= {"x", "y", "z", "w"} and all(
        isinstance(v, (int, float)) for v in d.values()
    ):
        return True
    # Flow style for colors (r, g, b, a)
    if keys <= {"r", "g", "b", "a"} and all(
        isinstance(v, (int, float)) for v in d.values()
    ):
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
        # Check for special characters that require quoting
        # Note: [] don't require quoting when not at start
        needs_quote = False
        if value.startswith(('[', '{', '*', '&', '!', '|', '>', "'", '"', '%', '@', '`')):
            needs_quote = True
        elif any(c in value for c in ":\n#"):
            needs_quote = True
        elif value.startswith('- ') or value.startswith('? '):
            needs_quote = True

        if needs_quote:
            # Use single quotes, escape internal quotes
            escaped = value.replace("'", "''")
            return f"'{escaped}'"
        # Check if it looks like a number (but not strings with leading zeros)
        if not (value.lstrip('-').startswith('0') and len(value.lstrip('-')) > 1):
            try:
                float(value)
                return f"'{value}'"
            except ValueError:
                pass
        return value
    return str(value)

"""Path-based query and surgical editing for Unity YAML files.

Provides JSONPath-like querying and modification of Unity prefab data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from unityflow.formats import export_to_json
from unityflow.parser import UnityYAMLDocument


@dataclass
class QueryResult:
    """Result of a path-based query."""

    path: str
    value: Any
    file_id: int | None = None


def query_path(doc: UnityYAMLDocument, path: str) -> list[QueryResult]:
    """Query a Unity YAML document using a path expression.

    Path syntax:
        - gameObjects/*/name - all GameObject names
        - gameObjects/12345/name - specific GameObject's name
        - components/*/type - all component types
        - components/12345/localPosition - specific component's position
        - **/m_Name - recursive search for m_Name

    Args:
        doc: The parsed Unity YAML document
        path: The path expression to query

    Returns:
        List of QueryResult objects
    """
    # Export to JSON structure for easier querying
    prefab_json = export_to_json(doc, include_raw=False)
    json_data = prefab_json.to_dict()

    results: list[QueryResult] = []

    # Parse path
    parts = path.split("/")

    if not parts:
        return results

    # Handle different root paths
    root = parts[0]
    rest = parts[1:] if len(parts) > 1 else []

    if root == "gameObjects":
        _query_objects(prefab_json.game_objects, rest, "gameObjects", results)
    elif root == "components":
        _query_objects(prefab_json.components, rest, "components", results)
    elif root == "**":
        # Recursive search
        _query_recursive(json_data, rest, "", results)
    else:
        # Try direct path on full data
        _query_objects(json_data, parts, "", results)

    return results


def _query_objects(
    objects: dict[str, Any],
    path_parts: list[str],
    prefix: str,
    results: list[QueryResult],
) -> None:
    """Query a dictionary of objects."""
    if not path_parts:
        # Return all objects
        for key, value in objects.items():
            results.append(
                QueryResult(
                    path=f"{prefix}/{key}" if prefix else key,
                    value=value,
                    file_id=int(key) if key.isdigit() else None,
                )
            )
        return

    selector = path_parts[0]
    rest = path_parts[1:]

    if selector == "*":
        # Wildcard - query all objects
        for key, obj in objects.items():
            if isinstance(obj, dict):
                _query_value(obj, rest, f"{prefix}/{key}" if prefix else key, results)
            else:
                if not rest:
                    results.append(
                        QueryResult(
                            path=f"{prefix}/{key}" if prefix else key,
                            value=obj,
                            file_id=int(key) if key.isdigit() else None,
                        )
                    )
    elif selector in objects:
        # Specific key
        obj = objects[selector]
        if isinstance(obj, dict):
            _query_value(obj, rest, f"{prefix}/{selector}" if prefix else selector, results)
        else:
            if not rest:
                results.append(
                    QueryResult(
                        path=f"{prefix}/{selector}" if prefix else selector,
                        value=obj,
                        file_id=int(selector) if selector.isdigit() else None,
                    )
                )


def _query_value(
    value: Any,
    path_parts: list[str],
    current_path: str,
    results: list[QueryResult],
) -> None:
    """Query a value at a given path."""
    if not path_parts:
        results.append(QueryResult(path=current_path, value=value))
        return

    key = path_parts[0]
    rest = path_parts[1:]

    if isinstance(value, dict):
        if key == "*":
            for k, v in value.items():
                _query_value(v, rest, f"{current_path}/{k}", results)
        elif key in value:
            _query_value(value[key], rest, f"{current_path}/{key}", results)
    elif isinstance(value, list):
        if key == "*":
            for i, item in enumerate(value):
                _query_value(item, rest, f"{current_path}[{i}]", results)
        elif key.isdigit():
            idx = int(key)
            if 0 <= idx < len(value):
                _query_value(value[idx], rest, f"{current_path}[{idx}]", results)


def _query_recursive(
    value: Any,
    path_parts: list[str],
    current_path: str,
    results: list[QueryResult],
) -> None:
    """Recursively search for a path pattern."""
    if not path_parts:
        return

    target = path_parts[0]
    rest = path_parts[1:]

    if isinstance(value, dict):
        for key, val in value.items():
            new_path = f"{current_path}/{key}" if current_path else key

            # Check if this key matches
            if key == target or (target == "*" and True):
                if rest:
                    _query_value(val, rest, new_path, results)
                else:
                    results.append(QueryResult(path=new_path, value=val))

            # Continue recursive search
            _query_recursive(val, path_parts, new_path, results)

    elif isinstance(value, list):
        for i, item in enumerate(value):
            new_path = f"{current_path}[{i}]"
            _query_recursive(item, path_parts, new_path, results)


def set_value(
    doc: UnityYAMLDocument,
    path: str,
    value: Any,
    *,
    create: bool = False,
) -> bool:
    """Set a value at a specific path in the document.

    Args:
        doc: The Unity YAML document to modify
        path: The path to the value (e.g., "components/12345/localPosition")
        value: The new value to set
        create: If True, create the path if it doesn't exist

    Returns:
        True if the value was set, False if path not found

    Note:
        When creating new fields, they are appended at the end. Unity will
        reorder fields according to the C# script declaration order when
        the file is saved in the editor.
    """
    parts = path.split("/")

    if len(parts) < 2:
        return False

    file_id_str = parts[1]
    property_path = parts[2:] if len(parts) > 2 else []

    # Find the object
    if not file_id_str.isdigit():
        return False

    file_id = int(file_id_str)
    obj = doc.get_by_file_id(file_id)

    if obj is None:
        return False

    content = obj.get_content()
    if content is None:
        return False

    # Navigate to the target
    if not property_path:
        return False

    target = content
    for part in property_path[:-1]:
        if isinstance(target, dict):
            if part in target:
                target = target[part]
            elif create:
                # Create intermediate dict
                target[part] = {}
                target = target[part]
            else:
                return False
        elif isinstance(target, list) and part.isdigit():
            idx = int(part)
            if 0 <= idx < len(target):
                target = target[idx]
            else:
                return False
        else:
            return False

    # Set the value
    final_key = property_path[-1]

    if isinstance(target, dict):
        # Check if key exists
        key_exists = final_key in target

        # Convert JSON-style keys to Unity-style if needed
        if not key_exists:
            # Try m_FieldName format
            unity_key = f"m_{final_key[0].upper()}{final_key[1:]}"
            if unity_key in target:
                final_key = unity_key
                key_exists = True

        if key_exists:
            # Update existing value
            target[final_key] = _convert_value(value)
            return True
        elif create:
            # Create new field (appended at end)
            target[final_key] = _convert_value(value)
            return True
        else:
            return False
    elif isinstance(target, list) and final_key.isdigit():
        idx = int(final_key)
        if 0 <= idx < len(target):
            target[idx] = _convert_value(value)
            return True

    return False


def merge_values(
    doc: UnityYAMLDocument,
    path: str,
    values: dict[str, Any],
    *,
    create: bool = True,
) -> tuple[int, int]:
    """Merge multiple values into a target path in the document.

    This is useful for batch inserting multiple fields at once.

    Args:
        doc: The Unity YAML document to modify
        path: The path to the target dict (e.g., "components/12345")
        values: Dictionary of key-value pairs to merge
        create: If True, create keys that don't exist

    Returns:
        Tuple of (updated_count, created_count)

    Example:
        merge_values(doc, "components/12345", {
            "portalAPrefab": {"fileID": 123, "guid": "abc", "type": 3},
            "portalBPrefab": {"fileID": 456, "guid": "def", "type": 3},
            "rotationStep": 15
        })
    """
    parts = path.split("/")

    if len(parts) < 2:
        return (0, 0)

    file_id_str = parts[1]
    property_path = parts[2:] if len(parts) > 2 else []

    # Find the object
    if not file_id_str.isdigit():
        return (0, 0)

    file_id = int(file_id_str)
    obj = doc.get_by_file_id(file_id)

    if obj is None:
        return (0, 0)

    content = obj.get_content()
    if content is None:
        return (0, 0)

    # Navigate to the target
    target = content
    for part in property_path:
        if isinstance(target, dict):
            if part in target:
                target = target[part]
            elif create:
                target[part] = {}
                target = target[part]
            else:
                return (0, 0)
        elif isinstance(target, list) and part.isdigit():
            idx = int(part)
            if 0 <= idx < len(target):
                target = target[idx]
            else:
                return (0, 0)
        else:
            return (0, 0)

    if not isinstance(target, dict):
        return (0, 0)

    updated_count = 0
    created_count = 0

    for key, value in values.items():
        converted_value = _convert_value(value)
        if key in target:
            target[key] = converted_value
            updated_count += 1
        elif create:
            target[key] = converted_value
            created_count += 1

    return (updated_count, created_count)


def _convert_value(value: Any) -> Any:
    """Convert a value from JSON format to Unity YAML format."""
    if isinstance(value, dict):
        # Check if it's a vector
        if set(value.keys()) <= {"x", "y", "z", "w"}:
            return {k: float(v) for k, v in value.items()}
        # Check if it's a reference
        if "fileID" in value:
            return value
        # Recursive conversion
        return {k: _convert_value(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_convert_value(item) for item in value]
    else:
        return value


def get_value(doc: UnityYAMLDocument, path: str) -> Any | None:
    """Get a value at a specific path.

    Args:
        doc: The Unity YAML document
        path: The path to the value

    Returns:
        The value at the path, or None if not found
    """
    results = query_path(doc, path)
    if results:
        return results[0].value
    return None

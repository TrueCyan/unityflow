"""Unity Prefab Normalizer.

Implements deterministic serialization for Unity YAML files by:
1. Sorting documents by fileID
2. Sorting m_Modifications arrays
3. Normalizing floating-point values
4. Normalizing quaternions (w >= 0)
5. Reordering MonoBehaviour fields according to C# script declaration order
6. Syncing fields with C# script (remove obsolete, add missing, merge renamed)
7. Preserving original fileIDs for external reference compatibility

Note: Script-based operations (5, 6) require project_root to be available.
"""

from __future__ import annotations

import math
import struct
from pathlib import Path
from typing import Any

from unityflow.builtin_schema import get_builtin_fields
from unityflow.parser import UnityYAMLDocument, UnityYAMLObject

_MONOBEHAVIOUR_CLASS_ID = 114

_TERMINAL_BASE_CLASSES = frozenset(
    {
        "MonoBehaviour",
        "ScriptableObject",
        "StateMachineBehaviour",
        "NetworkBehaviour",
        "Component",
        "Behaviour",
        "Object",
        "UIBehaviour",
    }
)

# Properties that contain quaternion values
QUATERNION_PROPERTIES = {
    "m_LocalRotation",
    "m_Rotation",
    "localRotation",
    "rotation",
}

# Properties that should use hex float format
FLOAT_PROPERTIES_HEX = {
    "m_LocalPosition",
    "m_LocalRotation",
    "m_LocalScale",
    "m_Position",
    "m_Rotation",
    "m_Scale",
    "m_Center",
    "m_Size",
    "m_Offset",
}

# Properties that contain order-independent arrays of references
# NOTE: We no longer sort any of these arrays because:
# - m_Children: affects Hierarchy order (rendering order, UI overlays)
# - m_Component: affects Inspector display order and GetComponents() order
# - Both may be intentionally ordered by developers for readability
ORDER_INDEPENDENT_ARRAYS: set[str] = set()  # Empty - preserve all array orders

_ROOT_GO_PROPERTY_PATHS = frozenset(
    {"m_IsActive", "m_Layer", "m_TagString", "m_StaticEditorFlags", "m_Icon", "m_NavMeshLayer"}
)


class UnityPrefabNormalizer:
    """Normalizes Unity prefab files for deterministic serialization."""

    def __init__(
        self,
        use_hex_floats: bool = False,  # Default to decimal for readability
        float_precision: int = 6,
        project_root: str | Path | None = None,
    ):
        """Initialize the normalizer.

        Args:
            use_hex_floats: Use IEEE 754 hex format for floats (lossless but less readable)
            float_precision: Decimal places for float normalization (if not using hex)
            project_root: Unity project root for script resolution (auto-detected if None)
        """
        self.use_hex_floats = use_hex_floats
        self.float_precision = float_precision
        self.project_root = Path(project_root) if project_root else None
        self._script_cache: Any = None  # Lazy initialized ScriptFieldCache
        self._script_info_cache: dict[str, Any] = {}  # Cache for ScriptInfo by GUID
        self._guid_index: Any = None  # Lazy initialized GUIDIndex

    def normalize_file(self, input_path: str | Path, output_path: str | Path | None = None) -> str:
        """Normalize a Unity YAML file.

        Args:
            input_path: Path to the input file
            output_path: Path to save the normalized file (if None, returns content only)

        Returns:
            The normalized YAML content
        """
        input_path = Path(input_path)

        # Auto-detect project root if not specified
        if self.project_root is None:
            from unityflow.asset_tracker import find_unity_project_root

            self.project_root = find_unity_project_root(input_path)

        doc = UnityYAMLDocument.load(input_path)
        self.normalize_document(doc)

        content = doc.dump()

        if output_path:
            Path(output_path).write_text(content, encoding="utf-8", newline="\n")

        return content

    def normalize_document(self, doc: UnityYAMLDocument) -> None:
        """Normalize a UnityYAMLDocument in place.

        Args:
            doc: The document to normalize
        """
        for obj in doc.objects:
            self._normalize_object(obj, source_path=doc.source_path)

        doc.objects.sort(key=lambda o: o.file_id)

    def _normalize_object(self, obj: UnityYAMLObject, source_path: Path | None = None) -> None:
        """Normalize a single Unity YAML object."""
        content = obj.get_content()
        if content is None:
            return

        if "m_Modification" in content:
            if source_path is not None:
                self._normalize_m_name_override(content, source_path)
            self._sort_modifications(content["m_Modification"])

        # Process MonoBehaviour fields (requires project_root for script parsing)
        if obj.class_id == _MONOBEHAVIOUR_CLASS_ID and self.project_root:
            # Sync fields with C# script (remove obsolete, add missing, merge renamed)
            self._cleanup_obsolete_fields(obj)

            # Reorder MonoBehaviour fields according to C# script declaration order
            self._reorder_monobehaviour_fields(obj)

        if obj.class_id != _MONOBEHAVIOUR_CLASS_ID:
            self._strip_nonstandard_fields(obj)

        # Recursively normalize the data
        self._normalize_value(obj.data, parent_key=None)

    def _strip_nonstandard_fields(self, obj: UnityYAMLObject) -> None:
        schema = get_builtin_fields(obj.class_id)
        if schema is None:
            return
        content = obj.get_content()
        if content is None:
            return
        nonstandard = [k for k in content if k not in schema]
        for k in nonstandard:
            del content[k]

    def _reorder_monobehaviour_fields(self, obj: UnityYAMLObject) -> None:
        """Reorder MonoBehaviour fields according to C# script declaration order.

        Args:
            obj: The MonoBehaviour object to reorder
        """
        content = obj.get_content()
        if content is None:
            return

        # Get script reference
        script_ref = content.get("m_Script")
        if not isinstance(script_ref, dict):
            return

        script_guid = script_ref.get("guid")
        if not script_guid:
            return

        # Get field order from script
        field_order = self._get_script_field_order(script_guid)
        if not field_order:
            return

        # Reorder the content fields
        from unityflow.script_parser import reorder_fields

        reordered = reorder_fields(content, field_order, unity_fields_first=True)

        # Replace content in place
        content.clear()
        content.update(reordered)

    def _cleanup_obsolete_fields(self, obj: UnityYAMLObject) -> None:
        """Remove obsolete fields and merge FormerlySerializedAs renamed fields.

        Args:
            obj: The MonoBehaviour object to clean up
        """
        content = obj.get_content()
        if content is None:
            return

        # Get script reference
        script_ref = content.get("m_Script")
        if not isinstance(script_ref, dict):
            return

        script_guid = script_ref.get("guid")
        if not script_guid:
            return

        # Get script info
        script_info = self._get_script_info(script_guid)
        if script_info is None:
            return

        valid_names = script_info.get_valid_field_names()
        rename_mapping = script_info.get_rename_mapping()

        unity_standard_fields = {
            "m_ObjectHideFlags",
            "m_CorrespondingSourceObject",
            "m_PrefabInstance",
            "m_PrefabAsset",
            "m_GameObject",
            "m_Enabled",
            "m_EditorHideFlags",
            "m_Script",
            "m_Name",
            "m_EditorClassIdentifier",
        }

        # First pass: handle FormerlySerializedAs renames
        for old_name, new_name in rename_mapping.items():
            if old_name in content and new_name not in content:
                content[new_name] = content[old_name]

        # Second pass: remove obsolete fields
        # valid_names includes inherited fields from the full inheritance chain
        fields_to_remove = []
        for field_name in content:
            if field_name in unity_standard_fields:
                continue
            if field_name not in valid_names:
                fields_to_remove.append(field_name)

        for field_name in fields_to_remove:
            del content[field_name]

        # Third pass: add missing fields with default values
        existing_names = set(content.keys())
        missing_fields = script_info.get_missing_fields(existing_names)

        for field in missing_fields:
            if field.default_value is not None:
                content[field.unity_name] = field.default_value

        if script_info.nested_types:
            self._sync_nested_fields(content, script_info, script_info.nested_types)

    def _sync_nested_fields(
        self,
        content: dict[str, Any],
        type_info: Any,
        nested_types: dict[str, Any],
    ) -> None:
        from unityflow.script_parser import extract_element_type

        for f in type_info.fields:
            value = content.get(f.unity_name)
            if value is None:
                continue

            element_type = extract_element_type(f.field_type)
            direct_type = f.field_type.strip()

            matched_type = None
            if element_type and element_type in nested_types:
                matched_type = element_type
            elif direct_type in nested_types:
                matched_type = direct_type

            if matched_type is None:
                continue

            nested_info = nested_types[matched_type]

            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        self._sync_struct_fields(item, nested_info, nested_types)
            elif isinstance(value, dict):
                self._sync_struct_fields(value, nested_info, nested_types)

    def _sync_struct_fields(
        self,
        data: dict[str, Any],
        nested_info: Any,
        nested_types: dict[str, Any],
    ) -> None:
        rename_mapping = nested_info.get_rename_mapping()

        for old_name, new_name in rename_mapping.items():
            if old_name in data and new_name not in data:
                data[new_name] = data[old_name]

        valid_names = nested_info.get_valid_field_names()
        fields_to_remove = [name for name in data if name not in valid_names]
        for name in fields_to_remove:
            del data[name]

        existing_names = set(data.keys())
        for f in nested_info.get_missing_fields(existing_names):
            if f.default_value is not None:
                data[f.unity_name] = f.default_value

        if nested_info.nested_types:
            self._sync_nested_fields(data, nested_info, nested_info.nested_types)

    def _get_script_info(self, script_guid: str):
        """Get script info for a script by GUID (with caching).

        Args:
            script_guid: The GUID of the script

        Returns:
            ScriptInfo object or None if not found
        """
        # Check cache first
        if script_guid in self._script_info_cache:
            return self._script_info_cache[script_guid]

        if self.project_root is None:
            return None

        # Lazy initialize GUID index
        if self._guid_index is None:
            from unityflow.asset_tracker import get_lazy_guid_index

            self._guid_index = get_lazy_guid_index(self.project_root)

        # Find script path
        script_path = self._guid_index.get_path(script_guid)
        if script_path is None:
            self._script_info_cache[script_guid] = None
            return None

        # Resolve to absolute path
        if not script_path.is_absolute():
            script_path = self.project_root / script_path

        # Check if it's a C# script
        if script_path.suffix.lower() != ".cs":
            self._script_info_cache[script_guid] = None
            return None

        # Parse script with inheritance chain
        from unityflow.script_parser import parse_script_file

        result = parse_script_file(script_path)
        if result is not None:
            self._resolve_inheritance(result)
        self._script_info_cache[script_guid] = result
        return result

    def _resolve_inheritance(self, info, visited: set[str] | None = None) -> None:
        """Resolve inheritance chain and merge parent fields into info."""
        from unityflow.script_parser import parse_script_file

        if visited is None:
            visited = set()

        base = info.base_class
        if not base or base in visited:
            return

        if base in _TERMINAL_BASE_CLASSES:
            return

        visited.add(base)

        base_path = self._find_script_by_class_name(base)
        if base_path is None:
            return

        base_info = parse_script_file(base_path)
        if base_info is None:
            return

        self._resolve_inheritance(base_info, visited)

        existing_names = {f.name for f in info.fields}
        for field in base_info.fields:
            if field.name not in existing_names:
                info.fields.insert(0, field)

        for type_name, nested in base_info.nested_types.items():
            if type_name not in info.nested_types:
                info.nested_types[type_name] = nested

    def _find_script_by_class_name(self, class_name: str) -> Path | None:
        if self._guid_index is None:
            return None
        for path in self._guid_index.path_to_guid:
            if path.suffix == ".cs" and path.stem == class_name:
                if path.is_absolute():
                    return path
                if self.project_root:
                    return self.project_root / path
        return None

    def _get_script_field_order(self, script_guid: str) -> list[str] | None:
        """Get field order for a script by GUID (with caching).

        Args:
            script_guid: The GUID of the script

        Returns:
            List of field names in declaration order, or None if not found
        """
        if self.project_root is None:
            return None

        # Lazy initialize cache
        if self._script_cache is None:
            from unityflow.asset_tracker import get_lazy_guid_index
            from unityflow.script_parser import ScriptFieldCache

            # Lazy initialize GUID index
            if self._guid_index is None:
                self._guid_index = get_lazy_guid_index(self.project_root)

            self._script_cache = ScriptFieldCache(
                guid_index=self._guid_index,
                project_root=self.project_root,
            )

        return self._script_cache.get_field_order(script_guid)

    def _normalize_m_name_override(self, content: dict[str, Any], source_path: Path) -> None:
        modification = content.get("m_Modification")
        if not isinstance(modification, dict):
            return

        mods = modification.get("m_Modifications")
        if not isinstance(mods, list):
            return

        file_stem = source_path.stem

        for mod in mods:
            if mod.get("propertyPath") == "m_Name":
                mod["value"] = file_stem
                return

        source_prefab = content.get("m_SourcePrefab")
        if not isinstance(source_prefab, dict):
            return
        source_guid = source_prefab.get("guid")
        if not source_guid:
            return

        for mod in mods:
            if mod.get("propertyPath") in _ROOT_GO_PROPERTY_PATHS:
                target = mod.get("target")
                if isinstance(target, dict) and target.get("guid") == source_guid:
                    mods.append(
                        {
                            "target": dict(target),
                            "propertyPath": "m_Name",
                            "value": file_stem,
                            "objectReference": {"fileID": 0},
                        }
                    )
                    return

    def _sort_modifications(self, modification: dict[str, Any]) -> None:
        """Sort m_Modifications array for deterministic order."""
        if not isinstance(modification, dict):
            return

        mods = modification.get("m_Modifications")
        if isinstance(mods, list) and mods:
            sorted_mods = self._sort_modification_list(list(mods))
            mods.clear()
            mods.extend(sorted_mods)

        # Sort m_RemovedComponents
        removed = modification.get("m_RemovedComponents")
        if isinstance(removed, list) and removed:
            sorted_removed = sorted(
                removed,
                key=lambda r: self._get_modification_sort_key(r, "target"),
            )
            removed.clear()
            removed.extend(sorted_removed)

        # Sort m_AddedComponents
        added = modification.get("m_AddedComponents")
        if isinstance(added, list) and added:
            sorted_added = sorted(
                added,
                key=lambda a: self._get_modification_sort_key(a, "targetCorrespondingSourceObject"),
            )
            added.clear()
            added.extend(sorted_added)

    def _sort_modification_list(self, mods: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Sort a list of modifications by target.fileID and propertyPath."""
        return sorted(mods, key=self._modification_sort_key)

    def _modification_sort_key(self, mod: dict[str, Any]) -> tuple[int, str]:
        """Generate sort key for a modification entry."""
        target = mod.get("target", {})
        file_id = target.get("fileID", 0) if isinstance(target, dict) else 0
        property_path = mod.get("propertyPath", "")
        return (file_id, property_path)

    def _get_modification_sort_key(self, item: dict[str, Any], target_key: str) -> tuple[int, str, int]:
        """Generate sort key for removed/added component entries."""
        target = item.get(target_key, {})
        file_id = target.get("fileID", 0) if isinstance(target, dict) else 0
        guid = target.get("guid", "") if isinstance(target, dict) else ""
        ref_type = target.get("type", 0) if isinstance(target, dict) else 0
        return (file_id, guid, ref_type)

    def _sort_reference_array(self, arr: list[Any]) -> None:
        """Sort an array of references by fileID for deterministic order.

        Handles arrays like m_Component and m_Children which contain
        references in the format: {component: {fileID: X}} or {fileID: X}
        """

        def get_sort_key(item: Any) -> int:
            if isinstance(item, dict):
                # Handle {component: {fileID: X}} format (m_Component)
                if "component" in item:
                    ref = item["component"]
                    if isinstance(ref, dict):
                        return ref.get("fileID", 0)
                # Handle {fileID: X} format (m_Children)
                if "fileID" in item:
                    return item.get("fileID", 0)
            return 0

        # Sort in place
        sorted_items = sorted(arr, key=get_sort_key)
        arr.clear()
        arr.extend(sorted_items)

    def _normalize_value(self, value: Any, parent_key: str | None = None, property_path: str = "") -> Any:
        """Recursively normalize a value."""
        if isinstance(value, dict):
            # Check if this is a quaternion
            if parent_key in QUATERNION_PROPERTIES:
                if self._is_quaternion_dict(value):
                    return self._normalize_quaternion_dict(value)

            # Check if this is a vector/position that should use hex floats
            if self.use_hex_floats:
                if parent_key in FLOAT_PROPERTIES_HEX and self._is_vector_dict(value):
                    return self._normalize_vector_to_hex(value)

            # Recursively normalize dict values
            for key in value:
                value[key] = self._normalize_value(
                    value[key],
                    parent_key=key,
                    property_path=f"{property_path}.{key}" if property_path else key,
                )
            return value

        elif isinstance(value, list):
            # Sort order-independent arrays (like m_Component, m_Children)
            if parent_key in ORDER_INDEPENDENT_ARRAYS and value:
                self._sort_reference_array(value)

            # Recursively normalize list items
            for i, item in enumerate(value):
                value[i] = self._normalize_value(
                    item,
                    parent_key=parent_key,
                    property_path=f"{property_path}[{i}]",
                )
            return value

        elif isinstance(value, float):
            return self._normalize_float(value)

        return value

    def _is_quaternion_dict(self, d: dict) -> bool:
        """Check if a dict represents a quaternion (has x, y, z, w keys)."""
        return all(k in d for k in ("x", "y", "z", "w"))

    def _is_vector_dict(self, d: dict) -> bool:
        """Check if a dict represents a vector (has x, y, z or x, y keys)."""
        keys = set(d.keys())
        return keys == {"x", "y", "z"} or keys == {"x", "y"} or keys == {"x", "y", "z", "w"}

    def _normalize_quaternion_dict(self, q: dict) -> dict:
        """Normalize a quaternion dict to ensure w >= 0."""
        x = float(q.get("x", 0))
        y = float(q.get("y", 0))
        z = float(q.get("z", 0))
        w = float(q.get("w", 1))

        # Negate all components if w < 0
        if w < 0:
            x, y, z, w = -x, -y, -z, -w

        # Normalize to unit length
        length = math.sqrt(x * x + y * y + z * z + w * w)
        if length > 0:
            x /= length
            y /= length
            z /= length
            w /= length

        # Update in place
        if self.use_hex_floats:
            q["x"] = self._float_to_hex(x)
            q["y"] = self._float_to_hex(y)
            q["z"] = self._float_to_hex(z)
            q["w"] = self._float_to_hex(w)
        else:
            q["x"] = self._normalize_float(x)
            q["y"] = self._normalize_float(y)
            q["z"] = self._normalize_float(z)
            q["w"] = self._normalize_float(w)

        return q

    def _normalize_vector_to_hex(self, v: dict) -> dict:
        """Convert vector components to hex float format."""
        for key in v:
            if key in ("x", "y", "z", "w") and isinstance(v[key], int | float):
                v[key] = self._float_to_hex(float(v[key]))
        return v

    def _normalize_float(self, value: float) -> float:
        """Normalize a float value to consistent representation."""
        # Handle special cases
        if math.isnan(value):
            return float("nan")
        if math.isinf(value):
            return float("inf") if value > 0 else float("-inf")

        # Round to specified precision
        rounded = round(value, self.float_precision)

        # Avoid -0.0
        if rounded == 0.0:
            return 0.0

        return rounded

    def _float_to_hex(self, value: float) -> str:
        """Convert a float to IEEE 754 hex representation."""
        # Pack as 32-bit float, then unpack as unsigned int
        packed = struct.pack(">f", value)
        int_val = struct.unpack(">I", packed)[0]
        return f"0x{int_val:08x}"

    def _hex_to_float(self, hex_str: str) -> float:
        """Convert IEEE 754 hex representation back to float."""
        int_val = int(hex_str, 16)
        packed = struct.pack(">I", int_val)
        return struct.unpack(">f", packed)[0]


def normalize_prefab(
    input_path: str | Path,
    output_path: str | Path | None = None,
    **kwargs,
) -> str:
    """Convenience function to normalize a prefab file.

    Args:
        input_path: Path to the input prefab file
        output_path: Optional path to save the normalized file
        **kwargs: Additional arguments passed to UnityPrefabNormalizer

    Returns:
        The normalized YAML content
    """
    normalizer = UnityPrefabNormalizer(**kwargs)
    return normalizer.normalize_file(input_path, output_path)

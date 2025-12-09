"""Unity Prefab Normalizer.

Implements deterministic serialization for Unity YAML files by:
1. Sorting documents by fileID
2. Sorting m_Modifications arrays
3. Sorting order-independent arrays (m_Component, m_Children) by fileID
4. Normalizing floating-point values
5. Normalizing quaternions (w >= 0)
6. Preserving original fileIDs for external reference compatibility
"""

from __future__ import annotations

import math
import struct
from pathlib import Path
from typing import Any

from prefab_tool.parser import UnityYAMLDocument, UnityYAMLObject


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

# Properties that contain order-independent arrays of references (should be sorted)
ORDER_INDEPENDENT_ARRAYS = {
    "m_Component",      # GameObject's component list
    "m_Children",       # Transform's children list
}


class UnityPrefabNormalizer:
    """Normalizes Unity prefab files for deterministic serialization."""

    def __init__(
        self,
        sort_documents: bool = True,
        sort_modifications: bool = True,
        normalize_floats: bool = True,
        use_hex_floats: bool = False,  # Default to decimal for readability
        normalize_quaternions: bool = True,
        float_precision: int = 6,
    ):
        """Initialize the normalizer.

        Args:
            sort_documents: Sort YAML documents by fileID
            sort_modifications: Sort m_Modifications arrays
            normalize_floats: Normalize float representations
            use_hex_floats: Use IEEE 754 hex format for floats (lossless but less readable)
            normalize_quaternions: Ensure quaternion w >= 0
            float_precision: Decimal places for float normalization (if not using hex)
        """
        self.sort_documents = sort_documents
        self.sort_modifications = sort_modifications
        self.normalize_floats = normalize_floats
        self.use_hex_floats = use_hex_floats
        self.normalize_quaternions = normalize_quaternions
        self.float_precision = float_precision

    def normalize_file(self, input_path: str | Path, output_path: str | Path | None = None) -> str:
        """Normalize a Unity YAML file.

        Args:
            input_path: Path to the input file
            output_path: Path to save the normalized file (if None, returns content only)

        Returns:
            The normalized YAML content
        """
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
        # Normalize each object's data
        for obj in doc.objects:
            self._normalize_object(obj)

        # Sort documents by fileID
        if self.sort_documents:
            doc.objects.sort(key=lambda o: o.file_id)

    def _normalize_object(self, obj: UnityYAMLObject) -> None:
        """Normalize a single Unity YAML object."""
        content = obj.get_content()
        if content is None:
            return

        # Sort m_Modifications if present
        if self.sort_modifications and "m_Modification" in content:
            self._sort_modifications(content["m_Modification"])

        # Recursively normalize the data
        self._normalize_value(obj.data, parent_key=None)

    def _sort_modifications(self, modification: dict[str, Any]) -> None:
        """Sort m_Modifications array for deterministic order."""
        if not isinstance(modification, dict):
            return

        # Sort m_Modifications array
        mods = modification.get("m_Modifications")
        if isinstance(mods, list) and mods:
            sorted_mods = self._sort_modification_list(list(mods))
            # Replace contents in place
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

    def _get_modification_sort_key(
        self, item: dict[str, Any], target_key: str
    ) -> tuple[int, str, int]:
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

    def _normalize_value(
        self, value: Any, parent_key: str | None = None, property_path: str = ""
    ) -> Any:
        """Recursively normalize a value."""
        if isinstance(value, dict):
            # Check if this is a quaternion
            if self.normalize_quaternions and parent_key in QUATERNION_PROPERTIES:
                if self._is_quaternion_dict(value):
                    return self._normalize_quaternion_dict(value)

            # Check if this is a vector/position that should use hex floats
            if self.normalize_floats and self.use_hex_floats:
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
            if self.normalize_floats:
                return self._normalize_float(value)
            return value

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
            if key in ("x", "y", "z", "w") and isinstance(v[key], (int, float)):
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

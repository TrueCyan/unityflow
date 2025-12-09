"""LLM-friendly format conversion for Unity YAML files.

Provides JSON export/import for easier manipulation by LLMs and scripts,
with round-trip fidelity through _rawFields preservation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from prefab_tool.parser import UnityYAMLDocument, UnityYAMLObject, CLASS_IDS

# Reverse mapping: class name -> class ID
CLASS_NAME_TO_ID = {name: id for id, name in CLASS_IDS.items()}

# Fields that are represented in the structured format (not raw)
STRUCTURED_FIELDS = {
    # GameObject fields
    "m_Name",
    "m_Layer",
    "m_TagString",
    "m_IsActive",
    "m_Component",
    # Transform fields
    "m_LocalPosition",
    "m_LocalRotation",
    "m_LocalScale",
    "m_Children",
    "m_Father",
    "m_GameObject",
    # MonoBehaviour fields
    "m_Script",
    "m_Enabled",
}


@dataclass
class PrefabJSON:
    """JSON representation of a Unity prefab."""

    metadata: dict[str, Any] = field(default_factory=dict)
    game_objects: dict[str, dict[str, Any]] = field(default_factory=dict)
    components: dict[str, dict[str, Any]] = field(default_factory=dict)
    raw_fields: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "prefabMetadata": self.metadata,
            "gameObjects": self.game_objects,
            "components": self.components,
        }
        if self.raw_fields:
            result["_rawFields"] = self.raw_fields
        return result

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PrefabJSON:
        """Create from dictionary."""
        return cls(
            metadata=data.get("prefabMetadata", {}),
            game_objects=data.get("gameObjects", {}),
            components=data.get("components", {}),
            raw_fields=data.get("_rawFields", {}),
        )

    @classmethod
    def from_json(cls, json_str: str) -> PrefabJSON:
        """Create from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)


def export_to_json(doc: UnityYAMLDocument, include_raw: bool = True) -> PrefabJSON:
    """Export a Unity YAML document to JSON format.

    Args:
        doc: The parsed Unity YAML document
        include_raw: Whether to include _rawFields for round-trip fidelity

    Returns:
        PrefabJSON object
    """
    result = PrefabJSON()

    # Metadata
    result.metadata = {
        "sourcePath": str(doc.source_path) if doc.source_path else None,
        "objectCount": len(doc.objects),
    }

    # Process each object
    for obj in doc.objects:
        file_id = str(obj.file_id)
        content = obj.get_content()

        if content is None:
            continue

        if obj.class_id == 1:  # GameObject
            result.game_objects[file_id] = _export_game_object(obj, content)
            if include_raw:
                raw = _extract_raw_fields(content, {"m_Name", "m_Layer", "m_TagString", "m_IsActive", "m_Component"})
                if raw:
                    result.raw_fields[file_id] = raw

        else:  # Component (Transform, MonoBehaviour, etc.)
            result.components[file_id] = _export_component(obj, content)
            if include_raw:
                component_structured = _get_structured_fields_for_class(obj.class_id)
                raw = _extract_raw_fields(content, component_structured)
                if raw:
                    result.raw_fields[file_id] = raw

    return result


def _export_game_object(obj: UnityYAMLObject, content: dict[str, Any]) -> dict[str, Any]:
    """Export a GameObject to JSON format."""
    result: dict[str, Any] = {
        "name": content.get("m_Name", ""),
        "layer": content.get("m_Layer", 0),
        "tag": content.get("m_TagString", "Untagged"),
        "isActive": content.get("m_IsActive", 1) == 1,
    }

    # Extract component references
    components = content.get("m_Component", [])
    if components:
        result["components"] = [
            str(c.get("component", {}).get("fileID", 0))
            for c in components
            if isinstance(c, dict) and "component" in c
        ]

    return result


def _export_component(obj: UnityYAMLObject, content: dict[str, Any]) -> dict[str, Any]:
    """Export a component to JSON format."""
    result: dict[str, Any] = {
        "type": obj.class_name,
        "classId": obj.class_id,
    }

    # GameObject reference
    go_ref = content.get("m_GameObject", {})
    if isinstance(go_ref, dict) and "fileID" in go_ref:
        result["gameObject"] = str(go_ref["fileID"])

    # Type-specific export
    if obj.class_id == 4:  # Transform
        result.update(_export_transform(content))
    elif obj.class_id == 114:  # MonoBehaviour
        result.update(_export_monobehaviour(content))
    elif obj.class_id == 1001:  # PrefabInstance
        result.update(_export_prefab_instance(content))
    else:
        # Generic component - export known fields
        result.update(_export_generic_component(content))

    return result


def _export_transform(content: dict[str, Any]) -> dict[str, Any]:
    """Export Transform-specific fields."""
    result: dict[str, Any] = {}

    # Position, rotation, scale
    if "m_LocalPosition" in content:
        result["localPosition"] = _export_vector(content["m_LocalPosition"])
    if "m_LocalRotation" in content:
        result["localRotation"] = _export_quaternion(content["m_LocalRotation"])
    if "m_LocalScale" in content:
        result["localScale"] = _export_vector(content["m_LocalScale"])

    # Parent reference
    father = content.get("m_Father", {})
    if isinstance(father, dict) and father.get("fileID", 0) != 0:
        result["parent"] = str(father["fileID"])

    # Children references
    children = content.get("m_Children", [])
    if children:
        result["children"] = [
            str(c.get("fileID", 0))
            for c in children
            if isinstance(c, dict) and c.get("fileID", 0) != 0
        ]

    return result


def _export_monobehaviour(content: dict[str, Any]) -> dict[str, Any]:
    """Export MonoBehaviour-specific fields."""
    result: dict[str, Any] = {}

    # Script reference
    script = content.get("m_Script", {})
    if isinstance(script, dict):
        result["scriptRef"] = {
            "fileID": script.get("fileID", 0),
            "guid": script.get("guid", ""),
            "type": script.get("type", 0),
        }

    # Enabled state
    if "m_Enabled" in content:
        result["enabled"] = content["m_Enabled"] == 1

    # Custom properties (everything else)
    properties: dict[str, Any] = {}
    skip_keys = {"m_ObjectHideFlags", "m_CorrespondingSourceObject", "m_PrefabInstance",
                 "m_PrefabAsset", "m_GameObject", "m_Enabled", "m_Script", "m_EditorHideFlags",
                 "m_EditorClassIdentifier"}

    for key, value in content.items():
        if key not in skip_keys:
            properties[key] = _export_value(value)

    if properties:
        result["properties"] = properties

    return result


def _export_prefab_instance(content: dict[str, Any]) -> dict[str, Any]:
    """Export PrefabInstance-specific fields."""
    result: dict[str, Any] = {}

    # Source prefab
    source = content.get("m_SourcePrefab", {})
    if isinstance(source, dict):
        result["sourcePrefab"] = {
            "fileID": source.get("fileID", 0),
            "guid": source.get("guid", ""),
        }

    # Modifications
    modification = content.get("m_Modification", {})
    if isinstance(modification, dict):
        mods = modification.get("m_Modifications", [])
        if mods:
            result["modifications"] = [
                {
                    "target": {
                        "fileID": m.get("target", {}).get("fileID", 0),
                        "guid": m.get("target", {}).get("guid", ""),
                    },
                    "propertyPath": m.get("propertyPath", ""),
                    "value": m.get("value"),
                }
                for m in mods
                if isinstance(m, dict)
            ]

    return result


def _export_generic_component(content: dict[str, Any]) -> dict[str, Any]:
    """Export a generic component's fields."""
    result: dict[str, Any] = {}

    skip_keys = {"m_ObjectHideFlags", "m_CorrespondingSourceObject", "m_PrefabInstance",
                 "m_PrefabAsset", "m_GameObject"}

    for key, value in content.items():
        if key not in skip_keys:
            # Convert m_FieldName to fieldName
            json_key = key[2].lower() + key[3:] if key.startswith("m_") else key
            result[json_key] = _export_value(value)

    return result


def _export_vector(v: dict[str, Any]) -> dict[str, float]:
    """Export a vector to JSON."""
    return {
        "x": float(v.get("x", 0)),
        "y": float(v.get("y", 0)),
        "z": float(v.get("z", 0)),
    }


def _export_quaternion(q: dict[str, Any]) -> dict[str, float]:
    """Export a quaternion to JSON."""
    return {
        "x": float(q.get("x", 0)),
        "y": float(q.get("y", 0)),
        "z": float(q.get("z", 0)),
        "w": float(q.get("w", 1)),
    }


def _export_value(value: Any) -> Any:
    """Export a generic value, converting Unity-specific types."""
    if isinstance(value, dict):
        # Check if it's a reference
        if "fileID" in value:
            return {
                "fileID": value.get("fileID", 0),
                "guid": value.get("guid"),
                "type": value.get("type"),
            }
        # Check if it's a vector
        if set(value.keys()) <= {"x", "y", "z", "w"}:
            return {k: float(v) for k, v in value.items()}
        # Recursive export
        return {k: _export_value(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_export_value(item) for item in value]
    else:
        return value


def _extract_raw_fields(content: dict[str, Any], structured: set[str]) -> dict[str, Any]:
    """Extract fields that aren't in the structured representation."""
    raw: dict[str, Any] = {}

    for key, value in content.items():
        if key not in structured and not key.startswith("m_Corresponding") and not key.startswith("m_Prefab"):
            raw[key] = value

    return raw


def _get_structured_fields_for_class(class_id: int) -> set[str]:
    """Get the set of structured fields for a class ID."""
    if class_id == 4:  # Transform
        return {"m_LocalPosition", "m_LocalRotation", "m_LocalScale", "m_Children", "m_Father", "m_GameObject"}
    elif class_id == 114:  # MonoBehaviour
        return {"m_Script", "m_Enabled", "m_GameObject"}
    elif class_id == 1001:  # PrefabInstance
        return {"m_SourcePrefab", "m_Modification"}
    else:
        return {"m_GameObject"}


def export_file_to_json(
    input_path: str | Path,
    output_path: str | Path | None = None,
    include_raw: bool = True,
    indent: int = 2,
) -> str:
    """Export a Unity YAML file to JSON.

    Args:
        input_path: Path to the Unity YAML file
        output_path: Optional path to save the JSON output
        include_raw: Whether to include _rawFields
        indent: JSON indentation level

    Returns:
        The JSON string
    """
    doc = UnityYAMLDocument.load(input_path)
    prefab_json = export_to_json(doc, include_raw=include_raw)
    json_str = prefab_json.to_json(indent=indent)

    if output_path:
        Path(output_path).write_text(json_str, encoding="utf-8")

    return json_str


def import_from_json(prefab_json: PrefabJSON) -> UnityYAMLDocument:
    """Import a PrefabJSON back to UnityYAMLDocument.

    This enables round-trip conversion: YAML -> JSON -> YAML
    LLMs can modify the JSON and this function converts it back to Unity YAML.

    Args:
        prefab_json: The PrefabJSON object to convert

    Returns:
        UnityYAMLDocument ready to be saved
    """
    doc = UnityYAMLDocument()

    # Import GameObjects (class_id = 1)
    for file_id_str, go_data in prefab_json.game_objects.items():
        file_id = int(file_id_str)
        raw_fields = prefab_json.raw_fields.get(file_id_str, {})
        obj = _import_game_object(file_id, go_data, raw_fields)
        doc.objects.append(obj)

    # Import Components
    for file_id_str, comp_data in prefab_json.components.items():
        file_id = int(file_id_str)
        raw_fields = prefab_json.raw_fields.get(file_id_str, {})
        obj = _import_component(file_id, comp_data, raw_fields)
        doc.objects.append(obj)

    # Sort by file_id for consistent output
    doc.objects.sort(key=lambda o: o.file_id)

    return doc


def _import_game_object(
    file_id: int, data: dict[str, Any], raw_fields: dict[str, Any]
) -> UnityYAMLObject:
    """Import a GameObject from JSON format."""
    content: dict[str, Any] = {}

    # Default Unity fields
    content["m_ObjectHideFlags"] = raw_fields.get("m_ObjectHideFlags", 0)
    content["m_CorrespondingSourceObject"] = {"fileID": 0}
    content["m_PrefabInstance"] = {"fileID": 0}
    content["m_PrefabAsset"] = {"fileID": 0}
    content["serializedVersion"] = raw_fields.get("serializedVersion", 6)

    # Component references
    components = data.get("components", [])
    if components:
        content["m_Component"] = [
            {"component": {"fileID": int(c)}} for c in components
        ]
    else:
        content["m_Component"] = []

    # Core fields from JSON
    content["m_Layer"] = data.get("layer", 0)
    content["m_Name"] = data.get("name", "")
    content["m_TagString"] = data.get("tag", "Untagged")

    # Restore raw fields that aren't structured
    for key in ["m_Icon", "m_NavMeshLayer", "m_StaticEditorFlags"]:
        if key in raw_fields:
            content[key] = raw_fields[key]
        else:
            # Default values
            if key == "m_Icon":
                content[key] = {"fileID": 0}
            else:
                content[key] = 0

    # isActive: bool -> 1/0
    is_active = data.get("isActive", True)
    content["m_IsActive"] = 1 if is_active else 0

    # Merge any additional raw fields
    for key, value in raw_fields.items():
        if key not in content:
            content[key] = value

    return UnityYAMLObject(
        class_id=1,
        file_id=file_id,
        data={"GameObject": content},
        stripped=False,
    )


def _import_component(
    file_id: int, data: dict[str, Any], raw_fields: dict[str, Any]
) -> UnityYAMLObject:
    """Import a component from JSON format."""
    class_id = data.get("classId", 0)
    comp_type = data.get("type", "")

    # Determine class_id if not provided
    if class_id == 0 and comp_type:
        class_id = CLASS_NAME_TO_ID.get(comp_type, 0)

    # Get the root key (class name)
    root_key = CLASS_IDS.get(class_id, comp_type or f"Unknown{class_id}")

    # Build content based on component type
    if class_id == 4:  # Transform
        content = _import_transform(data, raw_fields)
    elif class_id == 224:  # RectTransform
        content = _import_rect_transform(data, raw_fields)
    elif class_id == 114:  # MonoBehaviour
        content = _import_monobehaviour(data, raw_fields)
    elif class_id == 1001:  # PrefabInstance
        content = _import_prefab_instance(data, raw_fields)
    else:
        content = _import_generic_component(data, raw_fields)

    return UnityYAMLObject(
        class_id=class_id,
        file_id=file_id,
        data={root_key: content},
        stripped=False,
    )


def _import_transform(
    data: dict[str, Any], raw_fields: dict[str, Any]
) -> dict[str, Any]:
    """Import Transform-specific fields."""
    content: dict[str, Any] = {}

    # Default Unity fields
    content["m_ObjectHideFlags"] = raw_fields.get("m_ObjectHideFlags", 0)
    content["m_CorrespondingSourceObject"] = {"fileID": 0}
    content["m_PrefabInstance"] = {"fileID": 0}
    content["m_PrefabAsset"] = {"fileID": 0}

    # GameObject reference
    if "gameObject" in data:
        content["m_GameObject"] = {"fileID": int(data["gameObject"])}
    else:
        content["m_GameObject"] = {"fileID": 0}

    content["serializedVersion"] = raw_fields.get("serializedVersion", 2)

    # Transform properties
    if "localRotation" in data:
        content["m_LocalRotation"] = _import_vector(data["localRotation"], include_w=True)
    else:
        content["m_LocalRotation"] = {"x": 0, "y": 0, "z": 0, "w": 1}

    if "localPosition" in data:
        content["m_LocalPosition"] = _import_vector(data["localPosition"])
    else:
        content["m_LocalPosition"] = {"x": 0, "y": 0, "z": 0}

    if "localScale" in data:
        content["m_LocalScale"] = _import_vector(data["localScale"])
    else:
        content["m_LocalScale"] = {"x": 1, "y": 1, "z": 1}

    # Raw fields like m_ConstrainProportionsScale
    if "m_ConstrainProportionsScale" in raw_fields:
        content["m_ConstrainProportionsScale"] = raw_fields["m_ConstrainProportionsScale"]
    else:
        content["m_ConstrainProportionsScale"] = 0

    # Children references
    if "children" in data and data["children"]:
        content["m_Children"] = [{"fileID": int(c)} for c in data["children"]]
    else:
        content["m_Children"] = []

    # Parent reference
    if "parent" in data and data["parent"]:
        content["m_Father"] = {"fileID": int(data["parent"])}
    else:
        content["m_Father"] = {"fileID": 0}

    # Euler angles hint
    if "m_LocalEulerAnglesHint" in raw_fields:
        content["m_LocalEulerAnglesHint"] = raw_fields["m_LocalEulerAnglesHint"]
    else:
        content["m_LocalEulerAnglesHint"] = {"x": 0, "y": 0, "z": 0}

    # Merge any additional raw fields
    for key, value in raw_fields.items():
        if key not in content:
            content[key] = value

    return content


def _import_rect_transform(
    data: dict[str, Any], raw_fields: dict[str, Any]
) -> dict[str, Any]:
    """Import RectTransform-specific fields (extends Transform)."""
    # Start with Transform fields
    content = _import_transform(data, raw_fields)

    # RectTransform-specific fields from raw_fields or defaults
    rect_fields = [
        "m_AnchorMin", "m_AnchorMax", "m_AnchoredPosition",
        "m_SizeDelta", "m_Pivot"
    ]

    for field in rect_fields:
        if field in raw_fields:
            content[field] = raw_fields[field]

    return content


def _import_monobehaviour(
    data: dict[str, Any], raw_fields: dict[str, Any]
) -> dict[str, Any]:
    """Import MonoBehaviour-specific fields."""
    content: dict[str, Any] = {}

    # Default Unity fields
    content["m_ObjectHideFlags"] = raw_fields.get("m_ObjectHideFlags", 0)
    content["m_CorrespondingSourceObject"] = {"fileID": 0}
    content["m_PrefabInstance"] = {"fileID": 0}
    content["m_PrefabAsset"] = {"fileID": 0}

    # GameObject reference
    if "gameObject" in data:
        content["m_GameObject"] = {"fileID": int(data["gameObject"])}
    else:
        content["m_GameObject"] = {"fileID": 0}

    # Enabled state
    enabled = data.get("enabled", True)
    content["m_Enabled"] = 1 if enabled else 0

    # Editor fields
    content["m_EditorHideFlags"] = raw_fields.get("m_EditorHideFlags", 0)
    content["m_EditorClassIdentifier"] = raw_fields.get("m_EditorClassIdentifier", "")

    # Script reference
    if "scriptRef" in data:
        script_ref = data["scriptRef"]
        content["m_Script"] = {
            "fileID": script_ref.get("fileID", 0),
            "guid": script_ref.get("guid", ""),
            "type": script_ref.get("type", 0),
        }
    elif "m_Script" in raw_fields:
        content["m_Script"] = raw_fields["m_Script"]
    else:
        content["m_Script"] = {"fileID": 0}

    # Custom properties
    properties = data.get("properties", {})
    for key, value in properties.items():
        content[key] = _import_value(value)

    # Merge additional raw fields
    for key, value in raw_fields.items():
        if key not in content:
            content[key] = value

    return content


def _import_prefab_instance(
    data: dict[str, Any], raw_fields: dict[str, Any]
) -> dict[str, Any]:
    """Import PrefabInstance-specific fields."""
    content: dict[str, Any] = {}

    # Default Unity fields
    content["m_ObjectHideFlags"] = raw_fields.get("m_ObjectHideFlags", 0)
    content["m_CorrespondingSourceObject"] = {"fileID": 0}
    content["m_PrefabInstance"] = {"fileID": 0}
    content["m_PrefabAsset"] = {"fileID": 0}

    # Source prefab
    if "sourcePrefab" in data:
        src = data["sourcePrefab"]
        content["m_SourcePrefab"] = {
            "fileID": src.get("fileID", 0),
            "guid": src.get("guid", ""),
            "type": src.get("type", 2),
        }
    elif "m_SourcePrefab" in raw_fields:
        content["m_SourcePrefab"] = raw_fields["m_SourcePrefab"]

    # Modifications
    modification: dict[str, Any] = {}

    # TransformParent
    if "m_Modification" in raw_fields and "m_TransformParent" in raw_fields["m_Modification"]:
        modification["m_TransformParent"] = raw_fields["m_Modification"]["m_TransformParent"]
    else:
        modification["m_TransformParent"] = {"fileID": 0}

    # Modifications list
    if "modifications" in data:
        mods_list = []
        for mod in data["modifications"]:
            target = mod.get("target", {})
            mods_list.append({
                "target": {
                    "fileID": target.get("fileID", 0),
                    "guid": target.get("guid", ""),
                },
                "propertyPath": mod.get("propertyPath", ""),
                "value": mod.get("value"),
                "objectReference": mod.get("objectReference", {"fileID": 0}),
            })
        modification["m_Modifications"] = mods_list
    elif "m_Modification" in raw_fields and "m_Modifications" in raw_fields["m_Modification"]:
        modification["m_Modifications"] = raw_fields["m_Modification"]["m_Modifications"]
    else:
        modification["m_Modifications"] = []

    # RemovedComponents and RemovedGameObjects
    if "m_Modification" in raw_fields:
        for key in ["m_RemovedComponents", "m_RemovedGameObjects", "m_AddedComponents", "m_AddedGameObjects"]:
            if key in raw_fields["m_Modification"]:
                modification[key] = raw_fields["m_Modification"][key]

    if "m_RemovedComponents" not in modification:
        modification["m_RemovedComponents"] = []
    if "m_RemovedGameObjects" not in modification:
        modification["m_RemovedGameObjects"] = []

    content["m_Modification"] = modification

    # Merge additional raw fields
    for key, value in raw_fields.items():
        if key not in content and key != "m_Modification":
            content[key] = value

    return content


def _import_generic_component(
    data: dict[str, Any], raw_fields: dict[str, Any]
) -> dict[str, Any]:
    """Import a generic component's fields."""
    content: dict[str, Any] = {}

    # Default Unity fields
    content["m_ObjectHideFlags"] = raw_fields.get("m_ObjectHideFlags", 0)
    content["m_CorrespondingSourceObject"] = {"fileID": 0}
    content["m_PrefabInstance"] = {"fileID": 0}
    content["m_PrefabAsset"] = {"fileID": 0}

    # GameObject reference
    if "gameObject" in data:
        content["m_GameObject"] = {"fileID": int(data["gameObject"])}
    else:
        content["m_GameObject"] = {"fileID": 0}

    # Convert exported fields back to Unity format
    skip_keys = {"type", "classId", "gameObject"}

    for key, value in data.items():
        if key in skip_keys:
            continue

        # Convert camelCase back to m_PascalCase
        if key[0].islower() and not key.startswith("m_"):
            unity_key = "m_" + key[0].upper() + key[1:]
        else:
            unity_key = key

        content[unity_key] = _import_value(value)

    # Merge raw fields
    for key, value in raw_fields.items():
        if key not in content:
            content[key] = value

    return content


def _import_vector(v: dict[str, Any], include_w: bool = False) -> dict[str, Any]:
    """Import a vector from JSON."""
    result = {
        "x": v.get("x", 0),
        "y": v.get("y", 0),
        "z": v.get("z", 0),
    }
    if include_w or "w" in v:
        result["w"] = v.get("w", 1)
    return result


def _import_value(value: Any) -> Any:
    """Import a generic value, converting JSON types back to Unity format."""
    if isinstance(value, dict):
        # Check if it's a reference
        if "fileID" in value:
            ref: dict[str, Any] = {"fileID": value["fileID"]}
            if value.get("guid"):
                ref["guid"] = value["guid"]
            if value.get("type") is not None:
                ref["type"] = value["type"]
            return ref
        # Recursive import
        return {k: _import_value(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_import_value(item) for item in value]
    else:
        return value


def import_file_from_json(
    input_path: str | Path,
    output_path: str | Path | None = None,
) -> UnityYAMLDocument:
    """Import a JSON file back to Unity YAML format.

    Args:
        input_path: Path to the JSON file
        output_path: Optional path to save the Unity YAML output

    Returns:
        UnityYAMLDocument object
    """
    input_path = Path(input_path)
    json_str = input_path.read_text(encoding="utf-8")
    prefab_json = PrefabJSON.from_json(json_str)
    doc = import_from_json(prefab_json)

    if output_path:
        doc.save(output_path)

    return doc


def get_summary(doc: UnityYAMLDocument) -> dict[str, Any]:
    """Get a summary of a Unity YAML document for context management.

    Useful for providing LLMs with an overview before sending full details.
    """
    # Count by type
    type_counts: dict[str, int] = {}
    for obj in doc.objects:
        type_counts[obj.class_name] = type_counts.get(obj.class_name, 0) + 1

    # Build hierarchy
    hierarchy: list[str] = []
    transforms: dict[int, dict[str, Any]] = {}

    # First pass: collect all transforms
    for obj in doc.objects:
        if obj.class_id == 4:  # Transform
            content = obj.get_content()
            if content:
                go_ref = content.get("m_GameObject", {})
                go_id = go_ref.get("fileID", 0) if isinstance(go_ref, dict) else 0
                father = content.get("m_Father", {})
                father_id = father.get("fileID", 0) if isinstance(father, dict) else 0
                transforms[obj.file_id] = {
                    "gameObject": go_id,
                    "parent": father_id,
                    "children": [],
                }

    # Second pass: find names
    go_names: dict[int, str] = {}
    for obj in doc.objects:
        if obj.class_id == 1:  # GameObject
            content = obj.get_content()
            if content:
                go_names[obj.file_id] = content.get("m_Name", "<unnamed>")

    # Build hierarchy strings
    def build_path(transform_id: int, visited: set[int]) -> str:
        if transform_id in visited or transform_id not in transforms:
            return ""
        visited.add(transform_id)

        t = transforms[transform_id]
        name = go_names.get(t["gameObject"], "<unnamed>")

        if t["parent"] == 0:
            return name
        else:
            parent_path = build_path(t["parent"], visited)
            if parent_path:
                return f"{parent_path}/{name}"
            return name

    # Find roots and build paths
    for tid, t in transforms.items():
        if t["parent"] == 0:
            path = build_path(tid, set())
            if path:
                hierarchy.append(path)

    return {
        "summary": {
            "totalGameObjects": type_counts.get("GameObject", 0),
            "totalComponents": len(doc.objects) - type_counts.get("GameObject", 0),
            "typeCounts": type_counts,
            "hierarchy": sorted(hierarchy),
        }
    }

"""LLM-friendly format conversion for Unity YAML files.

Provides JSON export/import for easier manipulation by LLMs and scripts,
with round-trip fidelity through _rawFields preservation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from unityflow.parser import CLASS_IDS, UnityYAMLDocument, UnityYAMLObject

# =============================================================================
# RectTransform Editor <-> File Format Conversion Utilities
# =============================================================================


@dataclass
class RectTransformEditorValues:
    """Values as shown in Unity Editor Inspector.

    For stretch mode (anchorMin != anchorMax):
        - left, right, top, bottom: offsets from anchor edges
    For anchored mode (anchorMin == anchorMax):
        - pos_x, pos_y: position relative to anchor
        - width, height: size of the rect
    """

    # Anchors (same for both modes)
    anchor_min_x: float = 0.5
    anchor_min_y: float = 0.5
    anchor_max_x: float = 0.5
    anchor_max_y: float = 0.5

    # Pivot
    pivot_x: float = 0.5
    pivot_y: float = 0.5

    # Position (Z is always stored directly)
    pos_z: float = 0

    # Stretch mode values (when anchorMin != anchorMax on that axis)
    left: float | None = None
    right: float | None = None
    top: float | None = None
    bottom: float | None = None

    # Anchored mode values (when anchorMin == anchorMax on that axis)
    pos_x: float | None = None
    pos_y: float | None = None
    width: float | None = None
    height: float | None = None

    @property
    def is_stretch_horizontal(self) -> bool:
        """Check if horizontal axis is in stretch mode."""
        return self.anchor_min_x != self.anchor_max_x

    @property
    def is_stretch_vertical(self) -> bool:
        """Check if vertical axis is in stretch mode."""
        return self.anchor_min_y != self.anchor_max_y


@dataclass
class RectTransformFileValues:
    """Values as stored in Unity YAML file."""

    anchor_min: dict[str, float]  # {x, y}
    anchor_max: dict[str, float]  # {x, y}
    anchored_position: dict[str, float]  # {x, y}
    size_delta: dict[str, float]  # {x, y}
    pivot: dict[str, float]  # {x, y}
    local_position_z: float = 0


def editor_to_file_values(editor: RectTransformEditorValues) -> RectTransformFileValues:
    """Convert Unity Editor values to file format values.

    This handles the complex conversion between what you see in the Inspector
    and what gets stored in the .prefab/.unity file.

    The conversion formulas:
    - For stretch mode (anchorMin != anchorMax):
        offsetMin = (left, bottom)
        offsetMax = (-right, -top)
        anchoredPosition = (offsetMin + offsetMax) / 2
        sizeDelta = offsetMax - offsetMin

    - For anchored mode (anchorMin == anchorMax):
        anchoredPosition = (pos_x, pos_y)
        sizeDelta = (width, height)
    """
    # Determine mode for each axis
    stretch_h = editor.is_stretch_horizontal
    stretch_v = editor.is_stretch_vertical

    # Calculate anchored position and size delta
    if stretch_h:
        # Horizontal stretch mode
        left = editor.left or 0
        right = editor.right or 0
        offset_min_x = left
        offset_max_x = -right
        anchored_x = (offset_min_x + offset_max_x) / 2
        size_delta_x = offset_max_x - offset_min_x
    else:
        # Horizontal anchored mode
        anchored_x = editor.pos_x or 0
        size_delta_x = editor.width or 100

    if stretch_v:
        # Vertical stretch mode
        bottom = editor.bottom or 0
        top = editor.top or 0
        offset_min_y = bottom
        offset_max_y = -top
        anchored_y = (offset_min_y + offset_max_y) / 2
        size_delta_y = offset_max_y - offset_min_y
    else:
        # Vertical anchored mode
        anchored_y = editor.pos_y or 0
        size_delta_y = editor.height or 100

    return RectTransformFileValues(
        anchor_min={"x": editor.anchor_min_x, "y": editor.anchor_min_y},
        anchor_max={"x": editor.anchor_max_x, "y": editor.anchor_max_y},
        anchored_position={"x": anchored_x, "y": anchored_y},
        size_delta={"x": size_delta_x, "y": size_delta_y},
        pivot={"x": editor.pivot_x, "y": editor.pivot_y},
        local_position_z=editor.pos_z,
    )


def file_to_editor_values(file_vals: RectTransformFileValues) -> RectTransformEditorValues:
    """Convert file format values to Unity Editor values.

    The conversion formulas:
    - offsetMin = anchoredPosition - sizeDelta * pivot
    - offsetMax = anchoredPosition + sizeDelta * (1 - pivot)

    For stretch mode:
        left = offsetMin.x
        right = -offsetMax.x
        bottom = offsetMin.y
        top = -offsetMax.y

    For anchored mode:
        pos_x = anchoredPosition.x
        pos_y = anchoredPosition.y
        width = sizeDelta.x
        height = sizeDelta.y
    """
    anchor_min_x = file_vals.anchor_min.get("x", 0.5)
    anchor_min_y = file_vals.anchor_min.get("y", 0.5)
    anchor_max_x = file_vals.anchor_max.get("x", 0.5)
    anchor_max_y = file_vals.anchor_max.get("y", 0.5)

    pivot_x = file_vals.pivot.get("x", 0.5)
    pivot_y = file_vals.pivot.get("y", 0.5)

    anchored_x = file_vals.anchored_position.get("x", 0)
    anchored_y = file_vals.anchored_position.get("y", 0)

    size_delta_x = file_vals.size_delta.get("x", 100)
    size_delta_y = file_vals.size_delta.get("y", 100)

    # Calculate offset values
    offset_min_x = anchored_x - size_delta_x * pivot_x
    offset_max_x = anchored_x + size_delta_x * (1 - pivot_x)
    offset_min_y = anchored_y - size_delta_y * pivot_y
    offset_max_y = anchored_y + size_delta_y * (1 - pivot_y)

    editor = RectTransformEditorValues(
        anchor_min_x=anchor_min_x,
        anchor_min_y=anchor_min_y,
        anchor_max_x=anchor_max_x,
        anchor_max_y=anchor_max_y,
        pivot_x=pivot_x,
        pivot_y=pivot_y,
        pos_z=file_vals.local_position_z,
    )

    # Determine mode and set appropriate values
    stretch_h = anchor_min_x != anchor_max_x
    stretch_v = anchor_min_y != anchor_max_y

    if stretch_h:
        editor.left = offset_min_x
        editor.right = -offset_max_x
    else:
        editor.pos_x = anchored_x
        editor.width = size_delta_x

    if stretch_v:
        editor.bottom = offset_min_y
        editor.top = -offset_max_y
    else:
        editor.pos_y = anchored_y
        editor.height = size_delta_y

    return editor


def create_rect_transform_file_values(
    anchor_preset: str = "center",
    pivot: tuple[float, float] = (0.5, 0.5),
    pos_x: float = 0,
    pos_y: float = 0,
    pos_z: float = 0,
    width: float = 100,
    height: float = 100,
    left: float = 0,
    right: float = 0,
    top: float = 0,
    bottom: float = 0,
) -> RectTransformFileValues:
    """Create RectTransform file values from common parameters.

    Args:
        anchor_preset: Preset name for anchor position:
            - "center": anchors at center (0.5, 0.5)
            - "top-left", "top-center", "top-right"
            - "middle-left", "middle-center", "middle-right"
            - "bottom-left", "bottom-center", "bottom-right"
            - "stretch-top", "stretch-middle", "stretch-bottom" (horizontal stretch)
            - "stretch-left", "stretch-center", "stretch-right" (vertical stretch)
            - "stretch-all": full stretch (0,0) to (1,1)
        pivot: Pivot point (x, y), default center
        pos_x, pos_y, pos_z: Position (for anchored mode)
        width, height: Size (for anchored mode)
        left, right, top, bottom: Offsets (for stretch mode)

    Returns:
        RectTransformFileValues ready for use
    """
    # Anchor presets mapping
    presets = {
        # Single point anchors
        "top-left": ((0, 1), (0, 1)),
        "top-center": ((0.5, 1), (0.5, 1)),
        "top-right": ((1, 1), (1, 1)),
        "middle-left": ((0, 0.5), (0, 0.5)),
        "center": ((0.5, 0.5), (0.5, 0.5)),
        "middle-center": ((0.5, 0.5), (0.5, 0.5)),
        "middle-right": ((1, 0.5), (1, 0.5)),
        "bottom-left": ((0, 0), (0, 0)),
        "bottom-center": ((0.5, 0), (0.5, 0)),
        "bottom-right": ((1, 0), (1, 0)),
        # Horizontal stretch
        "stretch-top": ((0, 1), (1, 1)),
        "stretch-middle": ((0, 0.5), (1, 0.5)),
        "stretch-bottom": ((0, 0), (1, 0)),
        # Vertical stretch
        "stretch-left": ((0, 0), (0, 1)),
        "stretch-center": ((0.5, 0), (0.5, 1)),
        "stretch-right": ((1, 0), (1, 1)),
        # Full stretch
        "stretch-all": ((0, 0), (1, 1)),
    }

    anchor_min, anchor_max = presets.get(anchor_preset, ((0.5, 0.5), (0.5, 0.5)))

    editor = RectTransformEditorValues(
        anchor_min_x=anchor_min[0],
        anchor_min_y=anchor_min[1],
        anchor_max_x=anchor_max[0],
        anchor_max_y=anchor_max[1],
        pivot_x=pivot[0],
        pivot_y=pivot[1],
        pos_z=pos_z,
    )

    # Set values based on stretch mode
    if editor.is_stretch_horizontal:
        editor.left = left
        editor.right = right
    else:
        editor.pos_x = pos_x
        editor.width = width

    if editor.is_stretch_vertical:
        editor.top = top
        editor.bottom = bottom
    else:
        editor.pos_y = pos_y
        editor.height = height

    return editor_to_file_values(editor)


# Reverse mapping: class name -> class ID
CLASS_NAME_TO_ID = {name: id for id, name in CLASS_IDS.items()}

# =============================================================================
# Layout-Driven Properties Detection
# =============================================================================

# Layout components that drive RectTransform properties on the SAME GameObject
# These components modify their own RectTransform's size
SELF_DRIVING_LAYOUT_GUIDS = {
    # ContentSizeFitter - drives width/height based on content
    "3245ec927659c4140ac4f8d17403cc18": "ContentSizeFitter",
    # AspectRatioFitter - drives width or height to maintain aspect ratio
    "306cc8c2b49d7114eaa3623786fc2126": "AspectRatioFitter",
}

# Layout components that drive RectTransform properties on CHILD GameObjects
# These components modify their children's RectTransform position/size
CHILD_DRIVING_LAYOUT_GUIDS = {
    # VerticalLayoutGroup - arranges children vertically
    "59f8146938fff824cb5fd77236b75775": "VerticalLayoutGroup",
    # HorizontalLayoutGroup - arranges children horizontally
    "30649d3a9faa99c48a7b1166b86bf2a0": "HorizontalLayoutGroup",
    # GridLayoutGroup - arranges children in a grid
    "8a8695521f0d02e499659fee002a26c2": "GridLayoutGroup",
}

# Combined for quick lookup
ALL_LAYOUT_GUIDS = {**SELF_DRIVING_LAYOUT_GUIDS, **CHILD_DRIVING_LAYOUT_GUIDS}

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
            "metadata": self.metadata,
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
        # Support both "metadata" and legacy "prefabMetadata" keys
        metadata = data.get("metadata") or data.get("prefabMetadata", {})
        return cls(
            metadata=metadata,
            game_objects=data.get("gameObjects", {}),
            components=data.get("components", {}),
            raw_fields=data.get("_rawFields", {}),
        )

    @classmethod
    def from_json(cls, json_str: str) -> PrefabJSON:
        """Create from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)


def _analyze_layout_driven_properties(doc: UnityYAMLDocument) -> dict[str, dict[str, Any]]:
    """Analyze which RectTransforms have layout-driven properties.

    Returns a dict mapping RectTransform fileID -> driven info:
    {
        "rectTransformFileId": {
            "drivenBy": "ContentSizeFitter",  # or other layout component
            "drivenProperties": ["width", "height"],  # which properties are driven
            "driverComponentId": "123456",  # fileID of the layout component
        }
    }
    """
    driven_info: dict[str, dict[str, Any]] = {}

    # Build lookup tables
    # gameObjectId -> list of component fileIDs
    go_components: dict[str, list[str]] = {}
    # componentId -> component object
    component_objs: dict[str, tuple[UnityYAMLObject, dict[str, Any]]] = {}
    # gameObjectId -> RectTransform fileID
    go_rect_transform: dict[str, str] = {}
    # RectTransform fileID -> parent RectTransform fileID
    rect_parent: dict[str, str] = {}

    # First pass: collect all objects
    for obj in doc.objects:
        content = obj.get_content()
        if content is None:
            continue

        file_id = str(obj.file_id)

        if obj.class_id == 1:  # GameObject
            components = content.get("m_Component", [])
            go_components[file_id] = [
                str(c.get("component", {}).get("fileID", 0))
                for c in components
                if isinstance(c, dict) and "component" in c
            ]
        elif obj.class_id == 224:  # RectTransform
            component_objs[file_id] = (obj, content)
            # Map GameObject -> RectTransform
            go_ref = content.get("m_GameObject", {})
            if isinstance(go_ref, dict) and "fileID" in go_ref:
                go_rect_transform[str(go_ref["fileID"])] = file_id
            # Track parent
            father = content.get("m_Father", {})
            if isinstance(father, dict) and father.get("fileID", 0) != 0:
                rect_parent[file_id] = str(father["fileID"])
        elif obj.class_id == 114:  # MonoBehaviour
            component_objs[file_id] = (obj, content)

    # Second pass: find layout components and mark driven RectTransforms
    for obj in doc.objects:
        content = obj.get_content()
        if content is None or obj.class_id != 114:
            continue

        file_id = str(obj.file_id)
        script = content.get("m_Script", {})
        if not isinstance(script, dict):
            continue

        guid = script.get("guid", "")

        # Check if this is a self-driving layout component (ContentSizeFitter, AspectRatioFitter)
        if guid in SELF_DRIVING_LAYOUT_GUIDS:
            component_name = SELF_DRIVING_LAYOUT_GUIDS[guid]
            go_ref = content.get("m_GameObject", {})
            if isinstance(go_ref, dict) and "fileID" in go_ref:
                go_id = str(go_ref["fileID"])
                rect_id = go_rect_transform.get(go_id)
                if rect_id:
                    driven_props = _get_driven_properties_for_component(component_name, content)
                    if driven_props:
                        driven_info[rect_id] = {
                            "drivenBy": component_name,
                            "drivenProperties": driven_props,
                            "driverComponentId": file_id,
                        }

        # Check if this is a child-driving layout component (LayoutGroups)
        elif guid in CHILD_DRIVING_LAYOUT_GUIDS:
            component_name = CHILD_DRIVING_LAYOUT_GUIDS[guid]
            go_ref = content.get("m_GameObject", {})
            if isinstance(go_ref, dict) and "fileID" in go_ref:
                go_id = str(go_ref["fileID"])
                parent_rect_id = go_rect_transform.get(go_id)
                if parent_rect_id:
                    # Find all children of this RectTransform
                    for child_rect_id, parent_id in rect_parent.items():
                        if parent_id == parent_rect_id:
                            driven_props = _get_driven_properties_for_layout_child(component_name, content)
                            if driven_props:
                                # Merge with existing driven info (a child could have both
                                # ContentSizeFitter and be in a LayoutGroup)
                                if child_rect_id in driven_info:
                                    existing = driven_info[child_rect_id]
                                    existing["drivenProperties"] = list(
                                        set(existing["drivenProperties"] + driven_props)
                                    )
                                    existing["drivenBy"] = f"{existing['drivenBy']}, {component_name}"
                                else:
                                    driven_info[child_rect_id] = {
                                        "drivenBy": component_name,
                                        "drivenProperties": driven_props,
                                        "driverComponentId": file_id,
                                    }

    return driven_info


def _get_driven_properties_for_component(component_name: str, content: dict[str, Any]) -> list[str]:
    """Get which properties are driven by a self-driving layout component."""
    driven = []

    if component_name == "ContentSizeFitter":
        # m_HorizontalFit: 0=Unconstrained, 1=MinSize, 2=PreferredSize
        h_fit = content.get("m_HorizontalFit", 0)
        v_fit = content.get("m_VerticalFit", 0)
        if h_fit != 0:
            driven.append("width")
        if v_fit != 0:
            driven.append("height")

    elif component_name == "AspectRatioFitter":
        # m_AspectMode: 0=None, 1=WidthControlsHeight, 2=HeightControlsWidth,
        #               3=FitInParent, 4=EnvelopeParent
        mode = content.get("m_AspectMode", 0)
        if mode == 1:
            driven.append("height")
        elif mode == 2:
            driven.append("width")
        elif mode in (3, 4):
            driven.extend(["width", "height"])

    return driven


def _get_driven_properties_for_layout_child(component_name: str, content: dict[str, Any]) -> list[str]:
    """Get which properties are driven on children by a layout group."""
    driven = []

    if component_name in ("HorizontalLayoutGroup", "VerticalLayoutGroup"):
        # Check childControlWidth/Height and childForceExpandWidth/Height
        if content.get("m_ChildControlWidth", False):
            driven.append("width")
        if content.get("m_ChildControlHeight", False):
            driven.append("height")
        # Position is always driven in layout groups
        driven.extend(["posX", "posY"])

    elif component_name == "GridLayoutGroup":
        # Grid always controls both size and position
        driven.extend(["width", "height", "posX", "posY"])

    return driven


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

    # Analyze layout-driven properties
    driven_info = _analyze_layout_driven_properties(doc)

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
            # Pass driven info for RectTransforms
            rect_driven = driven_info.get(file_id) if obj.class_id == 224 else None
            result.components[file_id] = _export_component(obj, content, rect_driven)
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
            str(c.get("component", {}).get("fileID", 0)) for c in components if isinstance(c, dict) and "component" in c
        ]

    return result


def _export_component(
    obj: UnityYAMLObject,
    content: dict[str, Any],
    driven_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Export a component to JSON format.

    Args:
        obj: The Unity YAML object
        content: The object's content dict
        driven_info: Optional layout-driven property info for RectTransforms
    """
    result: dict[str, Any] = {
        "type": obj.class_name,
        "classId": obj.class_id,
    }

    # Preserve original root key for unknown types (important for round-trip fidelity)
    original_root_key = obj.root_key
    if original_root_key and original_root_key != obj.class_name:
        result["_originalType"] = original_root_key

    # GameObject reference
    go_ref = content.get("m_GameObject", {})
    if isinstance(go_ref, dict) and "fileID" in go_ref:
        result["gameObject"] = str(go_ref["fileID"])

    # Type-specific export
    if obj.class_id == 4:  # Transform
        result.update(_export_transform(content))
    elif obj.class_id == 224:  # RectTransform
        result.update(_export_rect_transform(content, driven_info))
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
            str(c.get("fileID", 0)) for c in children if isinstance(c, dict) and c.get("fileID", 0) != 0
        ]

    return result


def _export_rect_transform(
    content: dict[str, Any],
    driven_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Export RectTransform-specific fields.

    Exports values as shown in Unity Inspector (editor values) for intuitive
    manipulation by LLMs. Each Unity field maps to exactly one JSON field.

    Layout-driven properties are replaced with "<driven>" placeholder to:
    1. Prevent LLMs from modifying values that will be overwritten at runtime
    2. Ensure consistent output regardless of what Unity saved (no spurious diffs)

    Args:
        content: The RectTransform content dict
        driven_info: Optional layout-driven property info containing:
            - drivenBy: Name of the layout component driving properties
            - drivenProperties: List of properties being driven (e.g., ["width", "height"])
            - driverComponentId: fileID of the layout component
    """
    # Start with Transform fields
    result = _export_transform(content)

    # Determine which properties are driven
    driven_props = set(driven_info["drivenProperties"]) if driven_info else set()

    # Extract RectTransform-specific fields
    anchor_min = content.get("m_AnchorMin", {"x": 0.5, "y": 0.5})
    anchor_max = content.get("m_AnchorMax", {"x": 0.5, "y": 0.5})
    anchored_position = content.get("m_AnchoredPosition", {"x": 0, "y": 0})
    size_delta = content.get("m_SizeDelta", {"x": 100, "y": 100})
    pivot = content.get("m_Pivot", {"x": 0.5, "y": 0.5})
    local_position = content.get("m_LocalPosition", {"x": 0, "y": 0, "z": 0})

    # Convert to editor values (what you see in Unity Inspector)
    file_vals = RectTransformFileValues(
        anchor_min=anchor_min,
        anchor_max=anchor_max,
        anchored_position=anchored_position,
        size_delta=size_delta,
        pivot=pivot,
        local_position_z=float(local_position.get("z", 0)),
    )
    editor_vals = file_to_editor_values(file_vals)

    # Export as single "rectTransform" field with Inspector-style values
    # Driven properties show "<driven>" placeholder instead of actual values
    rt = result["rectTransform"] = {
        "anchorMin": {"x": editor_vals.anchor_min_x, "y": editor_vals.anchor_min_y},
        "anchorMax": {"x": editor_vals.anchor_max_x, "y": editor_vals.anchor_max_y},
        "pivot": {"x": editor_vals.pivot_x, "y": editor_vals.pivot_y},
        "posZ": editor_vals.pos_z,
    }

    # Add mode-specific values, replacing driven properties with placeholder
    if editor_vals.is_stretch_horizontal:
        rt["left"] = "<driven>" if "posX" in driven_props else editor_vals.left
        rt["right"] = "<driven>" if "posX" in driven_props else editor_vals.right
    else:
        rt["posX"] = "<driven>" if "posX" in driven_props else editor_vals.pos_x
        rt["width"] = "<driven>" if "width" in driven_props else editor_vals.width

    if editor_vals.is_stretch_vertical:
        rt["top"] = "<driven>" if "posY" in driven_props else editor_vals.top
        rt["bottom"] = "<driven>" if "posY" in driven_props else editor_vals.bottom
    else:
        rt["posY"] = "<driven>" if "posY" in driven_props else editor_vals.pos_y
        rt["height"] = "<driven>" if "height" in driven_props else editor_vals.height

    # Add layout-driven metadata if present (for reference only)
    if driven_info:
        result["_layoutDriven"] = {
            "drivenBy": driven_info["drivenBy"],
            "drivenProperties": driven_info["drivenProperties"],
            "driverComponentId": driven_info["driverComponentId"],
        }

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
    skip_keys = {
        "m_ObjectHideFlags",
        "m_CorrespondingSourceObject",
        "m_PrefabInstance",
        "m_PrefabAsset",
        "m_GameObject",
        "m_Enabled",
        "m_Script",
        "m_EditorHideFlags",
        "m_EditorClassIdentifier",
    }

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

    skip_keys = {
        "m_ObjectHideFlags",
        "m_CorrespondingSourceObject",
        "m_PrefabInstance",
        "m_PrefabAsset",
        "m_GameObject",
    }

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
    elif class_id == 224:  # RectTransform
        return {
            "m_LocalPosition",
            "m_LocalRotation",
            "m_LocalScale",
            "m_Children",
            "m_Father",
            "m_GameObject",
            "m_AnchorMin",
            "m_AnchorMax",
            "m_AnchoredPosition",
            "m_SizeDelta",
            "m_Pivot",
        }
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


def import_from_json(
    prefab_json: PrefabJSON,
    auto_fix: bool = True,
) -> UnityYAMLDocument:
    """Import a PrefabJSON back to UnityYAMLDocument.

    This enables round-trip conversion: YAML -> JSON -> YAML
    LLMs can modify the JSON and this function converts it back to Unity YAML.

    Args:
        prefab_json: The PrefabJSON object to convert
        auto_fix: If True, automatically fix common issues like invalid GUIDs
                  and missing SceneRoots entries (default: True)

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

    # Apply automatic fixes if requested
    if auto_fix:
        from unityflow.validator import fix_document

        fix_document(doc)

    return doc


def _import_game_object(file_id: int, data: dict[str, Any], raw_fields: dict[str, Any]) -> UnityYAMLObject:
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
        content["m_Component"] = [{"component": {"fileID": int(c)}} for c in components]
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


def _import_component(file_id: int, data: dict[str, Any], raw_fields: dict[str, Any]) -> UnityYAMLObject:
    """Import a component from JSON format."""
    class_id = data.get("classId", 0)
    comp_type = data.get("type", "")

    # Determine class_id if not provided
    if class_id == 0 and comp_type:
        class_id = CLASS_NAME_TO_ID.get(comp_type, 0)

    # Get the root key (class name)
    # Priority: _originalType > CLASS_IDS > comp_type > fallback
    original_type = data.get("_originalType")
    if original_type:
        root_key = original_type
    elif class_id in CLASS_IDS:
        root_key = CLASS_IDS[class_id]
    elif comp_type and not comp_type.startswith("Unknown"):
        root_key = comp_type
    else:
        root_key = comp_type or f"Unknown{class_id}"

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


def _import_transform(data: dict[str, Any], raw_fields: dict[str, Any]) -> dict[str, Any]:
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


def _import_rect_transform(data: dict[str, Any], raw_fields: dict[str, Any]) -> dict[str, Any]:
    """Import RectTransform-specific fields (extends Transform).

    Supports two ways to specify RectTransform values:
    1. From rectTransform (Inspector-style values - posX/posY, width/height, etc.)
    2. From raw_fields (fallback for round-trip)

    Layout-driven properties (marked as "<driven>" or listed in _layoutDriven)
    are normalized to 0, as they will be recalculated by Unity at runtime.
    """
    # Start with Transform fields
    content = _import_transform(data, raw_fields)

    # Get driven properties if present
    driven_props = set()
    if "_layoutDriven" in data:
        driven_props = set(data["_layoutDriven"].get("drivenProperties", []))

    # Priority 1: Import from rectTransform (Inspector-style values)
    if "rectTransform" in data:
        rt = data["rectTransform"]

        # Helper to get value, treating "<driven>" as None (will use default 0)
        def get_val(key: str, default: float | None = None) -> float | None:
            val = rt.get(key)
            if val == "<driven>":
                return None  # Will be handled as driven
            return val if val is not None else default

        # Build editor values object
        # Driven properties get None, which will result in 0 after conversion
        editor_vals = RectTransformEditorValues(
            anchor_min_x=rt.get("anchorMin", {}).get("x", 0.5),
            anchor_min_y=rt.get("anchorMin", {}).get("y", 0.5),
            anchor_max_x=rt.get("anchorMax", {}).get("x", 0.5),
            anchor_max_y=rt.get("anchorMax", {}).get("y", 0.5),
            pivot_x=rt.get("pivot", {}).get("x", 0.5),
            pivot_y=rt.get("pivot", {}).get("y", 0.5),
            pos_z=rt.get("posZ", 0),
            left=get_val("left"),
            right=get_val("right"),
            top=get_val("top"),
            bottom=get_val("bottom"),
            pos_x=get_val("posX"),
            pos_y=get_val("posY"),
            width=get_val("width"),
            height=get_val("height"),
        )

        # Convert to file values
        file_vals = editor_to_file_values(editor_vals)

        content["m_AnchorMin"] = file_vals.anchor_min
        content["m_AnchorMax"] = file_vals.anchor_max
        content["m_AnchoredPosition"] = file_vals.anchored_position
        content["m_SizeDelta"] = file_vals.size_delta
        content["m_Pivot"] = file_vals.pivot
        content["m_LocalPosition"]["z"] = file_vals.local_position_z

        # Normalize driven properties to 0
        if "posX" in driven_props or "posY" in driven_props:
            pos = content["m_AnchoredPosition"]
            if "posX" in driven_props:
                pos["x"] = 0
            if "posY" in driven_props:
                pos["y"] = 0
        if "width" in driven_props or "height" in driven_props:
            size = content["m_SizeDelta"]
            if "width" in driven_props:
                size["x"] = 0
            if "height" in driven_props:
                size["y"] = 0

    # Priority 2: Fallback to raw_fields
    else:
        rect_fields = [
            ("m_AnchorMin", {"x": 0.5, "y": 0.5}),
            ("m_AnchorMax", {"x": 0.5, "y": 0.5}),
            ("m_AnchoredPosition", {"x": 0, "y": 0}),
            ("m_SizeDelta", {"x": 100, "y": 100}),
            ("m_Pivot", {"x": 0.5, "y": 0.5}),
        ]

        for field, default in rect_fields:
            if field in raw_fields:
                content[field] = raw_fields[field]
            elif field not in content:
                content[field] = default

    return content


def _import_monobehaviour(data: dict[str, Any], raw_fields: dict[str, Any]) -> dict[str, Any]:
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


def _import_prefab_instance(data: dict[str, Any], raw_fields: dict[str, Any]) -> dict[str, Any]:
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
            mods_list.append(
                {
                    "target": {
                        "fileID": target.get("fileID", 0),
                        "guid": target.get("guid", ""),
                    },
                    "propertyPath": mod.get("propertyPath", ""),
                    "value": mod.get("value"),
                    "objectReference": mod.get("objectReference", {"fileID": 0}),
                }
            )
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


def _import_generic_component(data: dict[str, Any], raw_fields: dict[str, Any]) -> dict[str, Any]:
    """Import a generic component's fields.

    For unknown/generic components, prioritize raw_fields to preserve
    the original data structure. Only add default Unity fields if they
    existed in the original data.
    """
    content: dict[str, Any] = {}

    # First, restore all raw fields (preserves original structure)
    for key, value in raw_fields.items():
        content[key] = value

    # Only add default Unity fields if they existed in raw_fields
    # (Don't inject new fields that weren't in the original)
    if "m_ObjectHideFlags" not in content and "m_ObjectHideFlags" not in raw_fields:
        # Only add if data suggests it's needed
        pass  # Don't add default

    # GameObject reference - only if provided in data and not already in content
    if "gameObject" in data and "m_GameObject" not in content:
        content["m_GameObject"] = {"fileID": int(data["gameObject"])}

    # Convert exported fields back to Unity format
    # Skip metadata keys and keys already handled
    skip_keys = {"type", "classId", "gameObject", "_originalType"}

    for key, value in data.items():
        if key in skip_keys:
            continue

        # Convert camelCase back to m_PascalCase
        if key[0].islower() and not key.startswith("m_"):
            unity_key = "m_" + key[0].upper() + key[1:]
        else:
            unity_key = key

        # Skip if the original key (without m_ prefix) already exists in content
        # This prevents duplicates like serializedVersion and m_SerializedVersion
        if key in content:
            continue

        # Only update if not already set from raw_fields
        if unity_key not in content:
            content[unity_key] = _import_value(value)

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
    auto_fix: bool = True,
) -> UnityYAMLDocument:
    """Import a JSON file back to Unity YAML format.

    Args:
        input_path: Path to the JSON file
        output_path: Optional path to save the Unity YAML output
        auto_fix: If True, automatically fix common issues like invalid GUIDs
                  and missing SceneRoots entries (default: True)

    Returns:
        UnityYAMLDocument object
    """
    input_path = Path(input_path)
    json_str = input_path.read_text(encoding="utf-8")
    prefab_json = PrefabJSON.from_json(json_str)
    doc = import_from_json(prefab_json, auto_fix=auto_fix)

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

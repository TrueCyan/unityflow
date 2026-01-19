"""Data models for Unity AnimationClip (.anim) files.

These models represent the structured data within Unity animation files,
enabling programmatic access and modification of animation data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class WrapMode(IntEnum):
    """Animation wrap mode values."""

    DEFAULT = 0
    ONCE = 1
    LOOP = 2
    PING_PONG = 4
    CLAMP_FOREVER = 8


class TangentMode(IntEnum):
    """Common tangent mode values for keyframes."""

    FREE = 0
    AUTO_DEPRECATED = 1
    AUTO = 21
    CONSTANT = 103
    FLAT = 136


class CurveType(IntEnum):
    """Curve type identifiers for internal use."""

    POSITION = 1
    ROTATION = 2  # Quaternion rotation (rare)
    EULER = 3  # Euler angle rotation
    SCALE = 4
    FLOAT = 5
    PPTR = 6  # Object reference


# Common Unity classIDs for animation curves
CURVE_CLASS_IDS = {
    1: "GameObject",
    4: "Transform",
    23: "MeshRenderer",
    25: "Renderer",
    82: "AudioSource",
    95: "Animator",
    114: "MonoBehaviour",
    212: "SpriteRenderer",
}


@dataclass
class Vector3Value:
    """Represents a Vector3 value used in position/rotation/scale curves."""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Vector3Value:
        """Create from Unity YAML dict format."""
        if data is None:
            return cls()
        return cls(
            x=float(data.get("x", 0)),
            y=float(data.get("y", 0)),
            z=float(data.get("z", 0)),
        )

    def to_dict(self) -> dict[str, float]:
        """Convert to Unity YAML dict format."""
        return {"x": self.x, "y": self.y, "z": self.z}

    def __repr__(self) -> str:
        return f"({self.x}, {self.y}, {self.z})"


@dataclass
class Keyframe:
    """Represents a single keyframe in an animation curve.

    This is used for position, rotation, scale, and float curves.
    For PPtrCurves (object references), use PPtrKeyframe instead.
    """

    time: float = 0.0
    value: float | Vector3Value = 0.0
    in_slope: float | Vector3Value = 0.0
    out_slope: float | Vector3Value = 0.0
    tangent_mode: int = 0
    weighted_mode: int = 0
    in_weight: float | Vector3Value = 0.333333
    out_weight: float | Vector3Value = 0.333333

    @classmethod
    def from_dict(cls, data: dict[str, Any], is_vector: bool = False) -> Keyframe:
        """Create from Unity YAML keyframe dict.

        Args:
            data: The keyframe dictionary from YAML
            is_vector: If True, treat value/slope/weight as Vector3
        """
        if is_vector:
            return cls(
                time=float(data.get("time", 0)),
                value=Vector3Value.from_dict(data.get("value")),
                in_slope=Vector3Value.from_dict(data.get("inSlope")),
                out_slope=Vector3Value.from_dict(data.get("outSlope")),
                tangent_mode=int(data.get("tangentMode", 0)),
                weighted_mode=int(data.get("weightedMode", 0)),
                in_weight=Vector3Value.from_dict(data.get("inWeight")),
                out_weight=Vector3Value.from_dict(data.get("outWeight")),
            )
        else:
            return cls(
                time=float(data.get("time", 0)),
                value=float(data.get("value", 0)),
                in_slope=float(data.get("inSlope", 0)),
                out_slope=float(data.get("outSlope", 0)),
                tangent_mode=int(data.get("tangentMode", 0)),
                weighted_mode=int(data.get("weightedMode", 0)),
                in_weight=float(data.get("inWeight", 0.333333)),
                out_weight=float(data.get("outWeight", 0.333333)),
            )

    def to_dict(self, is_vector: bool = False) -> dict[str, Any]:
        """Convert to Unity YAML keyframe dict format."""
        result: dict[str, Any] = {
            "serializedVersion": 3,
            "time": self.time,
        }

        if is_vector and isinstance(self.value, Vector3Value):
            result["value"] = self.value.to_dict()
            result["inSlope"] = (
                self.in_slope.to_dict() if isinstance(self.in_slope, Vector3Value) else {"x": 0, "y": 0, "z": 0}
            )
            result["outSlope"] = (
                self.out_slope.to_dict() if isinstance(self.out_slope, Vector3Value) else {"x": 0, "y": 0, "z": 0}
            )
            result["inWeight"] = (
                self.in_weight.to_dict()
                if isinstance(self.in_weight, Vector3Value)
                else {"x": 0.333333, "y": 0.333333, "z": 0.333333}
            )
            result["outWeight"] = (
                self.out_weight.to_dict()
                if isinstance(self.out_weight, Vector3Value)
                else {"x": 0.333333, "y": 0.333333, "z": 0.333333}
            )
        else:
            result["value"] = self.value if isinstance(self.value, int | float) else 0.0
            result["inSlope"] = self.in_slope if isinstance(self.in_slope, int | float) else 0.0
            result["outSlope"] = self.out_slope if isinstance(self.out_slope, int | float) else 0.0
            result["inWeight"] = self.in_weight if isinstance(self.in_weight, int | float) else 0.333333
            result["outWeight"] = self.out_weight if isinstance(self.out_weight, int | float) else 0.333333

        result["tangentMode"] = self.tangent_mode
        result["weightedMode"] = self.weighted_mode

        return result

    def get_tangent_mode_name(self) -> str:
        """Get human-readable tangent mode name."""
        mode_names = {
            0: "free",
            1: "auto_deprecated",
            21: "auto",
            103: "constant",
            136: "flat",
        }
        return mode_names.get(self.tangent_mode, f"custom({self.tangent_mode})")


@dataclass
class PPtrKeyframe:
    """Represents a keyframe for object reference (PPtrCurve) animations.

    Used for sprite swaps, material changes, and other object reference animations.
    """

    time: float = 0.0
    file_id: int = 0
    guid: str = ""
    type: int = 0  # Usually 3 for external assets

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PPtrKeyframe:
        """Create from Unity YAML PPtrKeyframe dict."""
        value = data.get("value", {})
        if isinstance(value, dict):
            return cls(
                time=float(data.get("time", 0)),
                file_id=int(value.get("fileID", 0)),
                guid=str(value.get("guid", "")),
                type=int(value.get("type", 0)),
            )
        return cls(time=float(data.get("time", 0)))

    def to_dict(self) -> dict[str, Any]:
        """Convert to Unity YAML PPtrKeyframe dict format."""
        result: dict[str, Any] = {
            "time": self.time,
            "value": {"fileID": self.file_id},
        }
        if self.guid:
            result["value"]["guid"] = self.guid
            result["value"]["type"] = self.type
        return result


@dataclass
class AnimationCurve:
    """Represents an animation curve within an AnimationClip.

    Different curve types store their keyframes differently:
    - Position/Rotation/Scale curves: Vector3 keyframes
    - Float curves: Scalar keyframes
    - PPtrCurves: Object reference keyframes
    """

    path: str = ""  # Target GameObject path (empty = root)
    attribute: str = ""  # Property path (e.g., "m_Color.a", "m_Sprite")
    class_id: int = 0  # Unity classID (e.g., 212 for SpriteRenderer)
    curve_type: str = "float"  # position, rotation, euler, scale, float, pptr
    keyframes: list[Keyframe] = field(default_factory=list)
    pptr_keyframes: list[PPtrKeyframe] = field(default_factory=list)
    pre_infinity: int = 2  # 2=Constant
    post_infinity: int = 2
    rotation_order: int = 4  # 4=ZXY (Unity default)
    script_guid: str = ""  # For MonoBehaviour curves

    @property
    def key_count(self) -> int:
        """Get the number of keyframes."""
        if self.curve_type == "pptr":
            return len(self.pptr_keyframes)
        return len(self.keyframes)

    @property
    def is_vector_curve(self) -> bool:
        """Check if this curve uses Vector3 values."""
        return self.curve_type in ("position", "rotation", "euler", "scale")

    @property
    def class_name(self) -> str:
        """Get human-readable class name."""
        return CURVE_CLASS_IDS.get(self.class_id, f"Unknown({self.class_id})")

    def get_duration(self) -> float:
        """Get the duration of this curve (last keyframe time)."""
        if self.curve_type == "pptr":
            if not self.pptr_keyframes:
                return 0.0
            return max(k.time for k in self.pptr_keyframes)
        if not self.keyframes:
            return 0.0
        return max(k.time for k in self.keyframes)

    @classmethod
    def from_position_curve(cls, data: dict[str, Any]) -> AnimationCurve:
        """Create from m_PositionCurves entry."""
        curve_data = data.get("curve", {})
        m_curve = curve_data.get("m_Curve", [])

        keyframes = [Keyframe.from_dict(k, is_vector=True) for k in m_curve]

        return cls(
            path=data.get("path", ""),
            attribute="localPosition",
            class_id=4,  # Transform
            curve_type="position",
            keyframes=keyframes,
            pre_infinity=curve_data.get("m_PreInfinity", 2),
            post_infinity=curve_data.get("m_PostInfinity", 2),
            rotation_order=curve_data.get("m_RotationOrder", 4),
        )

    @classmethod
    def from_euler_curve(cls, data: dict[str, Any]) -> AnimationCurve:
        """Create from m_EulerCurves entry."""
        curve_data = data.get("curve", {})
        m_curve = curve_data.get("m_Curve", [])

        keyframes = [Keyframe.from_dict(k, is_vector=True) for k in m_curve]

        return cls(
            path=data.get("path", ""),
            attribute="localEulerAngles",
            class_id=4,  # Transform
            curve_type="euler",
            keyframes=keyframes,
            pre_infinity=curve_data.get("m_PreInfinity", 2),
            post_infinity=curve_data.get("m_PostInfinity", 2),
            rotation_order=curve_data.get("m_RotationOrder", 4),
        )

    @classmethod
    def from_scale_curve(cls, data: dict[str, Any]) -> AnimationCurve:
        """Create from m_ScaleCurves entry."""
        curve_data = data.get("curve", {})
        m_curve = curve_data.get("m_Curve", [])

        keyframes = [Keyframe.from_dict(k, is_vector=True) for k in m_curve]

        return cls(
            path=data.get("path", ""),
            attribute="localScale",
            class_id=4,  # Transform
            curve_type="scale",
            keyframes=keyframes,
            pre_infinity=curve_data.get("m_PreInfinity", 2),
            post_infinity=curve_data.get("m_PostInfinity", 2),
            rotation_order=curve_data.get("m_RotationOrder", 4),
        )

    @classmethod
    def from_float_curve(cls, data: dict[str, Any]) -> AnimationCurve:
        """Create from m_FloatCurves entry."""
        curve_data = data.get("curve", {})
        m_curve = curve_data.get("m_Curve", [])

        keyframes = [Keyframe.from_dict(k, is_vector=False) for k in m_curve]

        script_ref = data.get("script", {})
        script_guid = ""
        if isinstance(script_ref, dict):
            script_guid = script_ref.get("guid", "")

        return cls(
            path=data.get("path", ""),
            attribute=data.get("attribute", ""),
            class_id=data.get("classID", 0),
            curve_type="float",
            keyframes=keyframes,
            pre_infinity=curve_data.get("m_PreInfinity", 2),
            post_infinity=curve_data.get("m_PostInfinity", 2),
            rotation_order=curve_data.get("m_RotationOrder", 4),
            script_guid=script_guid,
        )

    @classmethod
    def from_pptr_curve(cls, data: dict[str, Any]) -> AnimationCurve:
        """Create from m_PPtrCurves entry."""
        curve_list = data.get("curve", [])

        pptr_keyframes = [PPtrKeyframe.from_dict(k) for k in curve_list]

        script_ref = data.get("script", {})
        script_guid = ""
        if isinstance(script_ref, dict):
            script_guid = script_ref.get("guid", "")

        return cls(
            path=data.get("path", ""),
            attribute=data.get("attribute", ""),
            class_id=data.get("classID", 0),
            curve_type="pptr",
            pptr_keyframes=pptr_keyframes,
            script_guid=script_guid,
        )

    def to_position_curve_dict(self) -> dict[str, Any]:
        """Convert to m_PositionCurves entry format."""
        return {
            "curve": {
                "serializedVersion": 2,
                "m_Curve": [k.to_dict(is_vector=True) for k in self.keyframes],
                "m_PreInfinity": self.pre_infinity,
                "m_PostInfinity": self.post_infinity,
                "m_RotationOrder": self.rotation_order,
            },
            "path": self.path,
        }

    def to_euler_curve_dict(self) -> dict[str, Any]:
        """Convert to m_EulerCurves entry format."""
        return {
            "curve": {
                "serializedVersion": 2,
                "m_Curve": [k.to_dict(is_vector=True) for k in self.keyframes],
                "m_PreInfinity": self.pre_infinity,
                "m_PostInfinity": self.post_infinity,
                "m_RotationOrder": self.rotation_order,
            },
            "path": self.path,
        }

    def to_scale_curve_dict(self) -> dict[str, Any]:
        """Convert to m_ScaleCurves entry format."""
        return {
            "curve": {
                "serializedVersion": 2,
                "m_Curve": [k.to_dict(is_vector=True) for k in self.keyframes],
                "m_PreInfinity": self.pre_infinity,
                "m_PostInfinity": self.post_infinity,
                "m_RotationOrder": self.rotation_order,
            },
            "path": self.path,
        }

    def to_float_curve_dict(self) -> dict[str, Any]:
        """Convert to m_FloatCurves entry format."""
        result: dict[str, Any] = {
            "curve": {
                "serializedVersion": 2,
                "m_Curve": [k.to_dict(is_vector=False) for k in self.keyframes],
                "m_PreInfinity": self.pre_infinity,
                "m_PostInfinity": self.post_infinity,
                "m_RotationOrder": self.rotation_order,
            },
            "attribute": self.attribute,
            "path": self.path,
            "classID": self.class_id,
            "script": {"fileID": 0},
        }
        if self.script_guid:
            result["script"] = {"fileID": 11500000, "guid": self.script_guid, "type": 3}
        return result

    def to_pptr_curve_dict(self) -> dict[str, Any]:
        """Convert to m_PPtrCurves entry format."""
        result: dict[str, Any] = {
            "curve": [k.to_dict() for k in self.pptr_keyframes],
            "attribute": self.attribute,
            "path": self.path,
            "classID": self.class_id,
            "script": {"fileID": 0},
        }
        if self.script_guid:
            result["script"] = {"fileID": 11500000, "guid": self.script_guid, "type": 3}
        return result


@dataclass
class AnimationEvent:
    """Represents an animation event that triggers at a specific time."""

    time: float = 0.0
    function_name: str = ""
    data: str = ""
    object_reference: dict[str, Any] = field(default_factory=lambda: {"fileID": 0})
    float_parameter: float = 0.0
    int_parameter: int = 0
    message_options: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnimationEvent:
        """Create from Unity YAML event dict."""
        return cls(
            time=float(data.get("time", 0)),
            function_name=data.get("functionName", ""),
            data=data.get("data", ""),
            object_reference=data.get("objectReferenceParameter", {"fileID": 0}),
            float_parameter=float(data.get("floatParameter", 0)),
            int_parameter=int(data.get("intParameter", 0)),
            message_options=int(data.get("messageOptions", 0)),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to Unity YAML event dict format."""
        return {
            "time": self.time,
            "functionName": self.function_name,
            "data": self.data,
            "objectReferenceParameter": self.object_reference,
            "floatParameter": self.float_parameter,
            "intParameter": self.int_parameter,
            "messageOptions": self.message_options,
        }


@dataclass
class AnimationClipSettings:
    """Animation clip settings (m_AnimationClipSettings)."""

    start_time: float = 0.0
    stop_time: float = 1.0
    orientation_offset_y: float = 0.0
    level: float = 0.0
    cycle_offset: float = 0.0
    has_additive_reference_pose: bool = False
    loop_time: bool = False
    loop_blend: bool = False
    loop_blend_orientation: bool = False
    loop_blend_position_y: bool = False
    loop_blend_position_xz: bool = False
    keep_original_orientation: bool = False
    keep_original_position_y: bool = True
    keep_original_position_xz: bool = False
    height_from_feet: bool = False
    mirror: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnimationClipSettings:
        """Create from m_AnimationClipSettings dict."""
        return cls(
            start_time=float(data.get("m_StartTime", 0)),
            stop_time=float(data.get("m_StopTime", 1)),
            orientation_offset_y=float(data.get("m_OrientationOffsetY", 0)),
            level=float(data.get("m_Level", 0)),
            cycle_offset=float(data.get("m_CycleOffset", 0)),
            has_additive_reference_pose=bool(data.get("m_HasAdditiveReferencePose", 0)),
            loop_time=bool(data.get("m_LoopTime", 0)),
            loop_blend=bool(data.get("m_LoopBlend", 0)),
            loop_blend_orientation=bool(data.get("m_LoopBlendOrientation", 0)),
            loop_blend_position_y=bool(data.get("m_LoopBlendPositionY", 0)),
            loop_blend_position_xz=bool(data.get("m_LoopBlendPositionXZ", 0)),
            keep_original_orientation=bool(data.get("m_KeepOriginalOrientation", 0)),
            keep_original_position_y=bool(data.get("m_KeepOriginalPositionY", 1)),
            keep_original_position_xz=bool(data.get("m_KeepOriginalPositionXZ", 0)),
            height_from_feet=bool(data.get("m_HeightFromFeet", 0)),
            mirror=bool(data.get("m_Mirror", 0)),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to m_AnimationClipSettings dict format."""
        return {
            "serializedVersion": 2,
            "m_AdditiveReferencePoseClip": {"fileID": 0},
            "m_AdditiveReferencePoseTime": 0,
            "m_StartTime": self.start_time,
            "m_StopTime": self.stop_time,
            "m_OrientationOffsetY": self.orientation_offset_y,
            "m_Level": self.level,
            "m_CycleOffset": self.cycle_offset,
            "m_HasAdditiveReferencePose": 1 if self.has_additive_reference_pose else 0,
            "m_LoopTime": 1 if self.loop_time else 0,
            "m_LoopBlend": 1 if self.loop_blend else 0,
            "m_LoopBlendOrientation": 1 if self.loop_blend_orientation else 0,
            "m_LoopBlendPositionY": 1 if self.loop_blend_position_y else 0,
            "m_LoopBlendPositionXZ": 1 if self.loop_blend_position_xz else 0,
            "m_KeepOriginalOrientation": 1 if self.keep_original_orientation else 0,
            "m_KeepOriginalPositionY": 1 if self.keep_original_position_y else 0,
            "m_KeepOriginalPositionXZ": 1 if self.keep_original_position_xz else 0,
            "m_HeightFromFeet": 1 if self.height_from_feet else 0,
            "m_Mirror": 1 if self.mirror else 0,
        }


@dataclass
class AnimationClip:
    """Represents a complete Unity AnimationClip (.anim file).

    This is the top-level structure for animation data.
    """

    name: str = ""
    file_id: int = 7400000  # Standard AnimationClip fileID
    legacy: bool = False
    compressed: bool = False
    use_high_quality_curve: bool = True
    sample_rate: float = 60.0
    wrap_mode: int = 0
    settings: AnimationClipSettings = field(default_factory=AnimationClipSettings)
    curves: list[AnimationCurve] = field(default_factory=list)
    events: list[AnimationEvent] = field(default_factory=list)
    # Raw data for fields we don't parse
    _raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def duration(self) -> float:
        """Get the clip duration in seconds."""
        return self.settings.stop_time - self.settings.start_time

    @property
    def loop(self) -> bool:
        """Check if the clip loops."""
        return self.settings.loop_time

    @loop.setter
    def loop(self, value: bool) -> None:
        """Set the loop flag."""
        self.settings.loop_time = value

    def get_curve_counts(self) -> dict[str, int]:
        """Get counts of each curve type."""
        counts = {
            "position": 0,
            "rotation": 0,
            "euler": 0,
            "scale": 0,
            "float": 0,
            "pptr": 0,
        }
        for curve in self.curves:
            if curve.curve_type in counts:
                counts[curve.curve_type] += 1
        return counts

    def find_curve(self, path: str, attribute: str | None = None) -> AnimationCurve | None:
        """Find a curve by path and optionally attribute."""
        for curve in self.curves:
            if curve.path == path:
                if attribute is None or curve.attribute == attribute:
                    return curve
        return None

    def find_curves_by_path(self, path: str) -> list[AnimationCurve]:
        """Find all curves targeting a specific path."""
        return [c for c in self.curves if c.path == path]

    def find_curves_by_type(self, curve_type: str) -> list[AnimationCurve]:
        """Find all curves of a specific type."""
        return [c for c in self.curves if c.curve_type == curve_type]

"""Query operations for Unity AnimationClip data.

Provides functions to search and retrieve animation data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from unityflow.animation.models import (
    AnimationClip,
    AnimationCurve,
    Keyframe,
    PPtrKeyframe,
    Vector3Value,
)


@dataclass
class CurveInfo:
    """Summary information about an animation curve."""

    index: int
    curve_type: str
    path: str
    attribute: str
    class_name: str
    class_id: int
    key_count: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON output."""
        return {
            "index": self.index,
            "type": self.curve_type,
            "path": self.path,
            "attribute": self.attribute,
            "class_name": self.class_name,
            "class_id": self.class_id,
            "key_count": self.key_count,
        }


def list_curves(clip: AnimationClip, curve_type: str | None = None, path: str | None = None) -> list[CurveInfo]:
    """List curves in an animation clip.

    Args:
        clip: The AnimationClip to query
        curve_type: Optional filter by type (position, euler, scale, float, pptr)
        path: Optional filter by path prefix

    Returns:
        List of CurveInfo objects
    """
    result: list[CurveInfo] = []

    for i, curve in enumerate(clip.curves):
        # Apply type filter
        if curve_type is not None and curve.curve_type != curve_type:
            continue

        # Apply path filter
        if path is not None and not curve.path.startswith(path):
            continue

        result.append(
            CurveInfo(
                index=i,
                curve_type=curve.curve_type,
                path=curve.path,
                attribute=curve.attribute,
                class_name=curve.class_name,
                class_id=curve.class_id,
                key_count=curve.key_count,
            )
        )

    return result


def get_curve(clip: AnimationClip, path: str, attribute: str | None = None) -> AnimationCurve | None:
    """Get a curve by path and optionally attribute.

    Args:
        clip: The AnimationClip to query
        path: The target GameObject path
        attribute: Optional attribute filter

    Returns:
        The matching curve or None
    """
    return clip.find_curve(path, attribute)


def get_curve_by_index(clip: AnimationClip, index: int) -> AnimationCurve | None:
    """Get a curve by its index.

    Args:
        clip: The AnimationClip to query
        index: The curve index

    Returns:
        The curve at the index or None if out of bounds
    """
    if 0 <= index < len(clip.curves):
        return clip.curves[index]
    return None


def get_keyframe(
    curve: AnimationCurve,
    key_index: int,
) -> Keyframe | PPtrKeyframe | None:
    """Get a keyframe from a curve by index.

    Args:
        curve: The curve to query
        key_index: The keyframe index

    Returns:
        The keyframe at the index or None if out of bounds
    """
    if curve.curve_type == "pptr":
        if 0 <= key_index < len(curve.pptr_keyframes):
            return curve.pptr_keyframes[key_index]
    else:
        if 0 <= key_index < len(curve.keyframes):
            return curve.keyframes[key_index]
    return None


def get_keyframes(
    curve: AnimationCurve,
) -> list[Keyframe] | list[PPtrKeyframe]:
    """Get all keyframes from a curve.

    Args:
        curve: The curve to query

    Returns:
        List of keyframes
    """
    if curve.curve_type == "pptr":
        return curve.pptr_keyframes
    return curve.keyframes


def keyframe_to_dict(keyframe: Keyframe | PPtrKeyframe, curve_type: str) -> dict[str, Any]:
    """Convert a keyframe to a dictionary for output.

    Args:
        keyframe: The keyframe to convert
        curve_type: The type of curve this keyframe belongs to

    Returns:
        Dictionary representation of the keyframe
    """
    if isinstance(keyframe, PPtrKeyframe):
        return {
            "time": keyframe.time,
            "fileID": keyframe.file_id,
            "guid": keyframe.guid,
            "type": keyframe.type,
        }

    # Regular keyframe
    result: dict[str, Any] = {"time": keyframe.time}

    if isinstance(keyframe.value, Vector3Value):
        result["value"] = keyframe.value.to_dict()
        if isinstance(keyframe.in_slope, Vector3Value):
            result["inSlope"] = keyframe.in_slope.to_dict()
        if isinstance(keyframe.out_slope, Vector3Value):
            result["outSlope"] = keyframe.out_slope.to_dict()
        if isinstance(keyframe.in_weight, Vector3Value):
            result["inWeight"] = keyframe.in_weight.to_dict()
        if isinstance(keyframe.out_weight, Vector3Value):
            result["outWeight"] = keyframe.out_weight.to_dict()
    else:
        result["value"] = keyframe.value
        result["inSlope"] = keyframe.in_slope
        result["outSlope"] = keyframe.out_slope
        result["inWeight"] = keyframe.in_weight
        result["outWeight"] = keyframe.out_weight

    result["tangentMode"] = keyframe.tangent_mode
    result["weightedMode"] = keyframe.weighted_mode

    return result


def find_keyframe_at_time(
    curve: AnimationCurve,
    time: float,
    tolerance: float = 0.0001,
) -> int | None:
    """Find the index of a keyframe at a specific time.

    Args:
        curve: The curve to search
        time: The time to search for
        tolerance: Time matching tolerance

    Returns:
        The keyframe index or None if not found
    """
    if curve.curve_type == "pptr":
        for i, kf in enumerate(curve.pptr_keyframes):
            if abs(kf.time - time) <= tolerance:
                return i
    else:
        for i, kf in enumerate(curve.keyframes):
            if abs(kf.time - time) <= tolerance:
                return i
    return None


def get_value_at_time(curve: AnimationCurve, time: float) -> Any:
    """Get the interpolated value at a specific time.

    Note: This performs simple linear interpolation. Unity uses
    more complex curve interpolation that we don't fully replicate.

    Args:
        curve: The curve to sample
        time: The time to sample at

    Returns:
        The interpolated value (or None for pptr curves)
    """
    if curve.curve_type == "pptr":
        # PPtrCurves use step interpolation (no interpolation)
        if not curve.pptr_keyframes:
            return None
        # Find the keyframe at or before the given time
        result = curve.pptr_keyframes[0]
        for kf in curve.pptr_keyframes:
            if kf.time <= time:
                result = kf
            else:
                break
        return {"fileID": result.file_id, "guid": result.guid, "type": result.type}

    if not curve.keyframes:
        return None

    # Find surrounding keyframes
    before: Keyframe | None = None
    after: Keyframe | None = None

    for kf in curve.keyframes:
        if kf.time <= time:
            before = kf
        if kf.time >= time and after is None:
            after = kf

    if before is None:
        before = curve.keyframes[0]
    if after is None:
        after = curve.keyframes[-1]

    # Same keyframe or at exact time
    if before is after or abs(before.time - after.time) < 0.0001:
        return before.value

    # Linear interpolation (simplified)
    t = (time - before.time) / (after.time - before.time)

    if isinstance(before.value, Vector3Value) and isinstance(after.value, Vector3Value):
        return Vector3Value(
            x=before.value.x + (after.value.x - before.value.x) * t,
            y=before.value.y + (after.value.y - before.value.y) * t,
            z=before.value.z + (after.value.z - before.value.z) * t,
        )
    elif isinstance(before.value, int | float) and isinstance(after.value, int | float):
        return before.value + (after.value - before.value) * t

    return before.value

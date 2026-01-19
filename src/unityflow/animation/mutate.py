"""Mutation operations for Unity AnimationClip data.

Provides functions to modify animation data (add/remove/update curves and keyframes).
"""

from __future__ import annotations

from typing import Any

from unityflow.animation.models import (
    AnimationClip,
    AnimationCurve,
    AnimationEvent,
    Keyframe,
    PPtrKeyframe,
    TangentMode,
    Vector3Value,
)


def set_keyframe_value(
    curve: AnimationCurve,
    key_index: int,
    value: Any,
    time: float | None = None,
    tangent: str | None = None,
) -> bool:
    """Set the value of a keyframe.

    Args:
        curve: The curve containing the keyframe
        key_index: Index of the keyframe to modify
        value: New value (float, dict for Vector3, or dict for pptr)
        time: Optional new time value
        tangent: Optional tangent mode ("smooth", "linear", "constant", "flat")

    Returns:
        True if successful, False if index out of bounds
    """
    if curve.curve_type == "pptr":
        if not (0 <= key_index < len(curve.pptr_keyframes)):
            return False

        kf = curve.pptr_keyframes[key_index]
        if time is not None:
            kf.time = time

        if isinstance(value, dict):
            kf.file_id = value.get("fileID", kf.file_id)
            kf.guid = value.get("guid", kf.guid)
            kf.type = value.get("type", kf.type)
        return True

    # Regular keyframe
    if not (0 <= key_index < len(curve.keyframes)):
        return False

    kf = curve.keyframes[key_index]

    if time is not None:
        kf.time = time

    # Update value
    if curve.is_vector_curve:
        if isinstance(value, dict):
            kf.value = Vector3Value.from_dict(value)
        elif isinstance(value, Vector3Value):
            kf.value = value
    else:
        if isinstance(value, int | float):
            kf.value = float(value)

    # Update tangent mode
    if tangent is not None:
        kf.tangent_mode = _get_tangent_mode(tangent)

    return True


def add_keyframe(
    curve: AnimationCurve,
    time: float,
    value: Any,
    tangent: str = "smooth",
) -> int:
    """Add a new keyframe to a curve.

    Args:
        curve: The curve to add the keyframe to
        time: Time of the new keyframe
        value: Value at the keyframe
        tangent: Tangent mode ("smooth", "linear", "constant", "flat")

    Returns:
        Index of the inserted keyframe
    """
    if curve.curve_type == "pptr":
        # PPtrKeyframe
        if isinstance(value, dict):
            new_kf = PPtrKeyframe(
                time=time,
                file_id=value.get("fileID", 0),
                guid=value.get("guid", ""),
                type=value.get("type", 0),
            )
        else:
            new_kf = PPtrKeyframe(time=time)

        # Insert in sorted order
        insert_idx = 0
        for i, kf in enumerate(curve.pptr_keyframes):
            if kf.time > time:
                break
            insert_idx = i + 1

        curve.pptr_keyframes.insert(insert_idx, new_kf)
        return insert_idx

    # Regular keyframe
    if curve.is_vector_curve:
        if isinstance(value, dict):
            vec_value = Vector3Value.from_dict(value)
        elif isinstance(value, Vector3Value):
            vec_value = value
        else:
            vec_value = Vector3Value()

        new_kf = Keyframe(
            time=time,
            value=vec_value,
            in_slope=Vector3Value(),
            out_slope=Vector3Value(),
            tangent_mode=_get_tangent_mode(tangent),
            in_weight=Vector3Value(x=0.333333, y=0.333333, z=0.333333),
            out_weight=Vector3Value(x=0.333333, y=0.333333, z=0.333333),
        )
    else:
        float_value = float(value) if isinstance(value, int | float) else 0.0
        new_kf = Keyframe(
            time=time,
            value=float_value,
            in_slope=0.0,
            out_slope=0.0,
            tangent_mode=_get_tangent_mode(tangent),
            in_weight=0.333333,
            out_weight=0.333333,
        )

    # Insert in sorted order
    insert_idx = 0
    for i, kf in enumerate(curve.keyframes):
        if kf.time > time:
            break
        insert_idx = i + 1

    curve.keyframes.insert(insert_idx, new_kf)
    return insert_idx


def delete_keyframe(curve: AnimationCurve, key_index: int) -> bool:
    """Delete a keyframe from a curve.

    Args:
        curve: The curve containing the keyframe
        key_index: Index of the keyframe to delete

    Returns:
        True if successful, False if index out of bounds
    """
    if curve.curve_type == "pptr":
        if not (0 <= key_index < len(curve.pptr_keyframes)):
            return False
        curve.pptr_keyframes.pop(key_index)
        return True

    if not (0 <= key_index < len(curve.keyframes)):
        return False
    curve.keyframes.pop(key_index)
    return True


def add_curve(
    clip: AnimationClip,
    path: str,
    curve_type: str,
    attribute: str = "",
    class_id: int = 0,
    keyframes: list[dict[str, Any]] | None = None,
) -> AnimationCurve:
    """Add a new curve to an animation clip.

    Args:
        clip: The AnimationClip to add the curve to
        path: Target GameObject path
        curve_type: Type of curve (position, euler, scale, float, pptr)
        attribute: Property attribute (for float/pptr curves)
        class_id: Unity classID for the component
        keyframes: Optional list of keyframe dictionaries

    Returns:
        The newly created AnimationCurve
    """
    # Determine attribute based on curve type if not provided
    if not attribute:
        if curve_type == "position":
            attribute = "localPosition"
            class_id = class_id or 4  # Transform
        elif curve_type == "euler":
            attribute = "localEulerAngles"
            class_id = class_id or 4
        elif curve_type == "scale":
            attribute = "localScale"
            class_id = class_id or 4

    curve = AnimationCurve(
        path=path,
        attribute=attribute,
        class_id=class_id,
        curve_type=curve_type,
    )

    # Add keyframes if provided
    if keyframes:
        is_vector = curve_type in ("position", "euler", "scale")
        for kf_data in keyframes:
            if curve_type == "pptr":
                pptr_kf = PPtrKeyframe(
                    time=float(kf_data.get("time", 0)),
                    file_id=int(kf_data.get("fileID", kf_data.get("value", {}).get("fileID", 0))),
                    guid=str(kf_data.get("guid", kf_data.get("value", {}).get("guid", ""))),
                    type=int(kf_data.get("type", kf_data.get("value", {}).get("type", 0))),
                )
                curve.pptr_keyframes.append(pptr_kf)
            else:
                kf = Keyframe.from_dict(kf_data, is_vector=is_vector)
                curve.keyframes.append(kf)

    clip.curves.append(curve)
    return curve


def delete_curve(
    clip: AnimationClip,
    index: int | None = None,
    path: str | None = None,
    attribute: str | None = None,
) -> bool:
    """Delete a curve from an animation clip.

    Args:
        clip: The AnimationClip to modify
        index: Index of the curve to delete (if specified)
        path: Path to match (if index not specified)
        attribute: Attribute to match (used with path)

    Returns:
        True if a curve was deleted, False otherwise
    """
    if index is not None:
        if 0 <= index < len(clip.curves):
            clip.curves.pop(index)
            return True
        return False

    # Find by path/attribute
    for i, curve in enumerate(clip.curves):
        if curve.path == path:
            if attribute is None or curve.attribute == attribute:
                clip.curves.pop(i)
                return True

    return False


def set_clip_settings(
    clip: AnimationClip,
    loop: bool | None = None,
    duration: float | None = None,
    sample_rate: float | None = None,
    **kwargs: Any,
) -> None:
    """Update animation clip settings.

    Args:
        clip: The AnimationClip to modify
        loop: Set loop mode
        duration: Set clip duration (stop_time)
        sample_rate: Set sample rate
        **kwargs: Additional AnimationClipSettings attributes
    """
    if loop is not None:
        clip.settings.loop_time = loop

    if duration is not None:
        clip.settings.stop_time = duration

    if sample_rate is not None:
        clip.sample_rate = sample_rate

    # Handle additional settings
    settings_attrs = [
        "start_time",
        "stop_time",
        "cycle_offset",
        "loop_blend",
        "mirror",
        "keep_original_position_y",
    ]
    for attr in settings_attrs:
        if attr in kwargs:
            setattr(clip.settings, attr, kwargs[attr])


def add_event(
    clip: AnimationClip,
    time: float,
    function_name: str,
    data: str = "",
    float_parameter: float = 0.0,
    int_parameter: int = 0,
) -> AnimationEvent:
    """Add an animation event to a clip.

    Args:
        clip: The AnimationClip to modify
        time: Event trigger time
        function_name: Name of the function to call
        data: String parameter
        float_parameter: Float parameter
        int_parameter: Int parameter

    Returns:
        The newly created AnimationEvent
    """
    event = AnimationEvent(
        time=time,
        function_name=function_name,
        data=data,
        float_parameter=float_parameter,
        int_parameter=int_parameter,
    )

    # Insert in sorted order
    insert_idx = 0
    for i, e in enumerate(clip.events):
        if e.time > time:
            break
        insert_idx = i + 1

    clip.events.insert(insert_idx, event)
    return event


def delete_event(clip: AnimationClip, index: int) -> bool:
    """Delete an animation event from a clip.

    Args:
        clip: The AnimationClip to modify
        index: Index of the event to delete

    Returns:
        True if successful, False if index out of bounds
    """
    if 0 <= index < len(clip.events):
        clip.events.pop(index)
        return True
    return False


def _get_tangent_mode(mode_name: str) -> int:
    """Convert tangent mode name to integer value."""
    mode_map = {
        "free": TangentMode.FREE,
        "smooth": TangentMode.AUTO,
        "auto": TangentMode.AUTO,
        "linear": TangentMode.FREE,
        "constant": TangentMode.CONSTANT,
        "flat": TangentMode.FLAT,
    }
    return mode_map.get(mode_name.lower(), TangentMode.AUTO)

"""Animation module for Unity .anim file support.

This module provides tools for reading, querying, and modifying Unity AnimationClip files.
"""

from unityflow.animation.models import (
    AnimationClip,
    AnimationClipSettings,
    AnimationCurve,
    AnimationEvent,
    CurveType,
    Keyframe,
    PPtrKeyframe,
    TangentMode,
    Vector3Value,
    WrapMode,
)
from unityflow.animation.mutate import (
    add_curve,
    add_event,
    add_keyframe,
    delete_curve,
    delete_event,
    delete_keyframe,
    set_clip_settings,
    set_keyframe_value,
)
from unityflow.animation.parser import parse_animation_clip
from unityflow.animation.query import (
    CurveInfo,
    find_keyframe_at_time,
    get_curve,
    get_curve_by_index,
    get_keyframe,
    get_keyframes,
    get_value_at_time,
    keyframe_to_dict,
    list_curves,
)
from unityflow.animation.writer import create_empty_animation_clip, write_animation_clip

__all__ = [
    # Models
    "AnimationClip",
    "AnimationClipSettings",
    "AnimationCurve",
    "AnimationEvent",
    "CurveType",
    "Keyframe",
    "PPtrKeyframe",
    "TangentMode",
    "Vector3Value",
    "WrapMode",
    # Parser
    "parse_animation_clip",
    # Writer
    "write_animation_clip",
    "create_empty_animation_clip",
    # Query
    "CurveInfo",
    "get_curve",
    "get_curve_by_index",
    "get_keyframe",
    "get_keyframes",
    "get_value_at_time",
    "keyframe_to_dict",
    "list_curves",
    "find_keyframe_at_time",
    # Mutate
    "add_curve",
    "add_event",
    "add_keyframe",
    "delete_curve",
    "delete_event",
    "delete_keyframe",
    "set_clip_settings",
    "set_keyframe_value",
]

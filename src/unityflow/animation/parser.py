"""Parser for Unity AnimationClip (.anim) files.

Converts Unity YAML animation data into structured AnimationClip objects.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from unityflow.animation.models import (
    AnimationClip,
    AnimationClipSettings,
    AnimationCurve,
    AnimationEvent,
)
from unityflow.parser import UnityYAMLDocument


def parse_animation_clip(source: str | Path | UnityYAMLDocument) -> AnimationClip:
    """Parse a Unity animation clip file or document.

    Args:
        source: Path to .anim file, YAML content string, or UnityYAMLDocument

    Returns:
        Parsed AnimationClip object

    Raises:
        ValueError: If no AnimationClip object found in the document
    """
    # Load document if needed
    if isinstance(source, UnityYAMLDocument):
        doc = source
    elif isinstance(source, Path):
        doc = UnityYAMLDocument.load(source)
    else:
        # Assume it's a file path string
        doc = UnityYAMLDocument.load(Path(source))

    # Find AnimationClip object (classID 74)
    clip_objects = doc.get_by_class_id(74)
    if not clip_objects:
        raise ValueError("No AnimationClip object found in document")

    clip_obj = clip_objects[0]
    content = clip_obj.get_content()
    if content is None:
        raise ValueError("AnimationClip object has no content")

    return _parse_clip_content(content, clip_obj.file_id, clip_obj.data)


def _parse_clip_content(content: dict[str, Any], file_id: int, raw_data: dict[str, Any]) -> AnimationClip:
    """Parse AnimationClip content dictionary."""
    clip = AnimationClip(
        name=content.get("m_Name", ""),
        file_id=file_id,
        legacy=bool(content.get("m_Legacy", 0)),
        compressed=bool(content.get("m_Compressed", 0)),
        use_high_quality_curve=bool(content.get("m_UseHighQualityCurve", 1)),
        sample_rate=float(content.get("m_SampleRate", 60)),
        wrap_mode=int(content.get("m_WrapMode", 0)),
        _raw_data=raw_data,
    )

    # Parse settings
    settings_data = content.get("m_AnimationClipSettings", {})
    if settings_data:
        clip.settings = AnimationClipSettings.from_dict(settings_data)

    # Parse curves
    curves: list[AnimationCurve] = []

    # Position curves
    for curve_data in content.get("m_PositionCurves", []):
        curves.append(AnimationCurve.from_position_curve(curve_data))

    # Euler curves (rotation as Euler angles)
    for curve_data in content.get("m_EulerCurves", []):
        curves.append(AnimationCurve.from_euler_curve(curve_data))

    # Scale curves
    for curve_data in content.get("m_ScaleCurves", []):
        curves.append(AnimationCurve.from_scale_curve(curve_data))

    # Float curves
    for curve_data in content.get("m_FloatCurves", []):
        curves.append(AnimationCurve.from_float_curve(curve_data))

    # PPtrCurves (object references like sprites)
    for curve_data in content.get("m_PPtrCurves", []):
        curves.append(AnimationCurve.from_pptr_curve(curve_data))

    clip.curves = curves

    # Parse events
    events: list[AnimationEvent] = []
    for event_data in content.get("m_Events", []):
        events.append(AnimationEvent.from_dict(event_data))
    clip.events = events

    return clip


def parse_animation_clip_from_dict(data: dict[str, Any], file_id: int = 7400000) -> AnimationClip:
    """Parse an AnimationClip from a dictionary.

    This is useful when you have the clip data already loaded.

    Args:
        data: Dictionary with AnimationClip key containing clip data
        file_id: File ID to assign (default: 7400000)

    Returns:
        Parsed AnimationClip object
    """
    content = data.get("AnimationClip", data)
    return _parse_clip_content(content, file_id, data)

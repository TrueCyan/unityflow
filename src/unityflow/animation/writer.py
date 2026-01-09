"""Writer for Unity AnimationClip (.anim) files.

Serializes AnimationClip objects back to Unity YAML format.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from unityflow.animation.models import AnimationClip
from unityflow.parser import UnityYAMLDocument, UnityYAMLObject


def write_animation_clip(clip: AnimationClip, path: str | Path | None = None) -> str:
    """Serialize an AnimationClip to Unity YAML format.

    Args:
        clip: The AnimationClip to serialize
        path: Optional output file path. If provided, writes to file.

    Returns:
        The serialized YAML content as a string
    """
    doc = animation_clip_to_document(clip)
    content = doc.dump()

    if path is not None:
        output_path = Path(path)
        output_path.write_text(content, encoding="utf-8", newline="\n")

    return content


def animation_clip_to_document(clip: AnimationClip) -> UnityYAMLDocument:
    """Convert an AnimationClip to a UnityYAMLDocument."""
    content = _build_clip_content(clip)

    obj = UnityYAMLObject(
        class_id=74,  # AnimationClip
        file_id=clip.file_id,
        data={"AnimationClip": content},
        stripped=False,
    )

    doc = UnityYAMLDocument(objects=[obj])
    return doc


def _build_clip_content(clip: AnimationClip) -> dict[str, Any]:
    """Build the AnimationClip content dictionary."""
    # Start with raw data if available to preserve unhandled fields
    if clip._raw_data and "AnimationClip" in clip._raw_data:
        content = dict(clip._raw_data["AnimationClip"])
    else:
        content = _build_default_clip_content()

    # Update with current values
    content["m_Name"] = clip.name
    content["m_Legacy"] = 1 if clip.legacy else 0
    content["m_Compressed"] = 1 if clip.compressed else 0
    content["m_UseHighQualityCurve"] = 1 if clip.use_high_quality_curve else 0
    content["m_SampleRate"] = clip.sample_rate
    content["m_WrapMode"] = clip.wrap_mode

    # Build curve arrays
    position_curves = []
    euler_curves = []
    scale_curves = []
    float_curves = []
    pptr_curves = []

    for curve in clip.curves:
        if curve.curve_type == "position":
            position_curves.append(curve.to_position_curve_dict())
        elif curve.curve_type == "euler":
            euler_curves.append(curve.to_euler_curve_dict())
        elif curve.curve_type == "scale":
            scale_curves.append(curve.to_scale_curve_dict())
        elif curve.curve_type == "float":
            float_curves.append(curve.to_float_curve_dict())
        elif curve.curve_type == "pptr":
            pptr_curves.append(curve.to_pptr_curve_dict())

    content["m_PositionCurves"] = position_curves
    content["m_EulerCurves"] = euler_curves
    content["m_ScaleCurves"] = scale_curves
    content["m_FloatCurves"] = float_curves
    content["m_PPtrCurves"] = pptr_curves

    # Rotation curves (quaternion) - preserve if present, otherwise empty
    if "m_RotationCurves" not in content:
        content["m_RotationCurves"] = []

    # Compressed rotation curves - preserve if present, otherwise empty
    if "m_CompressedRotationCurves" not in content:
        content["m_CompressedRotationCurves"] = []

    # Events
    content["m_Events"] = [event.to_dict() for event in clip.events]

    # Settings
    content["m_AnimationClipSettings"] = clip.settings.to_dict()

    return content


def _build_default_clip_content() -> dict[str, Any]:
    """Build default AnimationClip content structure."""
    return {
        "m_ObjectHideFlags": 0,
        "m_CorrespondingSourceObject": {"fileID": 0},
        "m_PrefabInstance": {"fileID": 0},
        "m_PrefabAsset": {"fileID": 0},
        "m_Name": "",
        "serializedVersion": 6,
        "m_Legacy": 0,
        "m_Compressed": 0,
        "m_UseHighQualityCurve": 1,
        "m_RotationCurves": [],
        "m_CompressedRotationCurves": [],
        "m_EulerCurves": [],
        "m_PositionCurves": [],
        "m_ScaleCurves": [],
        "m_FloatCurves": [],
        "m_PPtrCurves": [],
        "m_SampleRate": 60,
        "m_WrapMode": 0,
        "m_Bounds": {
            "m_Center": {"x": 0, "y": 0, "z": 0},
            "m_Extent": {"x": 0, "y": 0, "z": 0},
        },
        "m_ClipBindingConstant": {
            "genericBindings": [],
            "pptrCurveMapping": [],
        },
        "m_AnimationClipSettings": {
            "serializedVersion": 2,
            "m_AdditiveReferencePoseClip": {"fileID": 0},
            "m_AdditiveReferencePoseTime": 0,
            "m_StartTime": 0,
            "m_StopTime": 1,
            "m_OrientationOffsetY": 0,
            "m_Level": 0,
            "m_CycleOffset": 0,
            "m_HasAdditiveReferencePose": 0,
            "m_LoopTime": 0,
            "m_LoopBlend": 0,
            "m_LoopBlendOrientation": 0,
            "m_LoopBlendPositionY": 0,
            "m_LoopBlendPositionXZ": 0,
            "m_KeepOriginalOrientation": 0,
            "m_KeepOriginalPositionY": 1,
            "m_KeepOriginalPositionXZ": 0,
            "m_HeightFromFeet": 0,
            "m_Mirror": 0,
        },
        "m_EditorCurves": [],
        "m_EulerEditorCurves": [],
        "m_HasGenericRootTransform": 0,
        "m_HasMotionFloatCurves": 0,
        "m_Events": [],
    }


def create_empty_animation_clip(
    name: str,
    duration: float = 1.0,
    sample_rate: float = 60.0,
    loop: bool = False,
) -> AnimationClip:
    """Create a new empty AnimationClip.

    Args:
        name: Name of the clip
        duration: Duration in seconds
        sample_rate: Sample rate in Hz (default 60)
        loop: Whether the clip should loop

    Returns:
        A new AnimationClip instance
    """
    from unityflow.animation.models import AnimationClipSettings

    settings = AnimationClipSettings(
        start_time=0.0,
        stop_time=duration,
        loop_time=loop,
    )

    return AnimationClip(
        name=name,
        sample_rate=sample_rate,
        settings=settings,
    )

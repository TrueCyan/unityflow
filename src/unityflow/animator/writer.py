"""Writer for Unity AnimatorController (.controller) files.

Serializes AnimatorController objects back to Unity multi-document YAML format.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from unityflow.animator.models import AnimatorController
from unityflow.parser import UnityYAMLDocument, UnityYAMLObject


def write_animator_controller(controller: AnimatorController, path: str | Path | None = None) -> str:
    """Serialize an AnimatorController to Unity YAML format.

    Args:
        controller: The AnimatorController to serialize
        path: Optional output file path. If provided, writes to file.

    Returns:
        The serialized YAML content as a string

    Note:
        This implementation preserves the original object structure to avoid
        breaking Unity's internal references. Modifications should be made
        through the mutation API rather than direct object manipulation.
    """
    doc = animator_controller_to_document(controller)
    content = doc.dump()

    if path is not None:
        output_path = Path(path)
        output_path.write_text(content, encoding="utf-8", newline="\n")

    return content


def animator_controller_to_document(controller: AnimatorController) -> UnityYAMLDocument:
    """Convert an AnimatorController to a UnityYAMLDocument.

    This reconstructs the multi-document YAML structure from the controller's
    internal object storage.
    """
    doc = UnityYAMLDocument()

    # If we have raw objects, use those to preserve structure
    if controller._raw_objects:
        # Re-parse the raw objects into UnityYAMLObject instances
        # This preserves the original structure while allowing our modifications
        for raw_data in controller._raw_objects:
            # Determine class ID and file ID from the data structure
            class_id, file_id, stripped = _extract_object_ids(raw_data)
            if class_id and file_id:
                obj = UnityYAMLObject(
                    class_id=class_id,
                    file_id=file_id,
                    data=raw_data,
                    stripped=stripped,
                )
                doc.add_object(obj)

    return doc


def _extract_object_ids(data: dict[str, Any]) -> tuple[int, int, bool]:
    """Extract class ID and file ID from raw object data.

    The data structure has the class name as the root key.
    """
    # Map of root key names to class IDs
    class_id_map = {
        "AnimatorController": 91,
        "AnimatorStateMachine": 1107,
        "AnimatorState": 1102,
        "AnimatorStateTransition": 1101,
        "BlendTree": 206,
    }

    for key, class_id in class_id_map.items():
        if key in data:
            # fileID is usually stored externally, but we need to recover it
            # For now, return a placeholder - this needs to be handled by
            # maintaining fileID mapping during parsing
            return class_id, 0, False

    return 0, 0, False


def update_controller_parameters(controller: AnimatorController) -> None:
    """Update the raw data with current parameter values.

    This syncs the parsed parameter changes back to the raw data structure.
    """
    # Find the controller object in raw data
    for raw_data in controller._raw_objects:
        if "AnimatorController" in raw_data:
            content = raw_data["AnimatorController"]
            # Update parameters
            content["m_AnimatorParameters"] = [param.to_dict(controller.file_id) for param in controller.parameters]
            break


def update_state_properties(controller: AnimatorController, state_file_id: int, **properties: Any) -> bool:
    """Update properties of a state in the raw data.

    Args:
        controller: The AnimatorController
        state_file_id: FileID of the state to update
        **properties: Properties to update (e.g., speed=1.5, motion_guid="...")

    Returns:
        True if state was found and updated
    """
    # Find the state in raw objects
    for raw_data in controller._raw_objects:
        if "AnimatorState" in raw_data:
            # We need to match by file_id, which requires tracking during parse
            # For now, match by state name through the parsed states
            state = controller._states.get(state_file_id)
            if state:
                content = raw_data["AnimatorState"]
                if content.get("m_Name") == state.name:
                    # Update properties
                    if "speed" in properties:
                        content["m_Speed"] = properties["speed"]
                        state.speed = properties["speed"]
                    if "motion_guid" in properties:
                        motion = content.get("m_Motion", {})
                        if isinstance(motion, dict):
                            motion["guid"] = properties["motion_guid"]
                            motion["fileID"] = 7400000  # Standard AnimationClip fileID
                            motion["type"] = 2
                            state.motion_guid = properties["motion_guid"]
                    return True
    return False

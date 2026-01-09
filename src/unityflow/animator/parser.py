"""Parser for Unity AnimatorController (.controller) files.

Converts Unity multi-document YAML animator data into structured AnimatorController objects.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from unityflow.animator.models import (
    AnimatorController,
    AnimatorLayer,
    AnimatorParameter,
    AnimatorState,
    AnimatorStateMachine,
    AnimatorStateTransition,
)
from unityflow.parser import UnityYAMLDocument

# Unity classIDs for animator objects
ANIMATOR_CONTROLLER_CLASS_ID = 91
ANIMATOR_STATE_MACHINE_CLASS_ID = 1107
ANIMATOR_STATE_CLASS_ID = 1102
ANIMATOR_STATE_TRANSITION_CLASS_ID = 1101
BLEND_TREE_CLASS_ID = 206


def parse_animator_controller(source: str | Path | UnityYAMLDocument) -> AnimatorController:
    """Parse a Unity animator controller file or document.

    Args:
        source: Path to .controller file, YAML content string, or UnityYAMLDocument

    Returns:
        Parsed AnimatorController object

    Raises:
        ValueError: If no AnimatorController object found in the document
    """
    # Load document if needed
    if isinstance(source, UnityYAMLDocument):
        doc = source
    elif isinstance(source, Path):
        doc = UnityYAMLDocument.load(source)
    else:
        doc = UnityYAMLDocument.load(Path(source))

    # Find AnimatorController object (classID 91)
    controller_objects = doc.get_by_class_id(ANIMATOR_CONTROLLER_CLASS_ID)
    if not controller_objects:
        raise ValueError("No AnimatorController object found in document")

    controller_obj = controller_objects[0]
    content = controller_obj.get_content()
    if content is None:
        raise ValueError("AnimatorController object has no content")

    # Create controller with basic info
    controller = AnimatorController(
        file_id=controller_obj.file_id,
        name=content.get("m_Name", ""),
    )

    # Parse all objects first (build lookup maps)
    _parse_all_objects(doc, controller)

    # Parse parameters
    for param_data in content.get("m_AnimatorParameters", []):
        controller.parameters.append(AnimatorParameter.from_dict(param_data))

    # Parse layers
    for layer_data in content.get("m_AnimatorLayers", []):
        layer = AnimatorLayer.from_dict(layer_data)

        # Resolve state machine reference
        if layer.state_machine_id in controller._state_machines:
            layer.state_machine = controller._state_machines[layer.state_machine_id]

        controller.layers.append(layer)

    # Resolve cross-references
    _resolve_references(controller)

    return controller


def _parse_all_objects(doc: UnityYAMLDocument, controller: AnimatorController) -> None:
    """Parse all animator-related objects and store in lookup maps."""
    for obj in doc.objects:
        if obj.class_id == ANIMATOR_STATE_MACHINE_CLASS_ID:
            machine = AnimatorStateMachine.from_dict(obj.data, obj.file_id)
            controller._state_machines[obj.file_id] = machine

        elif obj.class_id == ANIMATOR_STATE_CLASS_ID:
            state = AnimatorState.from_dict(obj.data, obj.file_id)
            controller._states[obj.file_id] = state

        elif obj.class_id == ANIMATOR_STATE_TRANSITION_CLASS_ID:
            transition = AnimatorStateTransition.from_dict(obj.data, obj.file_id)
            controller._transitions[obj.file_id] = transition

    # Store raw objects for serialization
    controller._raw_objects = [obj.data for obj in doc.objects]


def _resolve_references(controller: AnimatorController) -> None:
    """Resolve fileID references between objects."""
    # Resolve state machine references
    for machine in controller._state_machines.values():
        # Resolve child states
        for state_id in machine.child_state_ids:
            if state_id in controller._states:
                machine.states.append(controller._states[state_id])

        # Resolve child state machines
        for machine_id in machine.child_machine_ids:
            if machine_id in controller._state_machines:
                machine.child_machines.append(controller._state_machines[machine_id])

        # Resolve any state transitions
        for trans_id in machine.any_state_transition_ids:
            if trans_id in controller._transitions:
                machine.any_state_transitions.append(controller._transitions[trans_id])

        # Resolve default state
        if machine.default_state_id in controller._states:
            machine.default_state = controller._states[machine.default_state_id]

    # Resolve state references
    for state in controller._states.values():
        # Resolve transitions
        for trans_id in state.transition_ids:
            if trans_id in controller._transitions:
                state.transitions.append(controller._transitions[trans_id])

    # Resolve transition destination names
    for transition in controller._transitions.values():
        if transition.destination_state_id in controller._states:
            transition.destination_state_name = controller._states[transition.destination_state_id].name
        elif transition.is_exit:
            transition.destination_state_name = "[Exit]"


def parse_animator_controller_info(source: str | Path | UnityYAMLDocument) -> dict[str, Any]:
    """Parse basic info from an animator controller without full resolution.

    This is faster than full parsing for overview information.

    Args:
        source: Path to .controller file

    Returns:
        Dictionary with basic controller info
    """
    if isinstance(source, UnityYAMLDocument):
        doc = source
    elif isinstance(source, Path):
        doc = UnityYAMLDocument.load(source)
    else:
        doc = UnityYAMLDocument.load(Path(source))

    # Find AnimatorController object
    controller_objects = doc.get_by_class_id(ANIMATOR_CONTROLLER_CLASS_ID)
    if not controller_objects:
        raise ValueError("No AnimatorController object found")

    content = controller_objects[0].get_content()
    if content is None:
        raise ValueError("AnimatorController has no content")

    # Count objects by type
    state_count = len(doc.get_by_class_id(ANIMATOR_STATE_CLASS_ID))
    transition_count = len(doc.get_by_class_id(ANIMATOR_STATE_TRANSITION_CLASS_ID))
    machine_count = len(doc.get_by_class_id(ANIMATOR_STATE_MACHINE_CLASS_ID))

    return {
        "name": content.get("m_Name", ""),
        "layer_count": len(content.get("m_AnimatorLayers", [])),
        "parameter_count": len(content.get("m_AnimatorParameters", [])),
        "state_count": state_count,
        "transition_count": transition_count,
        "state_machine_count": machine_count,
        "parameters": [
            {
                "name": p.get("m_Name", ""),
                "type": p.get("m_Type", 1),
            }
            for p in content.get("m_AnimatorParameters", [])
        ],
        "layers": [{"name": layer_data.get("m_Name", "")} for layer_data in content.get("m_AnimatorLayers", [])],
    }

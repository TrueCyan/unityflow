"""Query operations for Unity AnimatorController data.

Provides functions to search and retrieve animator controller data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from unityflow.animator.models import (
    AnimatorController,
    AnimatorLayer,
    AnimatorParameter,
    AnimatorState,
    AnimatorStateTransition,
)


@dataclass
class LayerInfo:
    """Summary information about an animator layer."""

    index: int
    name: str
    blending_mode: str
    default_weight: float
    state_count: int
    default_state_name: str | None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON output."""
        return {
            "index": self.index,
            "name": self.name,
            "blending_mode": self.blending_mode,
            "default_weight": self.default_weight,
            "state_count": self.state_count,
            "default_state": self.default_state_name,
        }


@dataclass
class StateInfo:
    """Summary information about an animator state."""

    name: str
    layer_name: str
    speed: float
    motion_name: str
    is_default: bool
    transition_count: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON output."""
        return {
            "name": self.name,
            "layer": self.layer_name,
            "speed": self.speed,
            "motion": self.motion_name,
            "is_default": self.is_default,
            "transition_count": self.transition_count,
        }


@dataclass
class TransitionInfo:
    """Summary information about a state transition."""

    source_name: str
    destination_name: str
    conditions: list[str]
    duration: float
    has_exit_time: bool
    exit_time: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON output."""
        return {
            "from": self.source_name,
            "to": self.destination_name,
            "conditions": self.conditions,
            "duration": self.duration,
            "has_exit_time": self.has_exit_time,
            "exit_time": self.exit_time,
        }


def list_parameters(controller: AnimatorController) -> list[dict[str, Any]]:
    """List all parameters in the controller.

    Returns:
        List of parameter info dictionaries
    """
    result = []
    for i, param in enumerate(controller.parameters):
        result.append(
            {
                "index": i,
                "name": param.name,
                "type": param.type_name,
                "default": param.default_value,
            }
        )
    return result


def list_layers(controller: AnimatorController) -> list[LayerInfo]:
    """List all layers in the controller.

    Returns:
        List of LayerInfo objects
    """
    result = []
    for i, layer in enumerate(controller.layers):
        state_count = 0
        default_state_name = None

        if layer.state_machine:
            state_count = len(layer.state_machine.states)
            if layer.state_machine.default_state:
                default_state_name = layer.state_machine.default_state.name

        result.append(
            LayerInfo(
                index=i,
                name=layer.name,
                blending_mode=layer.blending_mode_name,
                default_weight=layer.default_weight,
                state_count=state_count,
                default_state_name=default_state_name,
            )
        )
    return result


def list_states(controller: AnimatorController, layer_name: str | None = None) -> list[StateInfo]:
    """List all states, optionally filtered by layer.

    Args:
        controller: The AnimatorController to query
        layer_name: Optional layer name filter

    Returns:
        List of StateInfo objects
    """
    result = []

    for layer in controller.layers:
        if layer_name and layer.name != layer_name:
            continue

        if not layer.state_machine:
            continue

        for state in layer.state_machine.states:
            is_default = (
                layer.state_machine.default_state is not None
                and layer.state_machine.default_state.file_id == state.file_id
            )

            # Try to determine motion name
            motion_name = state.motion_name or ""
            if not motion_name and state.motion_guid:
                motion_name = f"(guid: {state.motion_guid[:8]}...)"

            result.append(
                StateInfo(
                    name=state.name,
                    layer_name=layer.name,
                    speed=state.speed,
                    motion_name=motion_name,
                    is_default=is_default,
                    transition_count=len(state.transitions),
                )
            )

    return result


def get_layer_by_name(controller: AnimatorController, name: str) -> AnimatorLayer | None:
    """Get a layer by name.

    Args:
        controller: The AnimatorController to query
        name: Layer name to find

    Returns:
        The layer or None if not found
    """
    return controller.find_layer(name)


def get_parameter_by_name(controller: AnimatorController, name: str) -> AnimatorParameter | None:
    """Get a parameter by name.

    Args:
        controller: The AnimatorController to query
        name: Parameter name to find

    Returns:
        The parameter or None if not found
    """
    return controller.find_parameter(name)


def get_state_by_name(
    controller: AnimatorController,
    state_name: str,
    layer_name: str | None = None,
) -> AnimatorState | None:
    """Get a state by name.

    Args:
        controller: The AnimatorController to query
        state_name: State name to find
        layer_name: Optional layer name filter

    Returns:
        The state or None if not found
    """
    if layer_name:
        return controller.find_state_in_layer(layer_name, state_name)

    # Search all layers
    for layer in controller.layers:
        if layer.state_machine:
            for state in layer.state_machine.states:
                if state.name == state_name:
                    return state
    return None


def get_state_transitions(
    controller: AnimatorController,
    state_name: str,
    layer_name: str | None = None,
) -> list[TransitionInfo]:
    """Get all transitions from a specific state.

    Args:
        controller: The AnimatorController to query
        state_name: Source state name
        layer_name: Optional layer name filter

    Returns:
        List of TransitionInfo objects
    """
    state = get_state_by_name(controller, state_name, layer_name)
    if not state:
        return []

    result = []
    for trans in state.transitions:
        conditions = [cond.format_condition() for cond in trans.conditions]
        dest_name = trans.destination_state_name or "(unknown)"

        result.append(
            TransitionInfo(
                source_name=state_name,
                destination_name=dest_name,
                conditions=conditions,
                duration=trans.transition_duration,
                has_exit_time=trans.has_exit_time,
                exit_time=trans.exit_time,
            )
        )

    return result


def get_any_state_transitions(
    controller: AnimatorController,
    layer_name: str | None = None,
) -> list[TransitionInfo]:
    """Get all Any State transitions for a layer.

    Args:
        controller: The AnimatorController to query
        layer_name: Optional layer name filter (uses first layer if not specified)

    Returns:
        List of TransitionInfo objects
    """
    result = []

    for layer in controller.layers:
        if layer_name and layer.name != layer_name:
            continue

        if not layer.state_machine:
            continue

        for trans in layer.state_machine.any_state_transitions:
            conditions = [cond.format_condition() for cond in trans.conditions]
            dest_name = trans.destination_state_name or "(unknown)"

            result.append(
                TransitionInfo(
                    source_name="Any State",
                    destination_name=dest_name,
                    conditions=conditions,
                    duration=trans.transition_duration,
                    has_exit_time=trans.has_exit_time,
                    exit_time=trans.exit_time,
                )
            )

    return result


def state_to_dict(state: AnimatorState) -> dict[str, Any]:
    """Convert a state to a detailed dictionary.

    Args:
        state: The state to convert

    Returns:
        Dictionary with all state properties
    """
    return {
        "name": state.name,
        "speed": state.speed,
        "cycleOffset": state.cycle_offset,
        "motion": (
            {
                "fileID": state.motion_file_id,
                "guid": state.motion_guid,
                "name": state.motion_name,
            }
            if state.motion_file_id or state.motion_guid
            else None
        ),
        "writeDefaultValues": state.write_default_values,
        "mirror": state.mirror,
        "tag": state.tag or None,
        "speedParameter": state.speed_parameter or None,
        "transitions": [
            {
                "to": t.destination_state_name,
                "conditions": [c.format_condition() for c in t.conditions],
                "duration": t.transition_duration,
                "hasExitTime": t.has_exit_time,
                "exitTime": t.exit_time,
            }
            for t in state.transitions
        ],
    }


def transition_to_dict(transition: AnimatorStateTransition) -> dict[str, Any]:
    """Convert a transition to a detailed dictionary.

    Args:
        transition: The transition to convert

    Returns:
        Dictionary with all transition properties
    """
    return {
        "name": transition.name or None,
        "destination": transition.destination_state_name,
        "isExit": transition.is_exit,
        "conditions": [c.format_condition() for c in transition.conditions],
        "duration": transition.transition_duration,
        "offset": transition.transition_offset,
        "hasExitTime": transition.has_exit_time,
        "exitTime": transition.exit_time,
        "hasFixedDuration": transition.has_fixed_duration,
        "interruptionSource": transition.interruption_source,
        "canTransitionToSelf": transition.can_transition_to_self,
    }

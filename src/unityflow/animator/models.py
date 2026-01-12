"""Data models for Unity AnimatorController (.controller) files.

These models represent the structured data within Unity animator controller files,
enabling programmatic access and modification of animator state machines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class ParameterType(IntEnum):
    """Animator parameter types."""

    FLOAT = 1
    INT = 3
    BOOL = 4
    TRIGGER = 9


class ConditionMode(IntEnum):
    """Transition condition modes."""

    IF = 1  # Bool/Trigger is true
    IF_NOT = 2  # Bool is false
    GREATER = 3  # Float > threshold
    LESS = 4  # Float < threshold
    EQUALS = 5  # Int == threshold
    NOT_EQUAL = 6  # Int != threshold


class BlendingMode(IntEnum):
    """Layer blending modes."""

    OVERRIDE = 0
    ADDITIVE = 1


# Parameter type names for display
PARAMETER_TYPE_NAMES = {
    ParameterType.FLOAT: "Float",
    ParameterType.INT: "Int",
    ParameterType.BOOL: "Bool",
    ParameterType.TRIGGER: "Trigger",
}

# Condition mode names for display
CONDITION_MODE_NAMES = {
    ConditionMode.IF: "If",
    ConditionMode.IF_NOT: "IfNot",
    ConditionMode.GREATER: ">",
    ConditionMode.LESS: "<",
    ConditionMode.EQUALS: "==",
    ConditionMode.NOT_EQUAL: "!=",
}


@dataclass
class AnimatorParameter:
    """Represents an animator parameter."""

    name: str = ""
    type: ParameterType = ParameterType.FLOAT
    default_float: float = 0.0
    default_int: int = 0
    default_bool: bool = False

    @property
    def type_name(self) -> str:
        """Get human-readable type name."""
        return PARAMETER_TYPE_NAMES.get(self.type, f"Unknown({self.type})")

    @property
    def default_value(self) -> float | int | bool:
        """Get the appropriate default value for this parameter type."""
        if self.type == ParameterType.FLOAT:
            return self.default_float
        elif self.type == ParameterType.INT:
            return self.default_int
        elif self.type in (ParameterType.BOOL, ParameterType.TRIGGER):
            return self.default_bool
        return 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnimatorParameter:
        """Create from Unity YAML parameter dict."""
        return cls(
            name=data.get("m_Name", ""),
            type=ParameterType(data.get("m_Type", 1)),
            default_float=float(data.get("m_DefaultFloat", 0)),
            default_int=int(data.get("m_DefaultInt", 0)),
            default_bool=bool(data.get("m_DefaultBool", 0)),
        )

    def to_dict(self, controller_file_id: int) -> dict[str, Any]:
        """Convert to Unity YAML parameter dict format."""
        return {
            "m_Name": self.name,
            "m_Type": int(self.type),
            "m_DefaultFloat": self.default_float,
            "m_DefaultInt": self.default_int,
            "m_DefaultBool": 1 if self.default_bool else 0,
            "m_Controller": {"fileID": controller_file_id},
        }


@dataclass
class AnimatorCondition:
    """Represents a transition condition."""

    mode: ConditionMode = ConditionMode.IF
    parameter: str = ""
    threshold: float = 0.0

    @property
    def mode_name(self) -> str:
        """Get human-readable condition mode."""
        return CONDITION_MODE_NAMES.get(self.mode, f"Unknown({self.mode})")

    def format_condition(self) -> str:
        """Format as human-readable condition string."""
        if self.mode == ConditionMode.IF:
            return f"{self.parameter} (If)"
        elif self.mode == ConditionMode.IF_NOT:
            return f"{self.parameter} (IfNot)"
        elif self.mode == ConditionMode.GREATER:
            return f"{self.parameter} > {self.threshold}"
        elif self.mode == ConditionMode.LESS:
            return f"{self.parameter} < {self.threshold}"
        elif self.mode == ConditionMode.EQUALS:
            return f"{self.parameter} == {int(self.threshold)}"
        elif self.mode == ConditionMode.NOT_EQUAL:
            return f"{self.parameter} != {int(self.threshold)}"
        return f"{self.parameter} ? {self.threshold}"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnimatorCondition:
        """Create from Unity YAML condition dict."""
        return cls(
            mode=ConditionMode(data.get("m_ConditionMode", 1)),
            parameter=data.get("m_ConditionEvent", ""),
            threshold=float(data.get("m_EventTreshold", 0)),  # Note: Unity typo "Treshold"
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to Unity YAML condition dict format."""
        return {
            "m_ConditionMode": int(self.mode),
            "m_ConditionEvent": self.parameter,
            "m_EventTreshold": self.threshold,  # Note: Unity typo
        }

    @classmethod
    def parse_condition_string(cls, condition: str) -> AnimatorCondition:
        """Parse a condition from string format.

        Supports formats:
            "ParamName (If)" - Bool/Trigger is true
            "ParamName (IfNot)" - Bool is false
            "ParamName > 0.5" - Float greater than
            "ParamName < 0.5" - Float less than
            "ParamName == 1" - Int equals
            "ParamName != 1" - Int not equals
        """
        condition = condition.strip()

        # Check for (If) or (IfNot)
        if condition.endswith("(If)"):
            param = condition[:-4].strip()
            return cls(mode=ConditionMode.IF, parameter=param, threshold=0)
        elif condition.endswith("(IfNot)"):
            param = condition[:-7].strip()
            return cls(mode=ConditionMode.IF_NOT, parameter=param, threshold=0)

        # Check for comparison operators
        for op, mode in [
            (" > ", ConditionMode.GREATER),
            (" < ", ConditionMode.LESS),
            (" == ", ConditionMode.EQUALS),
            (" != ", ConditionMode.NOT_EQUAL),
        ]:
            if op in condition:
                parts = condition.split(op)
                if len(parts) == 2:
                    return cls(
                        mode=mode,
                        parameter=parts[0].strip(),
                        threshold=float(parts[1].strip()),
                    )

        # Default to IF
        return cls(mode=ConditionMode.IF, parameter=condition, threshold=0)


@dataclass
class AnimatorStateTransition:
    """Represents a transition between states."""

    file_id: int = 0
    name: str = ""
    conditions: list[AnimatorCondition] = field(default_factory=list)
    destination_state_id: int = 0  # fileID of destination state
    destination_machine_id: int = 0  # fileID of destination sub-state machine
    is_exit: bool = False
    solo: bool = False
    mute: bool = False
    transition_duration: float = 0.25
    transition_offset: float = 0.0
    exit_time: float = 0.0
    has_exit_time: bool = False
    has_fixed_duration: bool = True
    interruption_source: int = 0
    ordered_interruption: bool = True
    can_transition_to_self: bool = False
    # Runtime resolved references
    destination_state_name: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any], file_id: int = 0) -> AnimatorStateTransition:
        """Create from Unity YAML transition dict."""
        content = data.get("AnimatorStateTransition", data)

        # Parse conditions
        conditions = []
        for cond_data in content.get("m_Conditions", []):
            conditions.append(AnimatorCondition.from_dict(cond_data))

        # Get destination references
        dst_state = content.get("m_DstState", {})
        dst_machine = content.get("m_DstStateMachine", {})

        return cls(
            file_id=file_id,
            name=content.get("m_Name", ""),
            conditions=conditions,
            destination_state_id=dst_state.get("fileID", 0) if isinstance(dst_state, dict) else 0,
            destination_machine_id=dst_machine.get("fileID", 0) if isinstance(dst_machine, dict) else 0,
            is_exit=bool(content.get("m_IsExit", 0)),
            solo=bool(content.get("m_Solo", 0)),
            mute=bool(content.get("m_Mute", 0)),
            transition_duration=float(content.get("m_TransitionDuration", 0.25)),
            transition_offset=float(content.get("m_TransitionOffset", 0)),
            exit_time=float(content.get("m_ExitTime", 0)),
            has_exit_time=bool(content.get("m_HasExitTime", 0)),
            has_fixed_duration=bool(content.get("m_HasFixedDuration", 1)),
            interruption_source=int(content.get("m_InterruptionSource", 0)),
            ordered_interruption=bool(content.get("m_OrderedInterruption", 1)),
            can_transition_to_self=bool(content.get("m_CanTransitionToSelf", 0)),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to Unity YAML transition dict format."""
        return {
            "m_ObjectHideFlags": 1,
            "m_Name": self.name,
            "m_Conditions": [c.to_dict() for c in self.conditions],
            "m_DstStateMachine": {"fileID": self.destination_machine_id},
            "m_DstState": {"fileID": self.destination_state_id},
            "m_Solo": 1 if self.solo else 0,
            "m_Mute": 1 if self.mute else 0,
            "m_IsExit": 1 if self.is_exit else 0,
            "serializedVersion": 3,
            "m_TransitionDuration": self.transition_duration,
            "m_TransitionOffset": self.transition_offset,
            "m_ExitTime": self.exit_time,
            "m_HasExitTime": 1 if self.has_exit_time else 0,
            "m_HasFixedDuration": 1 if self.has_fixed_duration else 0,
            "m_InterruptionSource": self.interruption_source,
            "m_OrderedInterruption": 1 if self.ordered_interruption else 0,
            "m_CanTransitionToSelf": 1 if self.can_transition_to_self else 0,
        }


@dataclass
class AnimatorState:
    """Represents an animator state."""

    file_id: int = 0
    name: str = ""
    speed: float = 1.0
    cycle_offset: float = 0.0
    transitions: list[AnimatorStateTransition] = field(default_factory=list)
    transition_ids: list[int] = field(default_factory=list)  # Raw fileIDs before resolution
    write_default_values: bool = True
    mirror: bool = False
    speed_parameter_active: bool = False
    mirror_parameter_active: bool = False
    cycle_offset_parameter_active: bool = False
    time_parameter_active: bool = False
    motion_file_id: int = 0
    motion_guid: str = ""
    motion_name: str = ""  # Resolved at runtime
    tag: str = ""
    speed_parameter: str = ""
    mirror_parameter: str = ""
    cycle_offset_parameter: str = ""
    time_parameter: str = ""
    position: tuple[float, float, float] = (0, 0, 0)  # Editor position

    @classmethod
    def from_dict(cls, data: dict[str, Any], file_id: int = 0) -> AnimatorState:
        """Create from Unity YAML state dict."""
        content = data.get("AnimatorState", data)

        # Get motion reference
        motion = content.get("m_Motion", {})
        motion_file_id = motion.get("fileID", 0) if isinstance(motion, dict) else 0
        motion_guid = motion.get("guid", "") if isinstance(motion, dict) else ""

        # Get transition references
        transition_ids = []
        for trans_ref in content.get("m_Transitions", []):
            if isinstance(trans_ref, dict):
                trans_id = trans_ref.get("fileID", 0)
                if trans_id:
                    transition_ids.append(trans_id)

        # Get position
        pos = content.get("m_Position", {})
        position = (
            (
                float(pos.get("x", 0)),
                float(pos.get("y", 0)),
                float(pos.get("z", 0)),
            )
            if isinstance(pos, dict)
            else (0, 0, 0)
        )

        return cls(
            file_id=file_id,
            name=content.get("m_Name", ""),
            speed=float(content.get("m_Speed", 1)),
            cycle_offset=float(content.get("m_CycleOffset", 0)),
            transition_ids=transition_ids,
            write_default_values=bool(content.get("m_WriteDefaultValues", 1)),
            mirror=bool(content.get("m_Mirror", 0)),
            speed_parameter_active=bool(content.get("m_SpeedParameterActive", 0)),
            mirror_parameter_active=bool(content.get("m_MirrorParameterActive", 0)),
            cycle_offset_parameter_active=bool(content.get("m_CycleOffsetParameterActive", 0)),
            time_parameter_active=bool(content.get("m_TimeParameterActive", 0)),
            motion_file_id=motion_file_id,
            motion_guid=motion_guid,
            tag=content.get("m_Tag", ""),
            speed_parameter=content.get("m_SpeedParameter", ""),
            mirror_parameter=content.get("m_MirrorParameter", ""),
            cycle_offset_parameter=content.get("m_CycleOffsetParameter", ""),
            time_parameter=content.get("m_TimeParameter", ""),
            position=position,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to Unity YAML state dict format."""
        motion_ref: dict[str, Any] = {"fileID": self.motion_file_id}
        if self.motion_guid:
            motion_ref["guid"] = self.motion_guid
            motion_ref["type"] = 2

        return {
            "serializedVersion": 6,
            "m_ObjectHideFlags": 1,
            "m_Name": self.name,
            "m_Speed": self.speed,
            "m_CycleOffset": self.cycle_offset,
            "m_Transitions": [{"fileID": tid} for tid in self.transition_ids],
            "m_StateMachineBehaviours": [],
            "m_Position": {"x": self.position[0], "y": self.position[1], "z": self.position[2]},
            "m_IKOnFeet": 0,
            "m_WriteDefaultValues": 1 if self.write_default_values else 0,
            "m_Mirror": 1 if self.mirror else 0,
            "m_SpeedParameterActive": 1 if self.speed_parameter_active else 0,
            "m_MirrorParameterActive": 1 if self.mirror_parameter_active else 0,
            "m_CycleOffsetParameterActive": 1 if self.cycle_offset_parameter_active else 0,
            "m_TimeParameterActive": 1 if self.time_parameter_active else 0,
            "m_Motion": motion_ref,
            "m_Tag": self.tag,
            "m_SpeedParameter": self.speed_parameter,
            "m_MirrorParameter": self.mirror_parameter,
            "m_CycleOffsetParameter": self.cycle_offset_parameter,
            "m_TimeParameter": self.time_parameter,
        }


@dataclass
class AnimatorStateMachine:
    """Represents an animator state machine (layer or sub-state machine)."""

    file_id: int = 0
    name: str = ""
    states: list[AnimatorState] = field(default_factory=list)
    child_state_ids: list[int] = field(default_factory=list)  # Raw fileIDs
    child_machines: list[AnimatorStateMachine] = field(default_factory=list)
    child_machine_ids: list[int] = field(default_factory=list)  # Raw fileIDs
    any_state_transitions: list[AnimatorStateTransition] = field(default_factory=list)
    any_state_transition_ids: list[int] = field(default_factory=list)
    default_state_id: int = 0
    default_state: AnimatorState | None = None
    # Editor positions
    any_state_position: tuple[float, float, float] = (50, 20, 0)
    entry_position: tuple[float, float, float] = (50, 120, 0)
    exit_position: tuple[float, float, float] = (800, 120, 0)

    @classmethod
    def from_dict(cls, data: dict[str, Any], file_id: int = 0) -> AnimatorStateMachine:
        """Create from Unity YAML state machine dict."""
        content = data.get("AnimatorStateMachine", data)

        # Parse child state references
        child_state_ids = []
        for child in content.get("m_ChildStates", []):
            state_ref = child.get("m_State", {})
            if isinstance(state_ref, dict):
                state_id = state_ref.get("fileID", 0)
                if state_id:
                    child_state_ids.append(state_id)

        # Parse child machine references
        child_machine_ids = []
        for child in content.get("m_ChildStateMachines", []):
            machine_ref = child.get("m_StateMachine", {})
            if isinstance(machine_ref, dict):
                machine_id = machine_ref.get("fileID", 0)
                if machine_id:
                    child_machine_ids.append(machine_id)

        # Parse any state transition references
        any_state_transition_ids = []
        for trans_ref in content.get("m_AnyStateTransitions", []):
            if isinstance(trans_ref, dict):
                trans_id = trans_ref.get("fileID", 0)
                if trans_id:
                    any_state_transition_ids.append(trans_id)

        # Get default state
        default_state_ref = content.get("m_DefaultState", {})
        default_state_id = default_state_ref.get("fileID", 0) if isinstance(default_state_ref, dict) else 0

        # Get positions
        def get_pos(data: dict) -> tuple[float, float, float]:
            return (float(data.get("x", 0)), float(data.get("y", 0)), float(data.get("z", 0)))

        any_pos = content.get("m_AnyStatePosition", {})
        entry_pos = content.get("m_EntryPosition", {})
        exit_pos = content.get("m_ExitPosition", {})

        return cls(
            file_id=file_id,
            name=content.get("m_Name", ""),
            child_state_ids=child_state_ids,
            child_machine_ids=child_machine_ids,
            any_state_transition_ids=any_state_transition_ids,
            default_state_id=default_state_id,
            any_state_position=get_pos(any_pos) if isinstance(any_pos, dict) else (50, 20, 0),
            entry_position=get_pos(entry_pos) if isinstance(entry_pos, dict) else (50, 120, 0),
            exit_position=get_pos(exit_pos) if isinstance(exit_pos, dict) else (800, 120, 0),
        )


@dataclass
class AnimatorLayer:
    """Represents an animator layer."""

    name: str = ""
    state_machine: AnimatorStateMachine | None = None
    state_machine_id: int = 0
    blending_mode: BlendingMode = BlendingMode.OVERRIDE
    default_weight: float = 1.0
    synced_layer_index: int = -1
    ik_pass: bool = False

    @property
    def blending_mode_name(self) -> str:
        """Get human-readable blending mode name."""
        return "Override" if self.blending_mode == BlendingMode.OVERRIDE else "Additive"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnimatorLayer:
        """Create from Unity YAML layer dict."""
        # Get state machine reference
        machine_ref = data.get("m_StateMachine", {})
        machine_id = machine_ref.get("fileID", 0) if isinstance(machine_ref, dict) else 0

        return cls(
            name=data.get("m_Name", ""),
            state_machine_id=machine_id,
            blending_mode=BlendingMode(data.get("m_BlendingMode", 0)),
            default_weight=float(data.get("m_DefaultWeight", 1)),
            synced_layer_index=int(data.get("m_SyncedLayerIndex", -1)),
            ik_pass=bool(data.get("m_IKPass", 0)),
        )


@dataclass
class AnimatorController:
    """Represents a complete Unity AnimatorController (.controller file).

    This is the top-level structure containing layers, parameters, and state machines.
    """

    file_id: int = 9100000  # Standard AnimatorController fileID
    name: str = ""
    parameters: list[AnimatorParameter] = field(default_factory=list)
    layers: list[AnimatorLayer] = field(default_factory=list)
    # Internal storage for all objects in the file
    _states: dict[int, AnimatorState] = field(default_factory=dict, repr=False)
    _transitions: dict[int, AnimatorStateTransition] = field(default_factory=dict, repr=False)
    _state_machines: dict[int, AnimatorStateMachine] = field(default_factory=dict, repr=False)
    _raw_objects: list[dict[str, Any]] = field(default_factory=list, repr=False)

    def get_state(self, file_id: int) -> AnimatorState | None:
        """Get a state by fileID."""
        return self._states.get(file_id)

    def get_transition(self, file_id: int) -> AnimatorStateTransition | None:
        """Get a transition by fileID."""
        return self._transitions.get(file_id)

    def get_state_machine(self, file_id: int) -> AnimatorStateMachine | None:
        """Get a state machine by fileID."""
        return self._state_machines.get(file_id)

    def find_parameter(self, name: str) -> AnimatorParameter | None:
        """Find a parameter by name."""
        for param in self.parameters:
            if param.name == name:
                return param
        return None

    def find_layer(self, name: str) -> AnimatorLayer | None:
        """Find a layer by name."""
        for layer in self.layers:
            if layer.name == name:
                return layer
        return None

    def find_state_in_layer(self, layer_name: str, state_name: str) -> AnimatorState | None:
        """Find a state by layer and state name."""
        layer = self.find_layer(layer_name)
        if layer and layer.state_machine:
            for state in layer.state_machine.states:
                if state.name == state_name:
                    return state
        return None

    def get_all_states(self) -> list[AnimatorState]:
        """Get all states across all layers."""
        return list(self._states.values())

    def get_all_transitions(self) -> list[AnimatorStateTransition]:
        """Get all transitions across all layers."""
        return list(self._transitions.values())

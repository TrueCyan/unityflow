"""Animator module for Unity AnimatorController (.controller) file support.

This module provides tools for reading, querying, and modifying Unity AnimatorController files.
"""

from unityflow.animator.models import (
    AnimatorCondition,
    AnimatorController,
    AnimatorLayer,
    AnimatorParameter,
    AnimatorState,
    AnimatorStateMachine,
    AnimatorStateTransition,
    BlendingMode,
    ConditionMode,
    ParameterType,
)
from unityflow.animator.parser import parse_animator_controller
from unityflow.animator.query import (
    get_any_state_transitions,
    get_layer_by_name,
    get_parameter_by_name,
    get_state_by_name,
    get_state_transitions,
    list_layers,
    list_parameters,
    list_states,
)
from unityflow.animator.writer import write_animator_controller

__all__ = [
    # Models
    "AnimatorCondition",
    "AnimatorController",
    "AnimatorLayer",
    "AnimatorParameter",
    "AnimatorState",
    "AnimatorStateMachine",
    "AnimatorStateTransition",
    "BlendingMode",
    "ConditionMode",
    "ParameterType",
    # Parser
    "parse_animator_controller",
    # Writer
    "write_animator_controller",
    # Query
    "get_any_state_transitions",
    "get_layer_by_name",
    "get_parameter_by_name",
    "get_state_by_name",
    "get_state_transitions",
    "list_layers",
    "list_parameters",
    "list_states",
]

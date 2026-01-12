"""CLI commands for Unity animator controller (.controller) files.

Provides commands for querying and modifying AnimatorController files.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from unityflow.animator.models import (
    PARAMETER_TYPE_NAMES,
    AnimatorParameter,
    ParameterType,
)
from unityflow.animator.parser import parse_animator_controller, parse_animator_controller_info
from unityflow.animator.query import (
    get_any_state_transitions,
    get_parameter_by_name,
    get_state_by_name,
    get_state_transitions,
    list_layers,
    list_parameters,
    list_states,
    state_to_dict,
)
from unityflow.animator.writer import (
    update_controller_parameters,
    update_state_properties,
    write_animator_controller,
)


@click.group(name="ctrl")
def ctrl_group() -> None:
    """Commands for Unity animator controller (.controller) files.

    Provides tools to query and modify AnimatorController files including:
    - Viewing controller structure (layers, states, parameters)
    - Inspecting state transitions and conditions
    - Modifying state and parameter properties

    Examples:

        # View controller information
        unityflow ctrl info Player.controller

        # List states in a layer
        unityflow ctrl states Player.controller --layer "Base Layer"

        # View transitions from a state
        unityflow ctrl transitions Player.controller --state "Idle"
    """
    pass


@ctrl_group.command(name="info")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
def info_cmd(file: Path, output_format: str) -> None:
    """Show animator controller information.

    Examples:

        unityflow ctrl info Player.controller
        unityflow ctrl info Player.controller --format json
    """
    try:
        info = parse_animator_controller_info(file)
    except Exception as e:
        click.echo(f"Error: Failed to load controller: {e}", err=True)
        sys.exit(1)

    if output_format == "json":
        click.echo(json.dumps(info, indent=2))
    else:
        click.echo(f"Name: {info['name']}")
        click.echo(f"Layers: {info['layer_count']}")
        click.echo(f"Parameters: {info['parameter_count']}")

        if info["parameters"]:
            click.echo("\nParameters:")
            for p in info["parameters"]:
                type_name = PARAMETER_TYPE_NAMES.get(p["type"], f"Unknown({p['type']})")
                click.echo(f"  [{info['parameters'].index(p)}] {p['name']} ({type_name})")


@ctrl_group.command(name="layers")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
def layers_cmd(file: Path, output_format: str) -> None:
    """List animator layers.

    Examples:

        unityflow ctrl layers Player.controller
    """
    try:
        controller = parse_animator_controller(file)
    except Exception as e:
        click.echo(f"Error: Failed to load controller: {e}", err=True)
        sys.exit(1)

    layers = list_layers(controller)

    if output_format == "json":
        click.echo(json.dumps([layer.to_dict() for layer in layers], indent=2))
    else:
        if not layers:
            click.echo("No layers found")
            return

        for layer in layers:
            default_str = f"  default={layer.default_state_name}" if layer.default_state_name else ""
            click.echo(
                f"[{layer.index}] {layer.name}  "
                f"weight={layer.default_weight}  "
                f"mode={layer.blending_mode}  "
                f"states={layer.state_count}{default_str}"
            )


@ctrl_group.command(name="states")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("--layer", "-l", "layer_name", type=str, help="Filter by layer name")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
def states_cmd(file: Path, layer_name: str | None, output_format: str) -> None:
    """List animator states.

    Examples:

        unityflow ctrl states Player.controller
        unityflow ctrl states Player.controller --layer "Base Layer"
    """
    try:
        controller = parse_animator_controller(file)
    except Exception as e:
        click.echo(f"Error: Failed to load controller: {e}", err=True)
        sys.exit(1)

    states = list_states(controller, layer_name=layer_name)

    if output_format == "json":
        click.echo(json.dumps([s.to_dict() for s in states], indent=2))
    else:
        if not states:
            click.echo("No states found")
            return

        # Group by layer
        current_layer = ""
        for state in states:
            if state.layer_name != current_layer:
                current_layer = state.layer_name
                click.echo(f"\nLayer: {current_layer}")

            default_marker = "  [DEFAULT]" if state.is_default else ""
            motion_str = f"  motion={state.motion_name}" if state.motion_name else ""
            click.echo(f"  {state.name}  speed={state.speed}{motion_str}{default_marker}")


@ctrl_group.command(name="transitions")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("--state", "-s", "state_name", type=str, help="Source state name")
@click.option("--any-state", is_flag=True, help="Show Any State transitions")
@click.option("--layer", "-l", "layer_name", type=str, help="Layer name (for --any-state)")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
def transitions_cmd(
    file: Path,
    state_name: str | None,
    any_state: bool,
    layer_name: str | None,
    output_format: str,
) -> None:
    """List state transitions.

    Examples:

        unityflow ctrl transitions Player.controller --state "Idle"
        unityflow ctrl transitions Player.controller --any-state --layer "Base Layer"
    """
    if not state_name and not any_state:
        click.echo("Error: Specify --state or --any-state", err=True)
        sys.exit(1)

    try:
        controller = parse_animator_controller(file)
    except Exception as e:
        click.echo(f"Error: Failed to load controller: {e}", err=True)
        sys.exit(1)

    if any_state:
        transitions = get_any_state_transitions(controller, layer_name)
        source = f"Any State ({layer_name or 'all layers'})"
    else:
        transitions = get_state_transitions(controller, state_name, layer_name)
        source = state_name

    if output_format == "json":
        click.echo(json.dumps([t.to_dict() for t in transitions], indent=2))
    else:
        if not transitions:
            click.echo(f"No transitions from {source}")
            return

        click.echo(f"From: {source}")
        for trans in transitions:
            cond_str = ", ".join(trans.conditions) if trans.conditions else "(none - has exit time)"
            click.echo(f"  -> {trans.destination_name}")
            click.echo(f"     Conditions: {cond_str}")
            exit_str = f"{trans.exit_time:.2f}" if trans.has_exit_time else "-"
            click.echo(f"     Duration: {trans.duration}s  ExitTime: {exit_str}  Offset: {trans.exit_time}")


@ctrl_group.command(name="params")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
def params_cmd(file: Path, output_format: str) -> None:
    """List animator parameters.

    Examples:

        unityflow ctrl params Player.controller
    """
    try:
        controller = parse_animator_controller(file)
    except Exception as e:
        click.echo(f"Error: Failed to load controller: {e}", err=True)
        sys.exit(1)

    params = list_parameters(controller)

    if output_format == "json":
        click.echo(json.dumps(params, indent=2))
    else:
        if not params:
            click.echo("No parameters found")
            return

        for p in params:
            default_str = ""
            if p["type"] in ("Float", "Int"):
                default_str = f" = {p['default']}"
            elif p["type"] == "Bool":
                default_str = f" = {'true' if p['default'] else 'false'}"
            click.echo(f"[{p['index']}] {p['name']} ({p['type']}){default_str}")


@ctrl_group.command(name="get-state")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("--state", "-s", "state_name", type=str, required=True, help="State name")
@click.option("--layer", "-l", "layer_name", type=str, help="Layer name")
def get_state_cmd(file: Path, state_name: str, layer_name: str | None) -> None:
    """Get detailed state information.

    Examples:

        unityflow ctrl get-state Player.controller --state "Idle"
    """
    try:
        controller = parse_animator_controller(file)
    except Exception as e:
        click.echo(f"Error: Failed to load controller: {e}", err=True)
        sys.exit(1)

    state = get_state_by_name(controller, state_name, layer_name)
    if not state:
        click.echo(f"Error: State '{state_name}' not found", err=True)
        sys.exit(1)

    data = state_to_dict(state)
    click.echo(json.dumps(data, indent=2))


@ctrl_group.command(name="set-state")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("--state", "-s", "state_name", type=str, required=True, help="State name")
@click.option("--layer", "-l", "layer_name", type=str, help="Layer name")
@click.option("--speed", type=float, help="Set playback speed")
@click.option("--motion", type=str, help="Set motion asset path (@Assets/...)")
@click.option("-o", "--output", type=click.Path(path_type=Path), help="Output file")
def set_state_cmd(
    file: Path,
    state_name: str,
    layer_name: str | None,
    speed: float | None,
    motion: str | None,
    output: Path | None,
) -> None:
    """Modify state properties.

    Examples:

        unityflow ctrl set-state Player.controller --state "Run" --speed 1.5
        unityflow ctrl set-state Player.controller --state "Idle" --motion "@Assets/Anim/NewIdle.anim"
    """
    try:
        controller = parse_animator_controller(file)
    except Exception as e:
        click.echo(f"Error: Failed to load controller: {e}", err=True)
        sys.exit(1)

    state = get_state_by_name(controller, state_name, layer_name)
    if not state:
        click.echo(f"Error: State '{state_name}' not found", err=True)
        sys.exit(1)

    # Prepare updates
    updates = {}
    if speed is not None:
        updates["speed"] = speed
    if motion is not None:
        # Resolve motion asset path
        if motion.startswith("@"):
            from unityflow.asset_resolver import resolve_asset_reference
            from unityflow.asset_tracker import find_unity_project_root

            project_root = find_unity_project_root(file)
            if project_root:
                try:
                    ref = resolve_asset_reference(motion, project_root)
                    if ref:
                        updates["motion_guid"] = ref.guid
                except Exception as e:
                    click.echo(f"Error: Failed to resolve asset: {e}", err=True)
                    sys.exit(1)
            else:
                click.echo("Error: Could not find Unity project root", err=True)
                sys.exit(1)

    if not updates:
        click.echo("Error: No changes specified", err=True)
        sys.exit(1)

    # Apply updates
    if not update_state_properties(controller, state.file_id, **updates):
        click.echo("Error: Failed to update state", err=True)
        sys.exit(1)

    output_path = output or file
    write_animator_controller(controller, output_path)
    click.echo(f"Updated state '{state_name}'")
    if output:
        click.echo(f"Saved to: {output}")


@ctrl_group.command(name="add-param")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("--name", "-n", "param_name", type=str, required=True, help="Parameter name")
@click.option("--type", "-t", "param_type", type=click.Choice(["float", "int", "bool", "trigger"]), required=True)
@click.option("--default", "default_value", type=str, help="Default value")
@click.option("-o", "--output", type=click.Path(path_type=Path), help="Output file")
def add_param_cmd(
    file: Path,
    param_name: str,
    param_type: str,
    default_value: str | None,
    output: Path | None,
) -> None:
    """Add an animator parameter.

    Examples:

        unityflow ctrl add-param Player.controller --name "Speed" --type float --default 0
        unityflow ctrl add-param Player.controller --name "Jump" --type trigger
    """
    try:
        controller = parse_animator_controller(file)
    except Exception as e:
        click.echo(f"Error: Failed to load controller: {e}", err=True)
        sys.exit(1)

    # Check if parameter already exists
    if get_parameter_by_name(controller, param_name):
        click.echo(f"Error: Parameter '{param_name}' already exists", err=True)
        sys.exit(1)

    # Create parameter
    type_map = {
        "float": ParameterType.FLOAT,
        "int": ParameterType.INT,
        "bool": ParameterType.BOOL,
        "trigger": ParameterType.TRIGGER,
    }

    param = AnimatorParameter(
        name=param_name,
        type=type_map[param_type],
    )

    # Set default value
    if default_value is not None:
        if param_type == "float":
            param.default_float = float(default_value)
        elif param_type == "int":
            param.default_int = int(default_value)
        elif param_type == "bool":
            param.default_bool = default_value.lower() in ("true", "1", "yes")

    controller.parameters.append(param)
    update_controller_parameters(controller)

    output_path = output or file
    write_animator_controller(controller, output_path)
    click.echo(f"Added parameter '{param_name}' ({param_type})")
    if output:
        click.echo(f"Saved to: {output}")


@ctrl_group.command(name="set-param")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("--name", "-n", "param_name", type=str, required=True, help="Parameter name")
@click.option("--default", "default_value", type=str, required=True, help="Default value")
@click.option("-o", "--output", type=click.Path(path_type=Path), help="Output file")
def set_param_cmd(
    file: Path,
    param_name: str,
    default_value: str,
    output: Path | None,
) -> None:
    """Modify parameter default value.

    Examples:

        unityflow ctrl set-param Player.controller --name "Speed" --default 1.5
    """
    try:
        controller = parse_animator_controller(file)
    except Exception as e:
        click.echo(f"Error: Failed to load controller: {e}", err=True)
        sys.exit(1)

    param = get_parameter_by_name(controller, param_name)
    if not param:
        click.echo(f"Error: Parameter '{param_name}' not found", err=True)
        sys.exit(1)

    # Update default value
    if param.type == ParameterType.FLOAT:
        param.default_float = float(default_value)
    elif param.type == ParameterType.INT:
        param.default_int = int(default_value)
    elif param.type in (ParameterType.BOOL, ParameterType.TRIGGER):
        param.default_bool = default_value.lower() in ("true", "1", "yes")

    update_controller_parameters(controller)

    output_path = output or file
    write_animator_controller(controller, output_path)
    click.echo(f"Updated parameter '{param_name}'")
    if output:
        click.echo(f"Saved to: {output}")


@ctrl_group.command(name="del-param")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("--name", "-n", "param_name", type=str, required=True, help="Parameter name")
@click.option("-o", "--output", type=click.Path(path_type=Path), help="Output file")
def del_param_cmd(
    file: Path,
    param_name: str,
    output: Path | None,
) -> None:
    """Delete an animator parameter.

    Examples:

        unityflow ctrl del-param Player.controller --name "OldParam"
    """
    try:
        controller = parse_animator_controller(file)
    except Exception as e:
        click.echo(f"Error: Failed to load controller: {e}", err=True)
        sys.exit(1)

    # Find and remove parameter
    for i, param in enumerate(controller.parameters):
        if param.name == param_name:
            controller.parameters.pop(i)
            update_controller_parameters(controller)

            output_path = output or file
            write_animator_controller(controller, output_path)
            click.echo(f"Deleted parameter '{param_name}'")
            if output:
                click.echo(f"Saved to: {output}")
            return

    click.echo(f"Error: Parameter '{param_name}' not found", err=True)
    sys.exit(1)

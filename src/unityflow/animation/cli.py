"""CLI commands for Unity animation files (.anim).

Provides commands for querying and modifying AnimationClip files.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

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
    get_curve,
    get_curve_by_index,
    get_keyframe,
    get_keyframes,
    keyframe_to_dict,
    list_curves,
)
from unityflow.animation.writer import create_empty_animation_clip, write_animation_clip


@click.group(name="anim")
def anim_group() -> None:
    """Commands for Unity animation clip (.anim) files.

    Provides tools to query and modify AnimationClip files including:
    - Viewing clip metadata and structure
    - Listing and inspecting animation curves
    - Modifying keyframe values
    - Adding/removing curves and keyframes

    Examples:

        # View clip information
        unityflow anim info Character_idle.anim

        # List all curves
        unityflow anim curves Character_idle.anim

        # View keyframes for a specific curve
        unityflow anim keyframes Character_idle.anim --index 0
    """
    pass


@anim_group.command(name="create")
@click.argument("file", type=click.Path(path_type=Path))
@click.option("--name", type=str, help="Clip name (defaults to filename)")
@click.option("--duration", type=float, default=1.0, help="Clip duration in seconds")
@click.option("--loop", is_flag=True, help="Enable looping")
@click.option("--sample-rate", type=float, default=60.0, help="Sample rate in Hz")
def create_cmd(
    file: Path,
    name: str | None,
    duration: float,
    loop: bool,
    sample_rate: float,
) -> None:
    """Create a new empty animation clip.

    Examples:

        unityflow anim create NewClip.anim --name "NewClip" --duration 2.0 --loop
    """
    if file.exists():
        click.echo(f"Error: File already exists: {file}", err=True)
        sys.exit(1)

    clip_name = name or file.stem
    clip = create_empty_animation_clip(
        name=clip_name,
        duration=duration,
        loop=loop,
        sample_rate=sample_rate,
    )

    write_animation_clip(clip, file)
    click.echo(f"Created: {file}")
    click.echo(f"Duration: {duration}s")
    click.echo(f"Loop: {'Yes' if loop else 'No'}")


@anim_group.command(name="info")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
def info_cmd(file: Path, output_format: str) -> None:
    """Show animation clip information.

    Examples:

        unityflow anim info Character_idle.anim
        unityflow anim info Character_idle.anim --format json
    """
    try:
        clip = parse_animation_clip(file)
    except Exception as e:
        click.echo(f"Error: Failed to load animation: {e}", err=True)
        sys.exit(1)

    counts = clip.get_curve_counts()
    total_curves = sum(counts.values())

    if output_format == "json":
        data = {
            "name": clip.name,
            "duration": clip.duration,
            "sample_rate": clip.sample_rate,
            "loop": clip.loop,
            "legacy": clip.legacy,
            "wrap_mode": clip.wrap_mode,
            "curve_counts": counts,
            "total_curves": total_curves,
            "event_count": len(clip.events),
        }
        click.echo(json.dumps(data, indent=2))
    else:
        click.echo(f"Name: {clip.name}")
        click.echo(f"Duration: {clip.duration:.2f}s")
        click.echo(f"Sample Rate: {clip.sample_rate} Hz")
        click.echo(f"Loop: {'Yes' if clip.loop else 'No'}")
        click.echo(f"Legacy: {'Yes' if clip.legacy else 'No'}")

        # Curve summary
        curve_parts = []
        if counts["position"]:
            curve_parts.append(f"{counts['position']} position")
        if counts["euler"]:
            curve_parts.append(f"{counts['euler']} rotation")
        if counts["scale"]:
            curve_parts.append(f"{counts['scale']} scale")
        if counts["float"]:
            curve_parts.append(f"{counts['float']} float")
        if counts["pptr"]:
            curve_parts.append(f"{counts['pptr']} pptr")

        click.echo(f"Curves: {total_curves} ({', '.join(curve_parts) if curve_parts else 'none'})")
        click.echo(f"Events: {len(clip.events)}")


@anim_group.command(name="curves")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("--type", "curve_type", type=click.Choice(["position", "euler", "scale", "float", "pptr"]))
@click.option("--path", "filter_path", type=str, help="Filter by path prefix")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
def curves_cmd(file: Path, curve_type: str | None, filter_path: str | None, output_format: str) -> None:
    """List animation curves in a clip.

    Examples:

        unityflow anim curves Character_idle.anim
        unityflow anim curves Character_idle.anim --type float
        unityflow anim curves Character_idle.anim --path "Root/role"
    """
    try:
        clip = parse_animation_clip(file)
    except Exception as e:
        click.echo(f"Error: Failed to load animation: {e}", err=True)
        sys.exit(1)

    curves = list_curves(clip, curve_type=curve_type, path=filter_path)

    if output_format == "json":
        click.echo(json.dumps([c.to_dict() for c in curves], indent=2))
    else:
        if not curves:
            click.echo("No curves found")
            return

        for info in curves:
            attr_str = f"  {info.attribute}" if info.attribute else ""
            path_display = info.path if info.path else "(root)"
            click.echo(f"[{info.index}] {info.curve_type:8} {path_display}{attr_str}  ({info.key_count} keys)")


@anim_group.command(name="keyframes")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("--index", "-i", "curve_index", type=int, help="Curve index")
@click.option("--path", "-p", type=str, help="Target path")
@click.option("--attr", "-a", "attribute", type=str, help="Target attribute")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
def keyframes_cmd(
    file: Path,
    curve_index: int | None,
    path: str | None,
    attribute: str | None,
    output_format: str,
) -> None:
    """List keyframes in a curve.

    Specify curve by index or by path/attribute.

    Examples:

        unityflow anim keyframes Character_idle.anim --index 0
        unityflow anim keyframes Character_idle.anim --path "Root/character" --attr position
    """
    try:
        clip = parse_animation_clip(file)
    except Exception as e:
        click.echo(f"Error: Failed to load animation: {e}", err=True)
        sys.exit(1)

    # Find the curve
    curve = None
    if curve_index is not None:
        curve = get_curve_by_index(clip, curve_index)
        if curve is None:
            click.echo(f"Error: Curve index {curve_index} out of range (0-{len(clip.curves) - 1})", err=True)
            sys.exit(1)
    elif path is not None:
        curve = get_curve(clip, path, attribute)
        if curve is None:
            click.echo(f"Error: Curve not found at path '{path}' attr '{attribute}'", err=True)
            sys.exit(1)
    else:
        click.echo("Error: Specify --index or --path", err=True)
        sys.exit(1)

    keyframes = get_keyframes(curve)

    if output_format == "json":
        data = [keyframe_to_dict(kf, curve.curve_type) for kf in keyframes]
        click.echo(json.dumps(data, indent=2))
    else:
        path_display = curve.path if curve.path else "(root)"
        attr_display = f" [{curve.attribute}]" if curve.attribute else ""
        click.echo(f"Curve: {path_display}{attr_display} ({curve.curve_type})")
        click.echo(f"Keys: {len(keyframes)}")

        for i, kf in enumerate(keyframes):
            kf_data = keyframe_to_dict(kf, curve.curve_type)
            time = kf_data["time"]
            value = kf_data.get("value", kf_data)

            if isinstance(value, dict) and "x" in value:
                # Vector3
                value_str = f"({value['x']:.2f}, {value['y']:.2f}, {value['z']:.2f})"
            elif isinstance(value, dict) and "fileID" in value:
                # PPtrKeyframe
                value_str = f"fileID={kf_data.get('fileID', 0)}"
                if kf_data.get("guid"):
                    value_str += f" guid={kf_data['guid'][:8]}..."
            elif isinstance(value, int | float):
                value_str = f"{value:.4f}"
            else:
                value_str = str(value)

            # Tangent info for regular keyframes
            tangent_str = ""
            if "tangentMode" in kf_data:
                mode = kf_data["tangentMode"]
                mode_names = {0: "free", 21: "auto", 103: "constant", 136: "flat"}
                tangent_str = f"  tangent={mode_names.get(mode, f'custom({mode})')}"

            click.echo(f"[{i}] t={time:.3f}  value={value_str}{tangent_str}")


@anim_group.command(name="get-key")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("--index", "-i", "curve_index", type=int, help="Curve index")
@click.option("--path", "-p", type=str, help="Target path")
@click.option("--attr", "-a", "attribute", type=str, help="Target attribute")
@click.option("--key", "-k", "key_index", type=int, required=True, help="Keyframe index")
def get_key_cmd(
    file: Path,
    curve_index: int | None,
    path: str | None,
    attribute: str | None,
    key_index: int,
) -> None:
    """Get detailed keyframe data.

    Examples:

        unityflow anim get-key Character_idle.anim --index 0 --key 0
        unityflow anim get-key Character_idle.anim --path "Root/fx" --attr eulerAngles --key 0
    """
    try:
        clip = parse_animation_clip(file)
    except Exception as e:
        click.echo(f"Error: Failed to load animation: {e}", err=True)
        sys.exit(1)

    # Find the curve
    curve = None
    if curve_index is not None:
        curve = get_curve_by_index(clip, curve_index)
    elif path is not None:
        curve = get_curve(clip, path, attribute)
    else:
        click.echo("Error: Specify --index or --path", err=True)
        sys.exit(1)

    if curve is None:
        click.echo("Error: Curve not found", err=True)
        sys.exit(1)

    kf = get_keyframe(curve, key_index)
    if kf is None:
        click.echo(f"Error: Keyframe {key_index} not found", err=True)
        sys.exit(1)

    data = keyframe_to_dict(kf, curve.curve_type)
    click.echo(json.dumps(data, indent=2))


@anim_group.command(name="set-key")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("--index", "-i", "curve_index", type=int, help="Curve index")
@click.option("--path", "-p", type=str, help="Target path")
@click.option("--attr", "-a", "attribute", type=str, help="Target attribute")
@click.option("--key", "-k", "key_index", type=int, required=True, help="Keyframe index")
@click.option("--value", "-v", type=str, required=True, help="New value (JSON for vectors)")
@click.option("--time", "-t", "new_time", type=float, help="New time value")
@click.option("--tangent", type=click.Choice(["smooth", "linear", "constant", "flat"]))
@click.option("-o", "--output", type=click.Path(path_type=Path), help="Output file")
def set_key_cmd(
    file: Path,
    curve_index: int | None,
    path: str | None,
    attribute: str | None,
    key_index: int,
    value: str,
    new_time: float | None,
    tangent: str | None,
    output: Path | None,
) -> None:
    """Set keyframe value.

    Examples:

        # Set position value
        unityflow anim set-key Character_idle.anim \\
            --path "Root/character" --attr position --key 0 \\
            --value '{"x": 0, "y": 2.0, "z": 0}'

        # Set float value
        unityflow anim set-key Character_idle.anim \\
            --index 3 --key 0 --value 0.8 --tangent flat
    """
    try:
        clip = parse_animation_clip(file)
    except Exception as e:
        click.echo(f"Error: Failed to load animation: {e}", err=True)
        sys.exit(1)

    # Find the curve
    curve = None
    if curve_index is not None:
        curve = get_curve_by_index(clip, curve_index)
    elif path is not None:
        curve = get_curve(clip, path, attribute)
    else:
        click.echo("Error: Specify --index or --path", err=True)
        sys.exit(1)

    if curve is None:
        click.echo("Error: Curve not found", err=True)
        sys.exit(1)

    # Parse value
    try:
        parsed_value = json.loads(value)
    except json.JSONDecodeError:
        # Try as float
        try:
            parsed_value = float(value)
        except ValueError:
            click.echo(f"Error: Invalid value format: {value}", err=True)
            sys.exit(1)

    if not set_keyframe_value(curve, key_index, parsed_value, time=new_time, tangent=tangent):
        click.echo(f"Error: Keyframe {key_index} not found", err=True)
        sys.exit(1)

    output_path = output or file
    write_animation_clip(clip, output_path)
    click.echo(f"Updated keyframe {key_index}")
    if output:
        click.echo(f"Saved to: {output}")


@anim_group.command(name="add-key")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("--index", "-i", "curve_index", type=int, help="Curve index")
@click.option("--path", "-p", type=str, help="Target path")
@click.option("--attr", "-a", "attribute", type=str, help="Target attribute")
@click.option("--time", "-t", type=float, required=True, help="Keyframe time")
@click.option("--value", "-v", type=str, required=True, help="Keyframe value")
@click.option("--tangent", type=click.Choice(["smooth", "linear", "constant", "flat"]), default="smooth")
@click.option("-o", "--output", type=click.Path(path_type=Path), help="Output file")
def add_key_cmd(
    file: Path,
    curve_index: int | None,
    path: str | None,
    attribute: str | None,
    time: float,
    value: str,
    tangent: str,
    output: Path | None,
) -> None:
    """Add a new keyframe to a curve.

    Examples:

        unityflow anim add-key Character_idle.anim \\
            --path "Root/character" --attr position \\
            --time 0.5 --value '{"x": 1, "y": 1, "z": 0}' --tangent smooth
    """
    try:
        clip = parse_animation_clip(file)
    except Exception as e:
        click.echo(f"Error: Failed to load animation: {e}", err=True)
        sys.exit(1)

    # Find the curve
    curve = None
    if curve_index is not None:
        curve = get_curve_by_index(clip, curve_index)
    elif path is not None:
        curve = get_curve(clip, path, attribute)
    else:
        click.echo("Error: Specify --index or --path", err=True)
        sys.exit(1)

    if curve is None:
        click.echo("Error: Curve not found", err=True)
        sys.exit(1)

    # Parse value
    try:
        parsed_value = json.loads(value)
    except json.JSONDecodeError:
        try:
            parsed_value = float(value)
        except ValueError:
            click.echo(f"Error: Invalid value format: {value}", err=True)
            sys.exit(1)

    idx = add_keyframe(curve, time, parsed_value, tangent)

    output_path = output or file
    write_animation_clip(clip, output_path)
    click.echo(f"Added keyframe at index {idx}, time={time}")
    if output:
        click.echo(f"Saved to: {output}")


@anim_group.command(name="del-key")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("--index", "-i", "curve_index", type=int, help="Curve index")
@click.option("--path", "-p", type=str, help="Target path")
@click.option("--attr", "-a", "attribute", type=str, help="Target attribute")
@click.option("--key", "-k", "key_index", type=int, required=True, help="Keyframe index to delete")
@click.option("-o", "--output", type=click.Path(path_type=Path), help="Output file")
def del_key_cmd(
    file: Path,
    curve_index: int | None,
    path: str | None,
    attribute: str | None,
    key_index: int,
    output: Path | None,
) -> None:
    """Delete a keyframe from a curve.

    Examples:

        unityflow anim del-key Character_idle.anim --index 0 --key 2
    """
    try:
        clip = parse_animation_clip(file)
    except Exception as e:
        click.echo(f"Error: Failed to load animation: {e}", err=True)
        sys.exit(1)

    # Find the curve
    curve = None
    if curve_index is not None:
        curve = get_curve_by_index(clip, curve_index)
    elif path is not None:
        curve = get_curve(clip, path, attribute)
    else:
        click.echo("Error: Specify --index or --path", err=True)
        sys.exit(1)

    if curve is None:
        click.echo("Error: Curve not found", err=True)
        sys.exit(1)

    if not delete_keyframe(curve, key_index):
        click.echo(f"Error: Keyframe {key_index} not found", err=True)
        sys.exit(1)

    output_path = output or file
    write_animation_clip(clip, output_path)
    click.echo(f"Deleted keyframe {key_index}")
    if output:
        click.echo(f"Saved to: {output}")


@anim_group.command(name="add-curve")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("--path", "-p", type=str, required=True, help="Target GameObject path")
@click.option("--type", "curve_type", type=click.Choice(["position", "euler", "scale", "float", "pptr"]), required=True)
@click.option("--attr", "-a", "attribute", type=str, help="Property attribute (for float/pptr)")
@click.option("--component", type=str, help="Component type (e.g., SpriteRenderer)")
@click.option("--keys", type=str, help="JSON array of keyframes")
@click.option("-o", "--output", type=click.Path(path_type=Path), help="Output file")
def add_curve_cmd(
    file: Path,
    path: str,
    curve_type: str,
    attribute: str | None,
    component: str | None,
    keys: str | None,
    output: Path | None,
) -> None:
    """Add a new curve to an animation clip.

    Examples:

        # Add empty position curve
        unityflow anim add-curve Character_idle.anim \\
            --path "NewObject" --type position

        # Add float curve with keyframes
        unityflow anim add-curve Character_idle.anim \\
            --path "NewObject" --type float --attr m_Color.a --component SpriteRenderer \\
            --keys '[{"time":0,"value":0},{"time":1,"value":1}]'
    """
    try:
        clip = parse_animation_clip(file)
    except Exception as e:
        click.echo(f"Error: Failed to load animation: {e}", err=True)
        sys.exit(1)

    # Determine class_id from component
    class_id = 0
    if component:
        component_ids = {
            "transform": 4,
            "spriterenderer": 212,
            "meshrenderer": 23,
            "audiosource": 82,
            "animator": 95,
        }
        class_id = component_ids.get(component.lower(), 114)  # Default to MonoBehaviour

    # Parse keyframes
    keyframes = None
    if keys:
        try:
            keyframes = json.loads(keys)
        except json.JSONDecodeError as e:
            click.echo(f"Error: Invalid keyframes JSON: {e}", err=True)
            sys.exit(1)

    add_curve(
        clip,
        path=path,
        curve_type=curve_type,
        attribute=attribute or "",
        class_id=class_id,
        keyframes=keyframes,
    )

    output_path = output or file
    write_animation_clip(clip, output_path)
    click.echo(f"Added {curve_type} curve for '{path}'")
    if output:
        click.echo(f"Saved to: {output}")


@anim_group.command(name="del-curve")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("--index", "-i", type=int, help="Curve index to delete")
@click.option("--path", "-p", type=str, help="Target path")
@click.option("--attr", "-a", "attribute", type=str, help="Target attribute")
@click.option("-o", "--output", type=click.Path(path_type=Path), help="Output file")
def del_curve_cmd(
    file: Path,
    index: int | None,
    path: str | None,
    attribute: str | None,
    output: Path | None,
) -> None:
    """Delete a curve from an animation clip.

    Examples:

        unityflow anim del-curve Character_idle.anim --index 2
        unityflow anim del-curve Character_idle.anim --path "Root/fx" --attr scale
    """
    try:
        clip = parse_animation_clip(file)
    except Exception as e:
        click.echo(f"Error: Failed to load animation: {e}", err=True)
        sys.exit(1)

    if index is None and path is None:
        click.echo("Error: Specify --index or --path", err=True)
        sys.exit(1)

    if not delete_curve(clip, index=index, path=path, attribute=attribute):
        click.echo("Error: Curve not found", err=True)
        sys.exit(1)

    output_path = output or file
    write_animation_clip(clip, output_path)
    click.echo("Deleted curve")
    if output:
        click.echo(f"Saved to: {output}")


@anim_group.command(name="events")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
def events_cmd(file: Path, output_format: str) -> None:
    """List animation events.

    Examples:

        unityflow anim events Character_idle.anim
    """
    try:
        clip = parse_animation_clip(file)
    except Exception as e:
        click.echo(f"Error: Failed to load animation: {e}", err=True)
        sys.exit(1)

    if output_format == "json":
        data = [e.to_dict() for e in clip.events]
        click.echo(json.dumps(data, indent=2))
    else:
        if not clip.events:
            click.echo("No events")
            return

        for i, event in enumerate(clip.events):
            click.echo(f"[{i}] t={event.time:.3f} {event.function_name}({event.data})")


@anim_group.command(name="add-event")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("--time", "-t", type=float, required=True, help="Event time")
@click.option("--function", "-f", "function_name", type=str, required=True, help="Function name")
@click.option("--data", "-d", type=str, default="", help="String parameter")
@click.option("--float", "float_param", type=float, default=0.0, help="Float parameter")
@click.option("--int", "int_param", type=int, default=0, help="Int parameter")
@click.option("-o", "--output", type=click.Path(path_type=Path), help="Output file")
def add_event_cmd(
    file: Path,
    time: float,
    function_name: str,
    data: str,
    float_param: float,
    int_param: int,
    output: Path | None,
) -> None:
    """Add an animation event.

    Examples:

        unityflow anim add-event Character_idle.anim \\
            --time 0.5 --function "PlaySound" --data "click"
    """
    try:
        clip = parse_animation_clip(file)
    except Exception as e:
        click.echo(f"Error: Failed to load animation: {e}", err=True)
        sys.exit(1)

    add_event(clip, time, function_name, data, float_param, int_param)

    output_path = output or file
    write_animation_clip(clip, output_path)
    click.echo(f"Added event: {function_name} at t={time}")
    if output:
        click.echo(f"Saved to: {output}")


@anim_group.command(name="del-event")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("--index", "-i", type=int, required=True, help="Event index to delete")
@click.option("-o", "--output", type=click.Path(path_type=Path), help="Output file")
def del_event_cmd(file: Path, index: int, output: Path | None) -> None:
    """Delete an animation event.

    Examples:

        unityflow anim del-event Character_idle.anim --index 0
    """
    try:
        clip = parse_animation_clip(file)
    except Exception as e:
        click.echo(f"Error: Failed to load animation: {e}", err=True)
        sys.exit(1)

    if not delete_event(clip, index):
        click.echo(f"Error: Event {index} not found", err=True)
        sys.exit(1)

    output_path = output or file
    write_animation_clip(clip, output_path)
    click.echo(f"Deleted event {index}")
    if output:
        click.echo(f"Saved to: {output}")


@anim_group.command(name="settings")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
def settings_cmd(file: Path, output_format: str) -> None:
    """Show animation clip settings.

    Examples:

        unityflow anim settings Character_idle.anim
    """
    try:
        clip = parse_animation_clip(file)
    except Exception as e:
        click.echo(f"Error: Failed to load animation: {e}", err=True)
        sys.exit(1)

    settings = clip.settings

    if output_format == "json":
        data = settings.to_dict()
        click.echo(json.dumps(data, indent=2))
    else:
        click.echo(f"Start Time: {settings.start_time}")
        click.echo(f"Stop Time: {settings.stop_time}")
        click.echo(f"Duration: {settings.stop_time - settings.start_time:.3f}s")
        click.echo(f"Loop Time: {settings.loop_time}")
        click.echo(f"Loop Blend: {settings.loop_blend}")
        click.echo(f"Mirror: {settings.mirror}")
        click.echo(f"Cycle Offset: {settings.cycle_offset}")


@anim_group.command(name="set-settings")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("--loop/--no-loop", "loop", default=None, help="Set loop mode")
@click.option("--duration", type=float, help="Set duration (stop_time)")
@click.option("--sample-rate", type=float, help="Set sample rate")
@click.option("-o", "--output", type=click.Path(path_type=Path), help="Output file")
def set_settings_cmd(
    file: Path,
    loop: bool | None,
    duration: float | None,
    sample_rate: float | None,
    output: Path | None,
) -> None:
    """Modify animation clip settings.

    Examples:

        unityflow anim set-settings Character_idle.anim --loop --duration 2.0
    """
    try:
        clip = parse_animation_clip(file)
    except Exception as e:
        click.echo(f"Error: Failed to load animation: {e}", err=True)
        sys.exit(1)

    if loop is None and duration is None and sample_rate is None:
        click.echo("Error: No settings specified", err=True)
        sys.exit(1)

    set_clip_settings(clip, loop=loop, duration=duration, sample_rate=sample_rate)

    output_path = output or file
    write_animation_clip(clip, output_path)
    click.echo("Updated settings")
    if output:
        click.echo(f"Saved to: {output}")

import base64
import json

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.utilities.types import Image

from unityflow.bridge.unity_client import UnityBridgeError, UnityClient

mcp = FastMCP(
    "unityflow-bridge",
    description="Unity Editor Bridge - visual feedback and runtime data from the Unity Editor",
)

_client = UnityClient()


def _error_text(e):
    return f"Error: {e}"


@mcp.tool()
def capture_screenshot(view: str = "scene", width: int = 1024, height: int = 768) -> Image | str:
    """Capture a screenshot from the Unity Editor.

    Args:
        view: "scene" for Scene View or "game" for Game View camera
        width: Image width in pixels (64-4096)
        height: Image height in pixels (64-4096)

    Returns:
        PNG image of the current view
    """
    try:
        png_data = _client.screenshot(view=view, width=width, height=height)
        return Image(data=base64.b64encode(png_data).decode(), media_type="image/png")
    except UnityBridgeError as e:
        return _error_text(e)


@mcp.tool()
def capture_prefab_preview(prefab_path: str, width: int = 512, height: int = 512, mode: str = "render") -> Image | str:
    """Render a preview of a Unity prefab.

    Args:
        prefab_path: Asset path of the prefab (e.g. "Assets/Prefabs/Player.prefab")
        width: Image width in pixels (64-2048)
        height: Image height in pixels (64-2048)
        mode: "preview" for AssetPreview thumbnail, "render" for full offscreen render with lighting

    Returns:
        PNG image of the prefab
    """
    try:
        png_data = _client.prefab_preview(path=prefab_path, width=width, height=height, mode=mode)
        return Image(data=base64.b64encode(png_data).decode(), media_type="image/png")
    except UnityBridgeError as e:
        return _error_text(e)


@mcp.tool()
def get_runtime_hierarchy(scene_path: str | None = None) -> str:
    """Get the runtime hierarchy tree of the active scene, including dynamically spawned objects.

    Args:
        scene_path: Optional scene path to query. Defaults to the active scene.

    Returns:
        JSON tree with name, instanceId, active state, components, and children for each GameObject
    """
    try:
        data = _client.hierarchy(scene_path=scene_path)
        return json.dumps(data, indent=2, ensure_ascii=False)
    except UnityBridgeError as e:
        return _error_text(e)


@mcp.tool()
def get_inspector(object_path: str | None = None, instance_id: int | None = None) -> str:
    """Get detailed Inspector data for a GameObject, including all component properties.

    Args:
        object_path: Scene hierarchy path (e.g. "/Canvas/Panel/Button")
        instance_id: Unity instance ID of the object

    Returns:
        JSON with transform, components, and serialized property values
    """
    try:
        data = _client.inspector(instance_id=instance_id, object_path=object_path)
        return json.dumps(data, indent=2, ensure_ascii=False)
    except UnityBridgeError as e:
        return _error_text(e)


@mcp.tool()
def get_console_logs(severity: str = "all", count: int = 100) -> str:
    """Get recent Unity console log messages.

    Args:
        severity: Filter by type - "all", "log", "warning", or "error"
        count: Number of recent entries to return (1-1000)

    Returns:
        JSON array of log entries with message, stackTrace, type, and timestamp
    """
    try:
        data = _client.console_logs(severity=severity, count=count)
        return json.dumps(data, indent=2, ensure_ascii=False)
    except UnityBridgeError as e:
        return _error_text(e)


@mcp.tool()
def get_editor_state() -> str:
    """Get the current Unity Editor state.

    Returns:
        JSON with playMode, isPaused, isCompiling, scene info, and current selection
    """
    try:
        data = _client.editor_state()
        return json.dumps(data, indent=2, ensure_ascii=False)
    except UnityBridgeError as e:
        return _error_text(e)


@mcp.tool()
def capture_animation_frames(
    target: str,
    clip: str | None = None,
    frame_count: int = 8,
    width: int = 512,
    height: int = 512,
) -> list[Image | str] | str:
    """Capture multiple frames of an animation clip for visual review.

    Samples the animation at evenly-spaced times and renders each frame.
    Works in Edit Mode using AnimationMode sampling.

    Args:
        target: Name of the GameObject with the Animator/Animation component
        clip: Animation clip name (uses first clip if not specified)
        frame_count: Number of frames to capture (2-30)
        width: Frame width in pixels (64-2048)
        height: Frame height in pixels (64-2048)

    Returns:
        List of PNG images, one per sampled frame
    """
    try:
        data = _client.animation_frames(target=target, clip=clip, frame_count=frame_count, width=width, height=height)
        results = []
        for frame in data.get("frames", []):
            img_b64 = frame.get("image", "")
            if img_b64:
                results.append(Image(data=img_b64, media_type="image/png"))
        if not results:
            return f"No frames captured. Clip: {data.get('clip', 'unknown')}, Duration: {data.get('duration', 0)}s"
        return results
    except UnityBridgeError as e:
        return _error_text(e)


@mcp.tool()
def get_animator_state(target: str) -> str:
    """Get the runtime Animator state of a GameObject (Play Mode only).

    Args:
        target: Name of the GameObject with the Animator component

    Returns:
        JSON with current state, parameters, transition info, and layer weights
    """
    try:
        data = _client.animator_state(target=target)
        return json.dumps(data, indent=2, ensure_ascii=False)
    except UnityBridgeError as e:
        return _error_text(e)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

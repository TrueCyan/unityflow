import json
import time
import urllib.error
import urllib.parse
import urllib.request

from unityflow.bridge.config import UNITY_BRIDGE_TIMEOUT, base_url

CONNECT_RETRY_ATTEMPTS = 3
CONNECT_RETRY_BASE_DELAY = 0.5

_TRANSIENT_GUIDANCE = (
    "The editor may be compiling or reloading the AppDomain — wait a few seconds and try again. "
    "Also confirm the Unity Editor is running with the unityflow bridge active."
)


class UnityBridgeError(Exception):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


class UnityClient:
    def _request(self, path, params=None, timeout=None, method="GET"):
        url = base_url() + path
        if params:
            filtered = {k: v for k, v in params.items() if v is not None}
            if filtered:
                url += "?" + urllib.parse.urlencode(filtered)
        timeout = timeout or UNITY_BRIDGE_TIMEOUT

        last_error: Exception | None = None
        for attempt in range(CONNECT_RETRY_ATTEMPTS):
            req = urllib.request.Request(url, method=method)
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    data = resp.read()
                    content_type = resp.headers.get("Content-Type", "")
                    return data, content_type
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")
                try:
                    err = json.loads(body)
                    msg = err.get("error", body)
                except (json.JSONDecodeError, KeyError):
                    msg = body
                raise UnityBridgeError(msg, status_code=e.code) from None
            except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
                last_error = e
                if attempt + 1 < CONNECT_RETRY_ATTEMPTS:
                    time.sleep(CONNECT_RETRY_BASE_DELAY * (2**attempt))

        reason = getattr(last_error, "reason", last_error)
        raise UnityBridgeError(
            f"Cannot connect to Unity Editor ({reason}) after {CONNECT_RETRY_ATTEMPTS} attempts. "
            f"{_TRANSIENT_GUIDANCE}"
        ) from None

    def get_json(self, path, params=None, timeout=None, method="GET"):
        data, _ = self._request(path, params, timeout, method)
        return json.loads(data)

    def post_json(self, path, params=None, timeout=None):
        return self.get_json(path, params, timeout, method="POST")

    def get_png(self, path, params=None, timeout=None):
        data, content_type = self._request(path, params, timeout)
        if "json" in content_type:
            err = json.loads(data)
            raise UnityBridgeError(err.get("error", "unknown error"))
        return data

    def ping(self):
        return self.get_json("/api/ping")

    def screenshot(self, view="scene", width=1024, height=768):
        return self.get_png("/api/screenshot", {"view": view, "width": width, "height": height})

    def prefab_preview(self, path, width=512, height=512, mode="render", angle=None):
        params = {"path": path, "width": width, "height": height, "mode": mode}
        if angle:
            params["angle"] = angle
        return self.get_png("/api/prefab_preview", params)

    def hierarchy(self, scene_path=None):
        return self.get_json("/api/hierarchy", {"scene": scene_path})

    def inspector(self, instance_id=None, object_path=None):
        params = {}
        if instance_id is not None:
            params["id"] = instance_id
        if object_path is not None:
            params["path"] = object_path
        return self.get_json("/api/inspector", params)

    def console_logs(self, severity="all", count=100):
        return self.get_json("/api/console", {"severity": severity, "count": count})

    def editor_state(self):
        return self.get_json("/api/editor_state")

    def refresh_assets(self):
        return self.post_json("/api/refresh_assets")

    def animation_frames(self, target, clip=None, frame_count=8, width=512, height=512):
        return self.get_json(
            "/api/animation_frames",
            {"target": target, "clip": clip, "frames": frame_count, "width": width, "height": height},
            timeout=max(UNITY_BRIDGE_TIMEOUT, 60),
        )

    def animator_state(self, target):
        return self.get_json("/api/animator_state", {"target": target})

    def playmode_state(self):
        return self.get_json("/api/playmode/state")

    def playmode_play(self):
        return self.post_json("/api/playmode/play")

    def playmode_stop(self):
        return self.post_json("/api/playmode/stop")

    def playmode_pause(self):
        return self.post_json("/api/playmode/pause")

    def playmode_step(self):
        return self.post_json("/api/playmode/step")

    def scene_list(self):
        return self.get_json("/api/scene/list")

    def scene_load(self, path, additive=False):
        return self.post_json("/api/scene/load", {"path": path, "additive": "true" if additive else "false"})

    def scene_view_camera(self):
        return self.get_json("/api/camera/scene_view")

    def set_scene_view_camera(
        self,
        pivot_x=None,
        pivot_y=None,
        pivot_z=None,
        rotation_x=None,
        rotation_y=None,
        rotation_z=None,
        size=None,
        orthographic=None,
    ):
        params = {}
        if pivot_x is not None:
            params["pivotX"] = pivot_x
        if pivot_y is not None:
            params["pivotY"] = pivot_y
        if pivot_z is not None:
            params["pivotZ"] = pivot_z
        if rotation_x is not None:
            params["rotationX"] = rotation_x
        if rotation_y is not None:
            params["rotationY"] = rotation_y
        if rotation_z is not None:
            params["rotationZ"] = rotation_z
        if size is not None:
            params["size"] = size
        if orthographic is not None:
            params["orthographic"] = "true" if orthographic else "false"
        return self.post_json("/api/camera/scene_view", params)

    def frame_object(self, path=None, instance_id=None):
        params = {}
        if path is not None:
            params["path"] = path
        if instance_id is not None:
            params["id"] = instance_id
        return self.post_json("/api/camera/frame_object", params)

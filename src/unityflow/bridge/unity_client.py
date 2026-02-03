import json
import urllib.error
import urllib.parse
import urllib.request

from unityflow.bridge.config import UNITY_BRIDGE_TIMEOUT, base_url


class UnityBridgeError(Exception):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


class UnityClient:
    def _request(self, path, params=None, timeout=None):
        url = base_url() + path
        if params:
            filtered = {k: v for k, v in params.items() if v is not None}
            if filtered:
                url += "?" + urllib.parse.urlencode(filtered)
        timeout = timeout or UNITY_BRIDGE_TIMEOUT
        req = urllib.request.Request(url)
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
        except urllib.error.URLError as e:
            raise UnityBridgeError(f"Cannot connect to Unity Editor: {e.reason}") from None

    def get_json(self, path, params=None, timeout=None):
        data, _ = self._request(path, params, timeout)
        return json.loads(data)

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

    def prefab_preview(self, path, width=512, height=512, mode="render"):
        return self.get_png("/api/prefab_preview", {"path": path, "width": width, "height": height, "mode": mode})

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

    def animation_frames(self, target, clip=None, frame_count=8, width=512, height=512):
        return self.get_json(
            "/api/animation_frames",
            {"target": target, "clip": clip, "frames": frame_count, "width": width, "height": height},
            timeout=max(UNITY_BRIDGE_TIMEOUT, 60),
        )

    def animator_state(self, target):
        return self.get_json("/api/animator_state", {"target": target})

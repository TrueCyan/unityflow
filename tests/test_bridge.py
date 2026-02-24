from unittest.mock import MagicMock, patch

import pytest

from unityflow.bridge.unity_client import UnityBridgeError, UnityClient


class TestUnityClient:
    def setup_method(self):
        self.client = UnityClient()

    def test_get_json_builds_url(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"status":"ok"}'
        mock_resp.headers.get.return_value = "application/json"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = self.client.get_json("/api/ping")
        assert result == {"status": "ok"}

    def test_get_json_with_params(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"count":5}'
        mock_resp.headers.get.return_value = "application/json"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
            self.client.get_json("/api/console", {"severity": "error", "count": 5})
            url = mock_open.call_args[0][0].full_url
            assert "severity=error" in url
            assert "count=5" in url

    def test_get_json_filters_none_params(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"{}"
        mock_resp.headers.get.return_value = "application/json"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
            self.client.get_json("/api/hierarchy", {"scene": None})
            url = mock_open.call_args[0][0].full_url
            assert "?" not in url

    def test_post_json_uses_post_method(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"success":true}'
        mock_resp.headers.get.return_value = "application/json"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
            result = self.client.post_json("/api/playmode/play")
            req = mock_open.call_args[0][0]
            assert req.method == "POST"
            assert result == {"success": True}

    def test_get_png_returns_bytes(self):
        png_bytes = b"\x89PNG\r\n\x1a\n"
        mock_resp = MagicMock()
        mock_resp.read.return_value = png_bytes
        mock_resp.headers.get.return_value = "image/png"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = self.client.get_png("/api/screenshot")
        assert result == png_bytes

    def test_get_png_raises_on_json_error(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"error":"no scene view"}'
        mock_resp.headers.get.return_value = "application/json"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            with pytest.raises(UnityBridgeError, match="no scene view"):
                self.client.get_png("/api/screenshot")

    def test_http_error_extracts_message(self):
        import urllib.error

        error_body = b'{"error":"Object not found"}'
        http_error = urllib.error.HTTPError(
            url="http://localhost:29184/api/inspector",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=MagicMock(read=MagicMock(return_value=error_body)),
        )
        with patch("urllib.request.urlopen", side_effect=http_error):
            with pytest.raises(UnityBridgeError, match="Object not found") as exc_info:
                self.client.get_json("/api/inspector")
            assert exc_info.value.status_code == 404

    def test_playmode_methods(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"isPlaying":false,"isPaused":false,"isCompiling":false}'
        mock_resp.headers.get.return_value = "application/json"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = self.client.playmode_state()
            assert result["isPlaying"] is False

    def test_scene_load_params(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"success":true}'
        mock_resp.headers.get.return_value = "application/json"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
            self.client.scene_load("Assets/Scenes/Main.unity", additive=True)
            req = mock_open.call_args[0][0]
            assert req.method == "POST"
            assert "additive=true" in req.full_url

    def test_set_scene_view_camera_params(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"pivotX":1.0}'
        mock_resp.headers.get.return_value = "application/json"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
            self.client.set_scene_view_camera(pivot_x=1.0, size=5.0, orthographic=True)
            url = mock_open.call_args[0][0].full_url
            assert "pivotX=1.0" in url
            assert "size=5.0" in url
            assert "orthographic=true" in url

    def test_frame_object_by_path(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"success":true}'
        mock_resp.headers.get.return_value = "application/json"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
            self.client.frame_object(path="/Player")
            req = mock_open.call_args[0][0]
            assert req.method == "POST"
            assert "path=%2FPlayer" in req.full_url

    def test_frame_object_by_instance_id(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"success":true}'
        mock_resp.headers.get.return_value = "application/json"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
            self.client.frame_object(instance_id=12345)
            url = mock_open.call_args[0][0].full_url
            assert "id=12345" in url


class TestMcpServerImport:
    def test_server_module_imports(self):
        from unityflow.bridge.server import mcp

        assert mcp is not None
        assert mcp.name == "unityflow-bridge"

    def test_all_tools_registered(self):
        from unityflow.bridge.server import mcp

        tool_names = set()
        for tool in mcp._tool_manager._tools.values():
            tool_names.add(tool.name)

        expected = {
            "capture_screenshot",
            "capture_prefab_preview",
            "get_runtime_hierarchy",
            "get_inspector",
            "get_console_logs",
            "get_editor_state",
            "capture_animation_frames",
            "get_animator_state",
            "control_playmode",
            "load_scene",
            "list_scenes",
            "get_scene_camera",
            "set_scene_camera",
            "frame_object",
        }
        assert tool_names == expected

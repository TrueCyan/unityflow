using System;
using System.Net;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace UnityFlow.Bridge.Handlers
{
    public static class ScreenshotHandler
    {
        public static void Register(UnityFlowHttpServer server)
        {
            server.RegisterBinaryRoute("/api/screenshot", HandleScreenshot);
            server.RegisterBinaryRoute("/api/prefab_preview", HandlePrefabPreview);
        }

        private static byte[] HandleScreenshot(HttpListenerRequest request, RequestContext ctx)
        {
            string view = request.QueryString["view"] ?? "scene";
            int width = ParseInt(request.QueryString["width"], 1024);
            int height = ParseInt(request.QueryString["height"], 768);
            width = Mathf.Clamp(width, 64, 4096);
            height = Mathf.Clamp(height, 64, 4096);

            Camera camera;

            if (view == "game")
            {
                camera = Camera.main;
                if (camera == null)
                {
                    ctx.StatusCode = 400;
                    ctx.ContentType = "application/json";
                    return Encoding.UTF8.GetBytes("{\"error\":\"no main camera found\"}");
                }
            }
            else
            {
                var sceneView = SceneView.lastActiveSceneView;
                if (sceneView == null)
                {
                    ctx.StatusCode = 400;
                    ctx.ContentType = "application/json";
                    return Encoding.UTF8.GetBytes("{\"error\":\"no active scene view\"}");
                }
                camera = sceneView.camera;
            }

            var rt = RenderTexture.GetTemporary(width, height, 24, RenderTextureFormat.ARGB32);
            var prevRT = camera.targetTexture;

            try
            {
                camera.targetTexture = rt;
                camera.Render();

                var tex = new Texture2D(width, height, TextureFormat.RGB24, false);
                RenderTexture.active = rt;
                tex.ReadPixels(new Rect(0, 0, width, height), 0, 0);
                tex.Apply();
                RenderTexture.active = null;

                byte[] png = tex.EncodeToPNG();
                UnityEngine.Object.DestroyImmediate(tex);

                ctx.ContentType = "image/png";
                return png;
            }
            finally
            {
                camera.targetTexture = prevRT;
                RenderTexture.ReleaseTemporary(rt);
            }
        }

        private static byte[] HandlePrefabPreview(HttpListenerRequest request, RequestContext ctx)
        {
            string prefabPath = request.QueryString["path"];
            string mode = request.QueryString["mode"] ?? "preview";
            int width = ParseInt(request.QueryString["width"], 512);
            int height = ParseInt(request.QueryString["height"], 512);
            width = Mathf.Clamp(width, 64, 2048);
            height = Mathf.Clamp(height, 64, 2048);

            if (string.IsNullOrEmpty(prefabPath))
            {
                ctx.StatusCode = 400;
                ctx.ContentType = "application/json";
                return Encoding.UTF8.GetBytes("{\"error\":\"path parameter required\"}");
            }

            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath);
            if (prefab == null)
            {
                ctx.StatusCode = 404;
                ctx.ContentType = "application/json";
                return Encoding.UTF8.GetBytes("{\"error\":\"prefab not found\"}");
            }

            if (mode == "preview")
                return CaptureAssetPreview(prefab, width, height, ctx);

            return CaptureOffscreenRender(prefab, width, height, ctx);
        }

        private static byte[] CaptureAssetPreview(GameObject prefab, int width, int height, RequestContext ctx)
        {
            var preview = AssetPreview.GetAssetPreview(prefab);
            if (preview == null)
            {
                AssetPreview.SetPreviewTextureCacheSize(256);
                preview = AssetPreview.GetAssetPreview(prefab);
            }

            if (preview == null)
            {
                return CaptureOffscreenRender(prefab, width, height, ctx);
            }

            var readableTex = new Texture2D(preview.width, preview.height, preview.format, false);
            Graphics.CopyTexture(preview, readableTex);
            byte[] png = readableTex.EncodeToPNG();
            UnityEngine.Object.DestroyImmediate(readableTex);

            ctx.ContentType = "image/png";
            return png;
        }

        private static byte[] CaptureOffscreenRender(GameObject prefab, int width, int height, RequestContext ctx)
        {
            var previewScene = EditorSceneManager.NewPreviewScene();

            try
            {
                var instance = (GameObject)PrefabUtility.InstantiatePrefab(prefab, previewScene);
                SceneManager.MoveGameObjectToScene(instance, previewScene);

                var bounds = CalculateBounds(instance);

                var camGo = new GameObject("PreviewCamera");
                SceneManager.MoveGameObjectToScene(camGo, previewScene);
                var cam = camGo.AddComponent<Camera>();
                cam.scene = previewScene;
                cam.clearFlags = CameraClearFlags.SolidColor;
                cam.backgroundColor = new Color(0.2f, 0.2f, 0.2f, 1f);

                float maxExtent = Mathf.Max(bounds.extents.x, bounds.extents.y, bounds.extents.z);
                float distance = maxExtent * 2.5f;
                cam.transform.position = bounds.center + new Vector3(0.5f, 0.7f, -1f).normalized * distance;
                cam.transform.LookAt(bounds.center);
                cam.nearClipPlane = distance * 0.01f;
                cam.farClipPlane = distance * 10f;

                var lightGo = new GameObject("PreviewLight");
                SceneManager.MoveGameObjectToScene(lightGo, previewScene);
                var light = lightGo.AddComponent<Light>();
                light.type = LightType.Directional;
                lightGo.transform.rotation = Quaternion.Euler(50f, -30f, 0f);
                light.intensity = 1.0f;

                var fillGo = new GameObject("FillLight");
                SceneManager.MoveGameObjectToScene(fillGo, previewScene);
                var fill = fillGo.AddComponent<Light>();
                fill.type = LightType.Directional;
                fillGo.transform.rotation = Quaternion.Euler(-20f, 120f, 0f);
                fill.intensity = 0.5f;

                var rt = RenderTexture.GetTemporary(width, height, 24, RenderTextureFormat.ARGB32);
                cam.targetTexture = rt;
                cam.Render();

                var tex = new Texture2D(width, height, TextureFormat.RGB24, false);
                RenderTexture.active = rt;
                tex.ReadPixels(new Rect(0, 0, width, height), 0, 0);
                tex.Apply();
                RenderTexture.active = null;

                byte[] png = tex.EncodeToPNG();
                UnityEngine.Object.DestroyImmediate(tex);
                RenderTexture.ReleaseTemporary(rt);

                ctx.ContentType = "image/png";
                return png;
            }
            finally
            {
                EditorSceneManager.ClosePreviewScene(previewScene);
            }
        }

        private static Bounds CalculateBounds(GameObject go)
        {
            var renderers = go.GetComponentsInChildren<Renderer>();
            if (renderers.Length == 0)
                return new Bounds(go.transform.position, Vector3.one);

            var bounds = renderers[0].bounds;
            for (int i = 1; i < renderers.Length; i++)
                bounds.Encapsulate(renderers[i].bounds);
            return bounds;
        }

        private static int ParseInt(string s, int defaultValue)
        {
            return int.TryParse(s, out int v) ? v : defaultValue;
        }
    }
}

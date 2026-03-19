using System;
using System.Net;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

namespace UnityFlow.Bridge.Handlers
{
    public static class ScreenshotHandler
    {
        private static readonly Vector3[] AnglePresets = new Vector3[]
        {
            new Vector3(0.5f, 0.7f, -1f),   // default (isometric)
            new Vector3(0f, 0f, -1f),         // front
            new Vector3(0f, 0f, 1f),          // back
            new Vector3(-1f, 0f, 0f),         // left
            new Vector3(1f, 0f, 0f),          // right
            new Vector3(0f, 1f, 0f),          // top
            new Vector3(0f, -1f, 0f),         // bottom
        };

        private static readonly string[] AngleNames = new string[]
        {
            "default", "front", "back", "left", "right", "top", "bottom"
        };

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
            string angle = request.QueryString["angle"];
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

            return CaptureOffscreenRender(prefab, width, height, angle, ctx);
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
                return CaptureOffscreenRender(prefab, width, height, null, ctx);
            }

            var readableTex = new Texture2D(preview.width, preview.height, preview.format, false);
            Graphics.CopyTexture(preview, readableTex);
            byte[] png = readableTex.EncodeToPNG();
            UnityEngine.Object.DestroyImmediate(readableTex);

            ctx.ContentType = "image/png";
            return png;
        }

        private static byte[] CaptureOffscreenRender(
            GameObject prefab, int width, int height, string angle, RequestContext ctx)
        {
            var previewScene = EditorSceneManager.NewPreviewScene();
            previewScene.name = "UnityFlowPreview";

            try
            {
                var holder = new GameObject("__holder__");
                SceneManager.MoveGameObjectToScene(holder, previewScene);
                holder.SetActive(false);

                var instance = (GameObject)PrefabUtility.InstantiatePrefab(prefab, holder.transform);

                instance.transform.SetParent(null, false);
                holder.SetActive(true);

                bool isUI = instance.GetComponentsInChildren<Canvas>().Length > 0;

                Canvas worldCanvas = null;
                if (isUI)
                    worldCanvas = SetupUIForCapture(instance);

                RebuildTextMeshPro(instance);

                var bounds = isUI ? CalculateUIBounds(instance) : CalculateBounds(instance);
                Debug.Log($"[UnityFlow] Bounds (isUI={isUI}): center={bounds.center}, size={bounds.size}, sqrMag={bounds.size.sqrMagnitude}");

                if (bounds.size.sqrMagnitude < 0.001f)
                {
                    bounds = CalculateBounds(instance);
                    Debug.Log($"[UnityFlow] Fallback to 3D bounds: size={bounds.size}, sqrMag={bounds.size.sqrMagnitude}");
                    isUI = false;
                }

                if (bounds.size.sqrMagnitude < 0.001f)
                {
                    bounds = new Bounds(instance.transform.position, Vector3.one);
                    Debug.Log("[UnityFlow] Last resort bounds: Vector3.one");
                }


                var camGo = new GameObject("PreviewCamera");
                SceneManager.MoveGameObjectToScene(camGo, previewScene);
                var cam = camGo.AddComponent<Camera>();
                cam.scene = previewScene;
                cam.clearFlags = CameraClearFlags.SolidColor;
                cam.backgroundColor = new Color(0.2f, 0.2f, 0.2f, 1f);

                TrySetupRenderPipeline(camGo);

                if (isUI)
                    SetupUICameraPosition(cam, bounds);
                else
                    Setup3DCameraPosition(cam, bounds, ResolveAngle(angle));

                if (!isUI)
                    SetupLighting(previewScene);

                var rt = RenderTexture.GetTemporary(width, height, 24, RenderTextureFormat.ARGB32);

                if (isUI && worldCanvas != null)
                    worldCanvas.worldCamera = cam;

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

        private static void RebuildTextMeshPro(GameObject instance)
        {
            var tmpTextType = Type.GetType("TMPro.TMP_Text, Unity.TextMeshPro");
            Debug.Log($"[UnityFlow] TMP_Text type resolved: {tmpTextType != null}");
            if (tmpTextType == null)
            {
                tmpTextType = Type.GetType("TMPro.TMP_Text, Unity.TextMeshPro.Runtime");
                Debug.Log($"[UnityFlow] TMP_Text fallback (Runtime): {tmpTextType != null}");
                if (tmpTextType == null)
                    return;
            }

            var forceMeshUpdate = tmpTextType.GetMethod("ForceMeshUpdate", Type.EmptyTypes);
            if (forceMeshUpdate == null)
                forceMeshUpdate = tmpTextType.GetMethod("ForceMeshUpdate", new[] { typeof(bool) });
            if (forceMeshUpdate == null)
                forceMeshUpdate = tmpTextType.GetMethod("ForceMeshUpdate", new[] { typeof(bool), typeof(bool) });
            Debug.Log($"[UnityFlow] ForceMeshUpdate method: {forceMeshUpdate != null} (params: {forceMeshUpdate?.GetParameters().Length})");
            if (forceMeshUpdate == null)
                return;

            var components = instance.GetComponentsInChildren(tmpTextType, true);
            Debug.Log($"[UnityFlow] TMP components found: {components.Length}");

            foreach (var comp in components)
            {
                try
                {
                    int paramCount = forceMeshUpdate.GetParameters().Length;
                    if (paramCount == 0)
                        forceMeshUpdate.Invoke(comp, null);
                    else if (paramCount == 1)
                        forceMeshUpdate.Invoke(comp, new object[] { true });
                    else
                        forceMeshUpdate.Invoke(comp, new object[] { true, false });
                }
                catch (Exception e)
                {
                    Debug.LogWarning($"[UnityFlow] ForceMeshUpdate failed on {comp.name}: {e.Message}");
                }
            }
        }

        private static Canvas SetupUIForCapture(GameObject instance)
        {
            var canvases = instance.GetComponentsInChildren<Canvas>();
            Debug.Log($"[UnityFlow] Canvas count: {canvases.Length}");
            Canvas rootCanvas = null;

            foreach (var canvas in canvases)
            {
                if (rootCanvas == null)
                    rootCanvas = canvas;
            }

            if (rootCanvas == null)
                return null;

            var scaler = rootCanvas.GetComponent<CanvasScaler>();
            var refResolution = scaler != null
                ? scaler.referenceResolution
                : new Vector2(1080, 1920);
            Debug.Log($"[UnityFlow] Reference resolution: {refResolution}");

            foreach (var canvas in canvases)
            {
                Debug.Log($"[UnityFlow] Canvas '{canvas.name}': {canvas.renderMode} -> WorldSpace");
                canvas.renderMode = RenderMode.WorldSpace;
            }

            var rt = rootCanvas.GetComponent<RectTransform>();
            if (rt != null)
            {
                rt.sizeDelta = refResolution;
                rt.localScale = Vector3.one * (1f / refResolution.y);
            }

            var scalers = instance.GetComponentsInChildren<CanvasScaler>();
            Debug.Log($"[UnityFlow] CanvasScaler disabled: {scalers.Length}");
            foreach (var s in scalers)
                s.enabled = false;

            Canvas.ForceUpdateCanvases();

            if (rt != null)
            {
                var rebuilderType = Type.GetType("UnityEngine.UI.LayoutRebuilder, UnityEngine.UI");
                if (rebuilderType != null)
                {
                    var forceRebuild = rebuilderType.GetMethod(
                        "ForceRebuildLayoutImmediate",
                        System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Static,
                        null,
                        new[] { typeof(RectTransform) },
                        null);
                    forceRebuild?.Invoke(null, new object[] { rt });
                }
            }

            return rootCanvas;
        }

        private static Bounds CalculateUIBounds(GameObject go)
        {
            var corners = new Vector3[4];

            var rootRT = go.GetComponent<RectTransform>();
            if (rootRT != null)
            {
                rootRT.GetWorldCorners(corners);
                var rootBounds = BoundsFromCorners(corners);
                if (rootBounds.size.sqrMagnitude > 0.001f && rootBounds.size.x < 10000f && rootBounds.size.y < 10000f)
                    return rootBounds;
            }

            var rectTransforms = go.GetComponentsInChildren<RectTransform>();
            if (rectTransforms.Length == 0)
                return new Bounds(go.transform.position, Vector3.one);

            var first = rectTransforms[0];
            first.GetWorldCorners(corners);
            var allBounds = BoundsFromCorners(corners);

            for (int i = 1; i < rectTransforms.Length; i++)
            {
                rectTransforms[i].GetWorldCorners(corners);
                for (int j = 0; j < 4; j++)
                    allBounds.Encapsulate(corners[j]);
            }

            if (allBounds.size.x > 10000f || allBounds.size.y > 10000f)
            {
                if (rootRT != null)
                {
                    rootRT.GetWorldCorners(corners);
                    var rootFallback = BoundsFromCorners(corners);
                    if (rootFallback.size.sqrMagnitude > 0.001f)
                        return rootFallback;
                }
            }

            return allBounds;
        }

        private static Bounds BoundsFromCorners(Vector3[] corners)
        {
            var b = new Bounds(corners[0], Vector3.zero);
            for (int i = 1; i < 4; i++)
                b.Encapsulate(corners[i]);
            return b;
        }

        private static void SetupUICameraPosition(Camera cam, Bounds bounds)
        {
            cam.orthographic = true;
            float orthoHeight = bounds.extents.y;
            float orthoWidth = bounds.extents.x;
            cam.orthographicSize = Mathf.Max(orthoHeight, orthoWidth) * 1.05f;
            cam.transform.position = bounds.center + new Vector3(0f, 0f, -10f);
            cam.transform.LookAt(bounds.center);
            cam.nearClipPlane = 0.1f;
            cam.farClipPlane = 100f;
        }

        private static void Setup3DCameraPosition(Camera cam, Bounds bounds, Vector3 direction)
        {
            float maxExtent = Mathf.Max(bounds.extents.x, bounds.extents.y, bounds.extents.z);
            float distance = maxExtent * 2.5f;
            cam.transform.position = bounds.center + direction.normalized * distance;
            cam.transform.LookAt(bounds.center);
            cam.nearClipPlane = distance * 0.01f;
            cam.farClipPlane = distance * 10f;
        }

        private static void SetupLighting(Scene previewScene)
        {
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
        }

        private static void TrySetupRenderPipeline(GameObject camGo)
        {
            var pipelineAsset = UnityEngine.Rendering.GraphicsSettings.currentRenderPipeline;
            if (pipelineAsset == null)
                return;

            var urpDataType = Type.GetType(
                "UnityEngine.Rendering.Universal.UniversalAdditionalCameraData, Unity.RenderPipelines.Universal.Runtime");
            if (urpDataType == null)
                return;

            var urpData = camGo.AddComponent(urpDataType);
            var setRendererMethod = urpDataType.GetMethod("SetRenderer", new[] { typeof(int) });
            setRendererMethod?.Invoke(urpData, new object[] { 0 });
        }

        private static Vector3 ResolveAngle(string angle)
        {
            if (string.IsNullOrEmpty(angle))
                return AnglePresets[0];

            for (int i = 0; i < AngleNames.Length; i++)
            {
                if (string.Equals(AngleNames[i], angle, StringComparison.OrdinalIgnoreCase))
                    return AnglePresets[i];
            }

            return AnglePresets[0];
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

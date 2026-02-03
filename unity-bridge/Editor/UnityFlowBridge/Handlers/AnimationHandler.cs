using System;
using System.Collections.Generic;
using System.Net;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace UnityFlow.Bridge.Handlers
{
    public static class AnimationHandler
    {
        public static void Register(UnityFlowHttpServer server)
        {
            server.RegisterRoute("/api/animation_frames", HandleAnimationFrames);
            server.RegisterRoute("/api/animator_state", HandleAnimatorState);
        }

        private static string HandleAnimationFrames(HttpListenerRequest request, RequestContext ctx)
        {
            string targetName = request.QueryString["target"];
            string clipName = request.QueryString["clip"];
            int frameCount = ParseInt(request.QueryString["frames"], 8);
            int width = ParseInt(request.QueryString["width"], 512);
            int height = ParseInt(request.QueryString["height"], 512);
            frameCount = Mathf.Clamp(frameCount, 2, 30);
            width = Mathf.Clamp(width, 64, 2048);
            height = Mathf.Clamp(height, 64, 2048);

            if (string.IsNullOrEmpty(targetName))
            {
                ctx.StatusCode = 400;
                return "{\"error\":\"target parameter required\"}";
            }

            var targetGo = GameObject.Find(targetName);
            if (targetGo == null)
            {
                ctx.StatusCode = 404;
                return "{\"error\":\"target object not found\"}";
            }

            AnimationClip clip = FindClip(targetGo, clipName);
            if (clip == null)
            {
                ctx.StatusCode = 404;
                return "{\"error\":\"animation clip not found\"}";
            }

            var previewScene = EditorSceneManager.NewPreviewScene();

            try
            {
                var instance = UnityEngine.Object.Instantiate(targetGo);
                SceneManager.MoveGameObjectToScene(instance, previewScene);
                instance.transform.position = Vector3.zero;
                instance.transform.rotation = Quaternion.identity;

                var bounds = CalculateBounds(instance);

                var camGo = new GameObject("PreviewCamera");
                SceneManager.MoveGameObjectToScene(camGo, previewScene);
                var cam = camGo.AddComponent<Camera>();
                cam.scene = previewScene;
                cam.clearFlags = CameraClearFlags.SolidColor;
                cam.backgroundColor = new Color(0.2f, 0.2f, 0.2f, 1f);

                float maxExtent = Mathf.Max(bounds.extents.x, bounds.extents.y, bounds.extents.z);
                float distance = maxExtent * 2.5f;
                cam.transform.position = bounds.center + new Vector3(0f, 0.5f, -1f).normalized * distance;
                cam.transform.LookAt(bounds.center);
                cam.nearClipPlane = distance * 0.01f;
                cam.farClipPlane = distance * 10f;

                var lightGo = new GameObject("Light");
                SceneManager.MoveGameObjectToScene(lightGo, previewScene);
                var light = lightGo.AddComponent<Light>();
                light.type = LightType.Directional;
                lightGo.transform.rotation = Quaternion.Euler(50f, -30f, 0f);

                var sb = new StringBuilder();
                sb.Append("{\"clip\":\"");
                sb.Append(EscapeJson(clip.name));
                sb.Append("\",\"duration\":");
                sb.Append(clip.length);
                sb.Append(",\"frameRate\":");
                sb.Append(clip.frameRate);
                sb.Append(",\"frames\":[");

                AnimationMode.StartAnimationMode();
                try
                {
                    for (int i = 0; i < frameCount; i++)
                    {
                        float t = clip.length * i / (frameCount - 1);
                        AnimationMode.BeginSampling();
                        AnimationMode.SampleAnimationClip(instance, clip, t);
                        AnimationMode.EndSampling();

                        var rt = RenderTexture.GetTemporary(width, height, 24, RenderTextureFormat.ARGB32);
                        cam.targetTexture = rt;
                        cam.Render();

                        var tex = new Texture2D(width, height, TextureFormat.RGB24, false);
                        RenderTexture.active = rt;
                        tex.ReadPixels(new Rect(0, 0, width, height), 0, 0);
                        tex.Apply();
                        RenderTexture.active = null;

                        byte[] png = tex.EncodeToPNG();
                        string base64 = Convert.ToBase64String(png);
                        UnityEngine.Object.DestroyImmediate(tex);
                        RenderTexture.ReleaseTemporary(rt);

                        if (i > 0) sb.Append(",");
                        sb.Append("{\"time\":");
                        sb.Append(t);
                        sb.Append(",\"frame\":");
                        sb.Append(i);
                        sb.Append(",\"image\":\"");
                        sb.Append(base64);
                        sb.Append("\"}");
                    }
                }
                finally
                {
                    AnimationMode.StopAnimationMode();
                }

                sb.Append("]}");
                return sb.ToString();
            }
            finally
            {
                EditorSceneManager.ClosePreviewScene(previewScene);
            }
        }

        private static string HandleAnimatorState(HttpListenerRequest request, RequestContext ctx)
        {
            string targetName = request.QueryString["target"];
            if (string.IsNullOrEmpty(targetName))
            {
                ctx.StatusCode = 400;
                return "{\"error\":\"target parameter required\"}";
            }

            var targetGo = GameObject.Find(targetName);
            if (targetGo == null)
            {
                ctx.StatusCode = 404;
                return "{\"error\":\"target object not found\"}";
            }

            var animator = targetGo.GetComponent<Animator>();
            if (animator == null)
            {
                ctx.StatusCode = 400;
                return "{\"error\":\"no Animator component on target\"}";
            }

            if (!EditorApplication.isPlaying)
            {
                ctx.StatusCode = 400;
                return "{\"error\":\"animator state only available in Play Mode\"}";
            }

            var sb = new StringBuilder();
            sb.Append("{\"target\":\"");
            sb.Append(EscapeJson(targetGo.name));
            sb.Append("\",\"isInTransition\":");
            sb.Append(animator.IsInTransition(0) ? "true" : "false");

            var stateInfo = animator.GetCurrentAnimatorStateInfo(0);
            sb.Append(",\"currentState\":{\"nameHash\":");
            sb.Append(stateInfo.shortNameHash);
            sb.Append(",\"normalizedTime\":");
            sb.Append(stateInfo.normalizedTime);
            sb.Append(",\"length\":");
            sb.Append(stateInfo.length);
            sb.Append(",\"speed\":");
            sb.Append(stateInfo.speed);
            sb.Append(",\"loop\":");
            sb.Append(stateInfo.loop ? "true" : "false");
            sb.Append("}");

            sb.Append(",\"parameters\":[");
            for (int i = 0; i < animator.parameterCount; i++)
            {
                if (i > 0) sb.Append(",");
                var param = animator.GetParameter(i);
                sb.Append("{\"name\":\"");
                sb.Append(EscapeJson(param.name));
                sb.Append("\",\"type\":\"");
                sb.Append(param.type.ToString());
                sb.Append("\",\"value\":");
                switch (param.type)
                {
                    case AnimatorControllerParameterType.Bool:
                        sb.Append(animator.GetBool(param.name) ? "true" : "false");
                        break;
                    case AnimatorControllerParameterType.Int:
                        sb.Append(animator.GetInteger(param.name));
                        break;
                    case AnimatorControllerParameterType.Float:
                        sb.Append(animator.GetFloat(param.name));
                        break;
                    case AnimatorControllerParameterType.Trigger:
                        sb.Append("null");
                        break;
                }
                sb.Append("}");
            }
            sb.Append("]");

            if (animator.layerCount > 1)
            {
                sb.Append(",\"layers\":[");
                for (int i = 0; i < animator.layerCount; i++)
                {
                    if (i > 0) sb.Append(",");
                    sb.Append("{\"name\":\"");
                    sb.Append(EscapeJson(animator.GetLayerName(i)));
                    sb.Append("\",\"weight\":");
                    sb.Append(animator.GetLayerWeight(i));
                    sb.Append("}");
                }
                sb.Append("]");
            }

            sb.Append("}");
            return sb.ToString();
        }

        private static AnimationClip FindClip(GameObject go, string clipName)
        {
            var animator = go.GetComponent<Animator>();
            if (animator != null && animator.runtimeAnimatorController != null)
            {
                foreach (var clip in animator.runtimeAnimatorController.animationClips)
                {
                    if (string.IsNullOrEmpty(clipName) || clip.name == clipName)
                        return clip;
                }
            }

            var animation = go.GetComponent<Animation>();
            if (animation != null)
            {
                foreach (AnimationState state in animation)
                {
                    if (string.IsNullOrEmpty(clipName) || state.name == clipName)
                        return state.clip;
                }
            }

            if (!string.IsNullOrEmpty(clipName))
            {
                string[] guids = AssetDatabase.FindAssets($"{clipName} t:AnimationClip");
                foreach (var guid in guids)
                {
                    string path = AssetDatabase.GUIDToAssetPath(guid);
                    var clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(path);
                    if (clip != null && clip.name == clipName)
                        return clip;
                }
            }

            return null;
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

        private static string EscapeJson(string s)
        {
            if (s == null) return "";
            return s.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\n", "\\n").Replace("\r", "\\r");
        }

        private static int ParseInt(string s, int defaultValue)
        {
            return int.TryParse(s, out int v) ? v : defaultValue;
        }
    }
}

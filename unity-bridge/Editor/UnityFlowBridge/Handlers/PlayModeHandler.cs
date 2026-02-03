using System.Net;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace UnityFlow.Bridge.Handlers
{
    public static class PlayModeHandler
    {
        public static void Register(UnityFlowHttpServer server)
        {
            server.RegisterRoute("/api/playmode/state", HandleGetState);
            server.RegisterRoute("/api/playmode/play", HandlePlay);
            server.RegisterRoute("/api/playmode/stop", HandleStop);
            server.RegisterRoute("/api/playmode/pause", HandlePause);
            server.RegisterRoute("/api/playmode/step", HandleStep);
            server.RegisterRoute("/api/scene/load", HandleLoadScene);
            server.RegisterRoute("/api/scene/list", HandleListScenes);
        }

        private static string HandleGetState(HttpListenerRequest request, RequestContext ctx)
        {
            return JsonUtility.ToJson(new PlayModeStateResponse
            {
                isPlaying = EditorApplication.isPlaying,
                isPaused = EditorApplication.isPaused,
                isCompiling = EditorApplication.isCompiling
            });
        }

        private static string HandlePlay(HttpListenerRequest request, RequestContext ctx)
        {
            if (request.HttpMethod != "POST")
            {
                ctx.StatusCode = 405;
                return "{\"error\":\"Method not allowed. Use POST.\"}";
            }

            if (EditorApplication.isCompiling)
            {
                ctx.StatusCode = 409;
                return "{\"error\":\"Cannot enter play mode while compiling\"}";
            }

            if (EditorApplication.isPlaying)
            {
                return "{\"success\":true,\"message\":\"Already in play mode\"}";
            }

            EditorApplication.isPlaying = true;
            return "{\"success\":true,\"message\":\"Entering play mode\"}";
        }

        private static string HandleStop(HttpListenerRequest request, RequestContext ctx)
        {
            if (request.HttpMethod != "POST")
            {
                ctx.StatusCode = 405;
                return "{\"error\":\"Method not allowed. Use POST.\"}";
            }

            if (!EditorApplication.isPlaying)
            {
                return "{\"success\":true,\"message\":\"Already in edit mode\"}";
            }

            EditorApplication.isPlaying = false;
            return "{\"success\":true,\"message\":\"Stopping play mode\"}";
        }

        private static string HandlePause(HttpListenerRequest request, RequestContext ctx)
        {
            if (request.HttpMethod != "POST")
            {
                ctx.StatusCode = 405;
                return "{\"error\":\"Method not allowed. Use POST.\"}";
            }

            if (!EditorApplication.isPlaying)
            {
                ctx.StatusCode = 409;
                return "{\"error\":\"Cannot pause in edit mode\"}";
            }

            EditorApplication.isPaused = !EditorApplication.isPaused;
            return JsonUtility.ToJson(new PauseResponse
            {
                success = true,
                isPaused = EditorApplication.isPaused
            });
        }

        private static string HandleStep(HttpListenerRequest request, RequestContext ctx)
        {
            if (request.HttpMethod != "POST")
            {
                ctx.StatusCode = 405;
                return "{\"error\":\"Method not allowed. Use POST.\"}";
            }

            if (!EditorApplication.isPlaying)
            {
                ctx.StatusCode = 409;
                return "{\"error\":\"Cannot step in edit mode\"}";
            }

            EditorApplication.Step();
            return "{\"success\":true,\"message\":\"Stepped one frame\"}";
        }

        private static string HandleLoadScene(HttpListenerRequest request, RequestContext ctx)
        {
            if (request.HttpMethod != "POST")
            {
                ctx.StatusCode = 405;
                return "{\"error\":\"Method not allowed. Use POST.\"}";
            }

            string scenePath = request.QueryString["path"];
            string additiveStr = request.QueryString["additive"];
            bool additive = additiveStr == "true" || additiveStr == "1";

            if (string.IsNullOrEmpty(scenePath))
            {
                ctx.StatusCode = 400;
                return "{\"error\":\"Missing 'path' parameter\"}";
            }

            if (EditorApplication.isPlaying)
            {
                ctx.StatusCode = 409;
                return "{\"error\":\"Cannot load scene in play mode. Stop play mode first.\"}";
            }

            var currentScene = EditorSceneManager.GetActiveScene();
            if (currentScene.isDirty)
            {
                bool saved = EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo();
                if (!saved)
                {
                    ctx.StatusCode = 409;
                    return "{\"error\":\"Scene has unsaved changes and user cancelled\"}";
                }
            }

            var mode = additive ? OpenSceneMode.Additive : OpenSceneMode.Single;
            try
            {
                var scene = EditorSceneManager.OpenScene(scenePath, mode);
                return JsonUtility.ToJson(new SceneLoadResponse
                {
                    success = true,
                    sceneName = scene.name,
                    scenePath = scene.path
                });
            }
            catch (System.Exception ex)
            {
                ctx.StatusCode = 400;
                return "{\"error\":\"" + EscapeJson(ex.Message) + "\"}";
            }
        }

        private static string HandleListScenes(HttpListenerRequest request, RequestContext ctx)
        {
            var sb = new StringBuilder();
            sb.Append("{\"scenes\":[");

            int sceneCount = SceneManager.sceneCountInBuildSettings;
            for (int i = 0; i < sceneCount; i++)
            {
                string path = SceneUtility.GetScenePathByBuildIndex(i);
                if (i > 0) sb.Append(",");
                sb.Append("{\"index\":");
                sb.Append(i);
                sb.Append(",\"path\":\"");
                sb.Append(EscapeJson(path));
                sb.Append("\",\"name\":\"");
                sb.Append(EscapeJson(System.IO.Path.GetFileNameWithoutExtension(path)));
                sb.Append("\"}");
            }

            sb.Append("]}");
            return sb.ToString();
        }

        private static string EscapeJson(string s)
        {
            if (s == null) return "";
            return s.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\n", "\\n").Replace("\r", "\\r");
        }

        [System.Serializable]
        private class PlayModeStateResponse
        {
            public bool isPlaying;
            public bool isPaused;
            public bool isCompiling;
        }

        [System.Serializable]
        private class PauseResponse
        {
            public bool success;
            public bool isPaused;
        }

        [System.Serializable]
        private class SceneLoadResponse
        {
            public bool success;
            public string sceneName;
            public string scenePath;
        }
    }
}

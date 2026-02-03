using System.Collections.Generic;
using System.Net;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace UnityFlow.Bridge.Handlers
{
    public static class HierarchyHandler
    {
        public static void Register(UnityFlowHttpServer server)
        {
            server.RegisterRoute("/api/hierarchy", HandleHierarchy);
        }

        private static string HandleHierarchy(HttpListenerRequest request, RequestContext ctx)
        {
            string scenePath = request.QueryString["scene"];
            Scene scene;

            if (!string.IsNullOrEmpty(scenePath))
            {
                scene = SceneManager.GetSceneByPath(scenePath);
                if (!scene.IsValid() || !scene.isLoaded)
                {
                    ctx.StatusCode = 404;
                    return "{\"error\":\"scene not found or not loaded\"}";
                }
            }
            else
            {
                scene = EditorSceneManager.GetActiveScene();
            }

            var rootObjects = scene.GetRootGameObjects();
            var sb = new StringBuilder();
            sb.Append("{\"scene\":\"");
            sb.Append(EscapeJson(scene.name));
            sb.Append("\",\"path\":\"");
            sb.Append(EscapeJson(scene.path));
            sb.Append("\",\"rootCount\":");
            sb.Append(rootObjects.Length);
            sb.Append(",\"children\":[");

            for (int i = 0; i < rootObjects.Length; i++)
            {
                if (i > 0) sb.Append(",");
                SerializeGameObject(rootObjects[i], sb, 0);
            }

            sb.Append("]}");
            return sb.ToString();
        }

        private static void SerializeGameObject(GameObject go, StringBuilder sb, int depth)
        {
            sb.Append("{\"name\":\"");
            sb.Append(EscapeJson(go.name));
            sb.Append("\",\"instanceId\":");
            sb.Append(go.GetInstanceID());
            sb.Append(",\"active\":");
            sb.Append(go.activeSelf ? "true" : "false");
            sb.Append(",\"tag\":\"");
            sb.Append(EscapeJson(go.tag));
            sb.Append("\",\"layer\":");
            sb.Append(go.layer);

            var components = go.GetComponents<Component>();
            sb.Append(",\"components\":[");
            bool first = true;
            foreach (var comp in components)
            {
                if (comp == null) continue;
                if (!first) sb.Append(",");
                first = false;
                sb.Append("\"");
                sb.Append(comp.GetType().Name);
                sb.Append("\"");
            }
            sb.Append("]");

            if (depth < 20 && go.transform.childCount > 0)
            {
                sb.Append(",\"children\":[");
                for (int i = 0; i < go.transform.childCount; i++)
                {
                    if (i > 0) sb.Append(",");
                    SerializeGameObject(go.transform.GetChild(i).gameObject, sb, depth + 1);
                }
                sb.Append("]");
            }
            else if (go.transform.childCount > 0)
            {
                sb.Append(",\"childCount\":");
                sb.Append(go.transform.childCount);
            }

            sb.Append("}");
        }

        private static string EscapeJson(string s)
        {
            if (s == null) return "";
            return s.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\n", "\\n").Replace("\r", "\\r");
        }
    }
}

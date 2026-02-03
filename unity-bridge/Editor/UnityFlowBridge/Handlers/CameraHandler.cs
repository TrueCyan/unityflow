using System.Globalization;
using System.Net;
using UnityEditor;
using UnityEngine;

namespace UnityFlow.Bridge.Handlers
{
    public static class CameraHandler
    {
        public static void Register(UnityFlowHttpServer server)
        {
            server.RegisterRoute("/api/camera/scene_view", HandleSceneView);
            server.RegisterRoute("/api/camera/frame_object", HandleFrameObject);
        }

        private static string HandleSceneView(HttpListenerRequest request, RequestContext ctx)
        {
            var sceneView = SceneView.lastActiveSceneView;
            if (sceneView == null)
            {
                ctx.StatusCode = 404;
                return "{\"error\":\"No Scene View available\"}";
            }

            if (request.HttpMethod == "POST")
            {
                return HandleSetSceneView(request, ctx, sceneView);
            }

            var pivot = sceneView.pivot;
            var rotation = sceneView.rotation.eulerAngles;

            return JsonUtility.ToJson(new SceneViewCameraResponse
            {
                pivotX = pivot.x,
                pivotY = pivot.y,
                pivotZ = pivot.z,
                rotationX = rotation.x,
                rotationY = rotation.y,
                rotationZ = rotation.z,
                size = sceneView.size,
                orthographic = sceneView.orthographic,
                is2D = sceneView.in2DMode
            });
        }

        private static string HandleSetSceneView(HttpListenerRequest request, RequestContext ctx, SceneView sceneView)
        {
            string pivotXStr = request.QueryString["pivotX"];
            string pivotYStr = request.QueryString["pivotY"];
            string pivotZStr = request.QueryString["pivotZ"];
            string rotXStr = request.QueryString["rotationX"];
            string rotYStr = request.QueryString["rotationY"];
            string rotZStr = request.QueryString["rotationZ"];
            string sizeStr = request.QueryString["size"];
            string orthoStr = request.QueryString["orthographic"];

            if (!string.IsNullOrEmpty(pivotXStr) || !string.IsNullOrEmpty(pivotYStr) || !string.IsNullOrEmpty(pivotZStr))
            {
                var current = sceneView.pivot;
                sceneView.pivot = new Vector3(
                    ParseFloat(pivotXStr, current.x),
                    ParseFloat(pivotYStr, current.y),
                    ParseFloat(pivotZStr, current.z)
                );
            }

            if (!string.IsNullOrEmpty(rotXStr) || !string.IsNullOrEmpty(rotYStr) || !string.IsNullOrEmpty(rotZStr))
            {
                var current = sceneView.rotation.eulerAngles;
                sceneView.rotation = Quaternion.Euler(
                    ParseFloat(rotXStr, current.x),
                    ParseFloat(rotYStr, current.y),
                    ParseFloat(rotZStr, current.z)
                );
            }

            if (!string.IsNullOrEmpty(sizeStr))
            {
                sceneView.size = ParseFloat(sizeStr, sceneView.size);
            }

            if (!string.IsNullOrEmpty(orthoStr))
            {
                sceneView.orthographic = orthoStr == "true" || orthoStr == "1";
            }

            sceneView.Repaint();

            var pivot = sceneView.pivot;
            var rotation = sceneView.rotation.eulerAngles;

            return JsonUtility.ToJson(new SceneViewCameraResponse
            {
                pivotX = pivot.x,
                pivotY = pivot.y,
                pivotZ = pivot.z,
                rotationX = rotation.x,
                rotationY = rotation.y,
                rotationZ = rotation.z,
                size = sceneView.size,
                orthographic = sceneView.orthographic,
                is2D = sceneView.in2DMode
            });
        }

        private static string HandleFrameObject(HttpListenerRequest request, RequestContext ctx)
        {
            if (request.HttpMethod != "POST")
            {
                ctx.StatusCode = 405;
                return "{\"error\":\"Method not allowed. Use POST.\"}";
            }

            var sceneView = SceneView.lastActiveSceneView;
            if (sceneView == null)
            {
                ctx.StatusCode = 404;
                return "{\"error\":\"No Scene View available\"}";
            }

            string path = request.QueryString["path"];
            string idStr = request.QueryString["id"];

            GameObject target = null;

            if (!string.IsNullOrEmpty(idStr) && int.TryParse(idStr, out int instanceId))
            {
                target = EditorUtility.InstanceIDToObject(instanceId) as GameObject;
            }
            else if (!string.IsNullOrEmpty(path))
            {
                target = GameObject.Find(path);
            }

            if (target == null)
            {
                ctx.StatusCode = 404;
                return "{\"error\":\"Object not found\"}";
            }

            Selection.activeGameObject = target;
            sceneView.FrameSelected();

            var pivot = sceneView.pivot;

            return JsonUtility.ToJson(new FrameObjectResponse
            {
                success = true,
                targetName = target.name,
                pivotX = pivot.x,
                pivotY = pivot.y,
                pivotZ = pivot.z
            });
        }

        private static float ParseFloat(string s, float defaultValue)
        {
            if (string.IsNullOrEmpty(s)) return defaultValue;
            if (float.TryParse(s, NumberStyles.Float, CultureInfo.InvariantCulture, out float result))
                return result;
            return defaultValue;
        }

        [System.Serializable]
        private class SceneViewCameraResponse
        {
            public float pivotX;
            public float pivotY;
            public float pivotZ;
            public float rotationX;
            public float rotationY;
            public float rotationZ;
            public float size;
            public bool orthographic;
            public bool is2D;
        }

        [System.Serializable]
        private class FrameObjectResponse
        {
            public bool success;
            public string targetName;
            public float pivotX;
            public float pivotY;
            public float pivotZ;
        }
    }
}

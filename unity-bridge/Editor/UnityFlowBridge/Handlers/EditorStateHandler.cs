using System.Net;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace UnityFlow.Bridge.Handlers
{
    public static class EditorStateHandler
    {
        public static void Register(UnityFlowHttpServer server)
        {
            server.RegisterRoute("/api/ping", HandlePing);
            server.RegisterRoute("/api/editor_state", HandleEditorState);
        }

        private static string HandlePing(HttpListenerRequest request, RequestContext ctx)
        {
            return JsonUtility.ToJson(new PingResponse
            {
                status = "ok",
                unity_version = Application.unityVersion,
                project_name = Application.productName
            });
        }

        private static string HandleEditorState(HttpListenerRequest request, RequestContext ctx)
        {
            var activeScene = EditorSceneManager.GetActiveScene();
            string selectionNames = "";
            if (Selection.gameObjects != null && Selection.gameObjects.Length > 0)
            {
                var names = new string[Selection.gameObjects.Length];
                for (int i = 0; i < names.Length; i++)
                    names[i] = Selection.gameObjects[i].name;
                selectionNames = string.Join(",", names);
            }

            return JsonUtility.ToJson(new EditorStateResponse
            {
                playMode = EditorApplication.isPlaying,
                isPaused = EditorApplication.isPaused,
                isCompiling = EditorApplication.isCompiling,
                sceneName = activeScene.name,
                scenePath = activeScene.path,
                sceneIsDirty = activeScene.isDirty,
                selection = selectionNames
            });
        }

        [System.Serializable]
        private class PingResponse
        {
            public string status;
            public string unity_version;
            public string project_name;
        }

        [System.Serializable]
        private class EditorStateResponse
        {
            public bool playMode;
            public bool isPaused;
            public bool isCompiling;
            public string sceneName;
            public string scenePath;
            public bool sceneIsDirty;
            public string selection;
        }
    }
}

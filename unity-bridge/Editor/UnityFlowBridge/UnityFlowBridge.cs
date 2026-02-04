using System;
using System.Collections.Generic;
using UnityEditor;
using UnityEngine;
using UnityFlow.Bridge.Handlers;

namespace UnityFlow.Bridge
{
    [InitializeOnLoad]
    public class UnityFlowBridgeBootstrap
    {
        private const string AutoStartPref = "UnityFlowBridge_AutoStart";
        private const string PortPref = "UnityFlowBridge_Port";
        private const int DefaultPort = 29184;

        static UnityFlowBridgeBootstrap()
        {
            if (EditorPrefs.GetBool(AutoStartPref, true))
            {
                EditorApplication.delayCall += () =>
                {
                    int port = EditorPrefs.GetInt(PortPref, DefaultPort);
                    UnityFlowBridgeWindow.StartServer(port);
                };
            }
        }
    }

    public class UnityFlowBridgeWindow : EditorWindow
    {
        private const string PortPref = "UnityFlowBridge_Port";
        private const string AutoStartPref = "UnityFlowBridge_AutoStart";
        private const int DefaultPort = 29184;
        private const int MaxLogEntries = 100;

        private static UnityFlowHttpServer _server;
        private static readonly List<RequestLogEntry> _requestLog = new();
        private static bool _initialized;

        private int _portInput;
        private bool _autoStart;
        private Vector2 _logScrollPos;
        private string _quickTestResult;
        private volatile bool _testInProgress;

        [MenuItem("Window/UnityFlow Bridge")]
        public static void ShowWindow()
        {
            GetWindow<UnityFlowBridgeWindow>("UnityFlow Bridge");
        }

        public static void StartServer(int port)
        {
            if (_server != null && _server.IsRunning)
                _server.Stop();

            _server = new UnityFlowHttpServer();
            _server.OnRequestLogged += OnRequestLogged;

            EditorStateHandler.Register(_server);
            ConsoleLogHandler.Register(_server);
            HierarchyHandler.Register(_server);
            InspectorHandler.Register(_server);
            ScreenshotHandler.Register(_server);
            AnimationHandler.Register(_server);
            PlayModeHandler.Register(_server);
            CameraHandler.Register(_server);

            _server.Start(port);
            _initialized = true;
        }

        public static void StopServer()
        {
            if (_server != null)
            {
                _server.Stop();
                ConsoleLogHandler.Unregister();
                _server = null;
            }
            _initialized = false;
        }

        private static void OnRequestLogged(RequestLogEntry entry)
        {
            lock (_requestLog)
            {
                _requestLog.Add(entry);
                while (_requestLog.Count > MaxLogEntries)
                    _requestLog.RemoveAt(0);
            }
        }

        private void OnEnable()
        {
            _portInput = EditorPrefs.GetInt(PortPref, DefaultPort);
            _autoStart = EditorPrefs.GetBool(AutoStartPref, true);
        }

        private void OnDisable()
        {
        }

        private void OnGUI()
        {
            bool isRunning = _server != null && _server.IsRunning;

            DrawStatus(isRunning);
            EditorGUILayout.Space(8);
            DrawControls(isRunning);
            EditorGUILayout.Space(8);
            DrawConnectionLog();
            EditorGUILayout.Space(8);
            DrawQuickTest(isRunning);
            EditorGUILayout.Space(4);
            DrawStatistics(isRunning);

            if (isRunning)
                Repaint();
        }

        private void DrawStatus(bool isRunning)
        {
            EditorGUILayout.BeginHorizontal();
            var statusColor = isRunning ? Color.green : Color.red;
            var prevColor = GUI.color;
            GUI.color = statusColor;
            GUILayout.Label("\u25CF", GUILayout.Width(16));
            GUI.color = prevColor;

            if (isRunning)
                EditorGUILayout.LabelField($"Listening on port {_server.Port}", EditorStyles.boldLabel);
            else
                EditorGUILayout.LabelField("Stopped", EditorStyles.boldLabel);

            EditorGUILayout.EndHorizontal();
        }

        private void DrawControls(bool isRunning)
        {
            EditorGUILayout.BeginHorizontal();

            EditorGUI.BeginDisabledGroup(isRunning);
            EditorGUILayout.LabelField("Port:", GUILayout.Width(35));
            _portInput = EditorGUILayout.IntField(_portInput, GUILayout.Width(60));
            EditorGUI.EndDisabledGroup();

            var newAutoStart = EditorGUILayout.ToggleLeft("Auto Start", _autoStart, GUILayout.Width(85));
            if (newAutoStart != _autoStart)
            {
                _autoStart = newAutoStart;
                EditorPrefs.SetBool(AutoStartPref, _autoStart);
            }

            GUILayout.FlexibleSpace();

            if (isRunning)
            {
                if (GUILayout.Button("Stop", GUILayout.Width(60)))
                    StopServer();
            }
            else
            {
                if (GUILayout.Button("Start", GUILayout.Width(60)))
                {
                    EditorPrefs.SetInt(PortPref, _portInput);
                    StartServer(_portInput);
                }
            }

            EditorGUILayout.EndHorizontal();
        }

        private void DrawConnectionLog()
        {
            EditorGUILayout.LabelField("Connection Log", EditorStyles.boldLabel);
            var rect = EditorGUILayout.GetControlRect(false, 150);
            GUI.Box(rect, GUIContent.none);

            var innerRect = new Rect(rect.x + 2, rect.y + 2, rect.width - 4, rect.height - 4);

            RequestLogEntry[] entries;
            lock (_requestLog)
            {
                entries = _requestLog.ToArray();
            }

            float lineHeight = EditorGUIUtility.singleLineHeight;
            var viewRect = new Rect(0, 0, innerRect.width - 16, entries.Length * lineHeight);

            _logScrollPos = GUI.BeginScrollView(innerRect, _logScrollPos, viewRect);

            for (int i = entries.Length - 1; i >= 0; i--)
            {
                var entry = entries[i];
                int row = entries.Length - 1 - i;
                var lineRect = new Rect(0, row * lineHeight, viewRect.width, lineHeight);

                string time = entry.Timestamp.ToString("HH:mm:ss");
                string duration = entry.DurationMs < 1000
                    ? $"{entry.DurationMs:F0}ms"
                    : $"{entry.DurationMs / 1000:F1}s";

                var color = entry.StatusCode >= 400 ? Color.red : Color.white;
                var style = new GUIStyle(EditorStyles.miniLabel) { normal = { textColor = color } };
                GUI.Label(lineRect, $"  {time}  {entry.Path,-35} {entry.StatusCode}  {duration,8}", style);
            }

            GUI.EndScrollView();
        }

        private void RunQuickTestAsync(string url, System.Action<byte[], Exception> onComplete)
        {
            if (_testInProgress) return;
            _testInProgress = true;
            _quickTestResult = "Testing...";
            System.Threading.ThreadPool.QueueUserWorkItem(_ =>
            {
                try
                {
                    using var client = new System.Net.WebClient();
                    byte[] data = client.DownloadData(url);
                    EditorApplication.delayCall += () =>
                    {
                        onComplete(data, null);
                        _testInProgress = false;
                    };
                }
                catch (Exception ex)
                {
                    EditorApplication.delayCall += () =>
                    {
                        onComplete(null, ex);
                        _testInProgress = false;
                    };
                }
            });
        }

        private void DrawQuickTest(bool isRunning)
        {
            EditorGUILayout.LabelField("Quick Test", EditorStyles.boldLabel);
            EditorGUI.BeginDisabledGroup(!isRunning || _testInProgress);

            EditorGUILayout.BeginHorizontal();

            if (GUILayout.Button("Ping Self"))
            {
                var url = $"http://localhost:{_server.Port}/api/ping";
                RunQuickTestAsync(url, (data, ex) =>
                {
                    if (ex != null)
                        _quickTestResult = $"Error: {ex.Message}";
                    else
                        _quickTestResult = System.Text.Encoding.UTF8.GetString(data);
                });
            }

            if (GUILayout.Button("Capture Screenshot"))
            {
                var url = $"http://localhost:{_server.Port}/api/screenshot?view=scene&width=512&height=384";
                RunQuickTestAsync(url, (data, ex) =>
                {
                    if (ex != null)
                    {
                        _quickTestResult = $"Error: {ex.Message}";
                        return;
                    }
                    var tex = new Texture2D(2, 2);
                    tex.LoadImage(data);
                    ShowTexturePreview(tex);
                    _quickTestResult = $"Screenshot: {tex.width}x{tex.height}";
                });
            }

            if (GUILayout.Button("Show Hierarchy"))
            {
                var url = $"http://localhost:{_server.Port}/api/hierarchy";
                RunQuickTestAsync(url, (data, ex) =>
                {
                    if (ex != null)
                    {
                        _quickTestResult = $"Error: {ex.Message}";
                        return;
                    }
                    _quickTestResult = System.Text.Encoding.UTF8.GetString(data);
                    if (_quickTestResult.Length > 500)
                        _quickTestResult = _quickTestResult.Substring(0, 500) + "...";
                });
            }

            EditorGUILayout.EndHorizontal();
            EditorGUI.EndDisabledGroup();

            if (!string.IsNullOrEmpty(_quickTestResult))
            {
                EditorGUILayout.Space(4);
                EditorGUILayout.HelpBox(_quickTestResult, MessageType.Info);
            }
        }

        private void DrawStatistics(bool isRunning)
        {
            if (!isRunning || _server == null) return;

            EditorGUILayout.BeginHorizontal();
            EditorGUILayout.LabelField($"Total Requests: {_server.TotalRequests}", GUILayout.Width(150));
            EditorGUILayout.LabelField($"Errors: {_server.ErrorCount}", GUILayout.Width(100));

            if (_server.StartTime.HasValue)
            {
                var uptime = DateTime.Now - _server.StartTime.Value;
                string uptimeStr;
                if (uptime.TotalHours >= 1)
                    uptimeStr = $"{uptime.Hours}h {uptime.Minutes}m";
                else if (uptime.TotalMinutes >= 1)
                    uptimeStr = $"{uptime.Minutes}m {uptime.Seconds}s";
                else
                    uptimeStr = $"{uptime.Seconds}s";
                EditorGUILayout.LabelField($"Uptime: {uptimeStr}");
            }

            EditorGUILayout.EndHorizontal();
        }

        private static void ShowTexturePreview(Texture2D tex)
        {
            var window = GetWindow<TexturePreviewWindow>("Screenshot Preview");
            window.SetTexture(tex);
            window.Show();
        }
    }

    public class TexturePreviewWindow : EditorWindow
    {
        private Texture2D _texture;

        public void SetTexture(Texture2D tex)
        {
            _texture = tex;
        }

        private void OnGUI()
        {
            if (_texture == null) return;

            var rect = new Rect(0, 0, position.width, position.height);
            float aspect = (float)_texture.width / _texture.height;
            float windowAspect = rect.width / rect.height;

            Rect drawRect;
            if (aspect > windowAspect)
            {
                float h = rect.width / aspect;
                drawRect = new Rect(0, (rect.height - h) / 2, rect.width, h);
            }
            else
            {
                float w = rect.height * aspect;
                drawRect = new Rect((rect.width - w) / 2, 0, w, rect.height);
            }

            GUI.DrawTexture(drawRect, _texture, ScaleMode.ScaleToFit);
        }
    }
}

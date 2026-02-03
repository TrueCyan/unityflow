using System;
using System.Collections.Generic;
using System.Net;
using System.Text;
using UnityEngine;

namespace UnityFlow.Bridge.Handlers
{
    public static class ConsoleLogHandler
    {
        private static readonly List<LogEntry> _logs = new();
        private static readonly object _lock = new object();
        private static bool _hooked;
        private const int MaxLogs = 1000;

        public static void Register(UnityFlowHttpServer server)
        {
            if (!_hooked)
            {
                Application.logMessageReceived += OnLogMessage;
                _hooked = true;
            }
            server.RegisterRoute("/api/console", HandleConsole);
        }

        public static void Unregister()
        {
            if (_hooked)
            {
                Application.logMessageReceived -= OnLogMessage;
                _hooked = false;
            }
        }

        private static void OnLogMessage(string condition, string stackTrace, LogType type)
        {
            lock (_lock)
            {
                _logs.Add(new LogEntry
                {
                    message = condition,
                    stackTrace = stackTrace,
                    type = type.ToString(),
                    timestamp = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss.fff")
                });
                while (_logs.Count > MaxLogs)
                    _logs.RemoveAt(0);
            }
        }

        private static string HandleConsole(HttpListenerRequest request, RequestContext ctx)
        {
            string severity = request.QueryString["severity"] ?? "all";
            int count = 100;
            if (int.TryParse(request.QueryString["count"], out int c))
                count = Mathf.Clamp(c, 1, MaxLogs);
            bool clear = request.QueryString["clear"] == "true";

            lock (_lock)
            {
                var filtered = new List<LogEntry>();
                for (int i = _logs.Count - 1; i >= 0 && filtered.Count < count; i--)
                {
                    var log = _logs[i];
                    if (severity == "all" || MatchesSeverity(log.type, severity))
                        filtered.Add(log);
                }
                filtered.Reverse();

                if (clear)
                    _logs.Clear();

                return ToJsonArray(filtered);
            }
        }

        private static bool MatchesSeverity(string logType, string severity)
        {
            return severity switch
            {
                "error" => logType == "Error" || logType == "Exception" || logType == "Assert",
                "warning" => logType == "Warning",
                "log" => logType == "Log",
                _ => true
            };
        }

        private static string ToJsonArray(List<LogEntry> entries)
        {
            var sb = new StringBuilder();
            sb.Append("{\"logs\":[");
            for (int i = 0; i < entries.Count; i++)
            {
                if (i > 0) sb.Append(",");
                sb.Append(JsonUtility.ToJson(entries[i]));
            }
            sb.Append("],\"total\":");
            lock (_lock) { sb.Append(_logs.Count); }
            sb.Append("}");
            return sb.ToString();
        }

        [Serializable]
        private class LogEntry
        {
            public string message;
            public string stackTrace;
            public string type;
            public string timestamp;
        }
    }
}

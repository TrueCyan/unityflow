using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Text;
using System.Threading;
using UnityEditor;
using UnityEngine;

namespace UnityFlow.Bridge
{
    public class UnityFlowHttpServer
    {
        private HttpListener _listener;
        private Thread _listenerThread;
        private volatile bool _isRunning;
        private int _port;

        public bool IsRunning => _isRunning;
        public int Port => _port;
        public int TotalRequests { get; private set; }
        public int ErrorCount { get; private set; }
        public DateTime? StartTime { get; private set; }

        public event Action<RequestLogEntry> OnRequestLogged;

        private readonly Dictionary<string, Func<HttpListenerRequest, RequestContext, string>> _routes = new();
        private readonly Dictionary<string, Func<HttpListenerRequest, RequestContext, byte[]>> _binaryRoutes = new();

        public void RegisterRoute(string path, Func<HttpListenerRequest, RequestContext, string> handler)
        {
            _routes[path] = handler;
        }

        public void RegisterBinaryRoute(string path, Func<HttpListenerRequest, RequestContext, byte[]> handler)
        {
            _binaryRoutes[path] = handler;
        }

        public void Start(int port)
        {
            if (_isRunning) return;

            _port = port;
            _listener = new HttpListener();
            _listener.Prefixes.Add($"http://localhost:{port}/");
            _listener.Prefixes.Add($"http://127.0.0.1:{port}/");

            try
            {
                _listener.Start();
                _isRunning = true;
                StartTime = DateTime.Now;
                TotalRequests = 0;
                ErrorCount = 0;

                _listenerThread = new Thread(ListenLoop) { IsBackground = true, Name = "UnityFlowBridge" };
                _listenerThread.Start();

                Debug.Log($"[UnityFlow Bridge] Listening on port {port}");
            }
            catch (Exception ex)
            {
                Debug.LogError($"[UnityFlow Bridge] Failed to start: {ex.Message}");
                _isRunning = false;
            }
        }

        public void Stop()
        {
            if (!_isRunning) return;

            _isRunning = false;
            try
            {
                _listener?.Stop();
                _listener?.Close();
            }
            catch (Exception) { }

            _listenerThread = null;
            StartTime = null;
            Debug.Log("[UnityFlow Bridge] Stopped");
        }

        private void ListenLoop()
        {
            while (_isRunning)
            {
                try
                {
                    var context = _listener.GetContext();
                    ThreadPool.QueueUserWorkItem(_ => HandleRequest(context));
                }
                catch (HttpListenerException)
                {
                    break;
                }
                catch (ObjectDisposedException)
                {
                    break;
                }
                catch (Exception ex)
                {
                    if (_isRunning)
                        Debug.LogError($"[UnityFlow Bridge] Listener error: {ex.Message}");
                }
            }
        }

        private void HandleRequest(HttpListenerContext context)
        {
            var stopwatch = System.Diagnostics.Stopwatch.StartNew();
            var request = context.Request;
            var response = context.Response;
            var path = request.Url.AbsolutePath;
            int statusCode = 200;

            try
            {
                TotalRequests++;

                response.AddHeader("Access-Control-Allow-Origin", "*");
                response.AddHeader("Access-Control-Allow-Methods", "GET, OPTIONS");
                response.AddHeader("Access-Control-Allow-Headers", "Content-Type");

                if (request.HttpMethod == "OPTIONS")
                {
                    response.StatusCode = 204;
                    response.Close();
                    return;
                }

                if (_binaryRoutes.TryGetValue(path, out var binaryHandler))
                {
                    var reqCtx = new RequestContext();
                    byte[] data = ExecuteOnMainThread(() => binaryHandler(request, reqCtx));

                    response.ContentType = reqCtx.ContentType ?? "application/octet-stream";
                    response.StatusCode = reqCtx.StatusCode;
                    statusCode = reqCtx.StatusCode;
                    response.ContentLength64 = data.Length;
                    response.OutputStream.Write(data, 0, data.Length);
                }
                else if (_routes.TryGetValue(path, out var handler))
                {
                    var reqCtx = new RequestContext();
                    string result = ExecuteOnMainThread(() => handler(request, reqCtx));

                    response.ContentType = "application/json; charset=utf-8";
                    response.StatusCode = reqCtx.StatusCode;
                    statusCode = reqCtx.StatusCode;
                    byte[] buffer = Encoding.UTF8.GetBytes(result);
                    response.ContentLength64 = buffer.Length;
                    response.OutputStream.Write(buffer, 0, buffer.Length);
                }
                else
                {
                    statusCode = 404;
                    response.StatusCode = 404;
                    byte[] buffer = Encoding.UTF8.GetBytes("{\"error\":\"not found\"}");
                    response.ContentType = "application/json";
                    response.ContentLength64 = buffer.Length;
                    response.OutputStream.Write(buffer, 0, buffer.Length);
                }
            }
            catch (Exception ex)
            {
                statusCode = 500;
                ErrorCount++;
                try
                {
                    response.StatusCode = 500;
                    byte[] buffer = Encoding.UTF8.GetBytes($"{{\"error\":\"{EscapeJson(ex.Message)}\"}}");
                    response.ContentType = "application/json";
                    response.ContentLength64 = buffer.Length;
                    response.OutputStream.Write(buffer, 0, buffer.Length);
                }
                catch (Exception) { }
            }
            finally
            {
                try { response.Close(); } catch (Exception) { }

                stopwatch.Stop();
                OnRequestLogged?.Invoke(new RequestLogEntry
                {
                    Timestamp = DateTime.Now,
                    Path = path,
                    StatusCode = statusCode,
                    DurationMs = stopwatch.Elapsed.TotalMilliseconds
                });
            }
        }

        private T ExecuteOnMainThread<T>(Func<T> action)
        {
            if (Thread.CurrentThread.ManagedThreadId == 1)
                return action();

            T result = default;
            Exception exception = null;
            var resetEvent = new ManualResetEventSlim(false);

            EditorApplication.delayCall += () =>
            {
                try
                {
                    result = action();
                }
                catch (Exception ex)
                {
                    exception = ex;
                }
                finally
                {
                    resetEvent.Set();
                }
            };

            if (!resetEvent.Wait(TimeSpan.FromSeconds(30)))
                throw new TimeoutException("Main thread dispatch timed out after 30 seconds");

            if (exception != null)
                throw exception;

            return result;
        }

        private static string EscapeJson(string s)
        {
            if (s == null) return "";
            return s.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\n", "\\n").Replace("\r", "\\r");
        }
    }

    public class RequestContext
    {
        public int StatusCode { get; set; } = 200;
        public string ContentType { get; set; }
    }

    public struct RequestLogEntry
    {
        public DateTime Timestamp;
        public string Path;
        public int StatusCode;
        public double DurationMs;
    }
}

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;
using UnityEngine;

namespace UnityFlow.Bridge
{
    [Serializable]
    public class InstanceEntry
    {
        public int port;
        public string projectPath;
        public int pid;
        public string startedAt;
    }

    [Serializable]
    internal class InstanceEntryList
    {
        public List<InstanceEntry> entries = new();
    }

    public static class InstanceRegistry
    {
        private static readonly string RegistryDir =
            Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
                ".unityflow");

        private static readonly string RegistryPath =
            Path.Combine(RegistryDir, "instances.json");

        public static void Register(int port, string dataPath)
        {
            var projectPath = Path.GetDirectoryName(dataPath);
            if (projectPath != null)
                projectPath = projectPath.Replace("\\", "/");

            var entry = new InstanceEntry
            {
                port = port,
                projectPath = projectPath,
                pid = Process.GetCurrentProcess().Id,
                startedAt = DateTime.UtcNow.ToString("o")
            };

            try
            {
                var entries = ReadEntries();
                PruneStale(entries);
                entries.RemoveAll(e => e.pid == entry.pid);
                entries.Add(entry);
                WriteEntries(entries);
            }
            catch (Exception ex)
            {
                UnityEngine.Debug.LogWarning($"[UnityFlow Bridge] Failed to write instance registry: {ex.Message}");
            }
        }

        public static void Unregister()
        {
            var pid = Process.GetCurrentProcess().Id;
            try
            {
                var entries = ReadEntries();
                entries.RemoveAll(e => e.pid == pid);
                WriteEntries(entries);
            }
            catch (Exception ex)
            {
                UnityEngine.Debug.LogWarning($"[UnityFlow Bridge] Failed to clean instance registry: {ex.Message}");
            }
        }

        internal static List<InstanceEntry> ReadEntries()
        {
            if (!File.Exists(RegistryPath))
                return new List<InstanceEntry>();

            var json = File.ReadAllText(RegistryPath, Encoding.UTF8);
            if (string.IsNullOrWhiteSpace(json))
                return new List<InstanceEntry>();

            var wrapped = $"{{\"entries\":{json}}}";
            var list = JsonUtility.FromJson<InstanceEntryList>(wrapped);
            return list?.entries ?? new List<InstanceEntry>();
        }

        internal static void WriteEntries(List<InstanceEntry> entries)
        {
            if (!Directory.Exists(RegistryDir))
                Directory.CreateDirectory(RegistryDir);

            var sb = new StringBuilder();
            sb.AppendLine("[");
            for (int i = 0; i < entries.Count; i++)
            {
                var e = entries[i];
                sb.Append("  ");
                sb.Append(JsonUtility.ToJson(e));
                if (i < entries.Count - 1) sb.Append(",");
                sb.AppendLine();
            }
            sb.Append("]");

            var tmpPath = RegistryPath + ".tmp";
            File.WriteAllText(tmpPath, sb.ToString(), Encoding.UTF8);
            if (File.Exists(RegistryPath))
                File.Delete(RegistryPath);
            File.Move(tmpPath, RegistryPath);
        }

        private static void PruneStale(List<InstanceEntry> entries)
        {
            entries.RemoveAll(e => !IsProcessAlive(e.pid));
        }

        private static bool IsProcessAlive(int pid)
        {
            try
            {
                var process = Process.GetProcessById(pid);
                return !process.HasExited;
            }
            catch
            {
                return false;
            }
        }
    }
}

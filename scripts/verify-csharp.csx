#!/usr/bin/env dotnet-script
#r "nuget: Microsoft.CodeAnalysis.CSharp, 4.8.0"

using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;

var unityEditorPath = Environment.GetEnvironmentVariable("UNITY_EDITOR_PATH")
    ?? @"E:\Unity\2021.3.56f2\Editor";
var managedPath = Path.Combine(unityEditorPath, "Data", "Managed");
var unityEnginePath = Path.Combine(managedPath, "UnityEngine");

var sourceDir = Args.Count > 0 ? Args[0] : "unity-bridge/Editor";

if (!Directory.Exists(sourceDir))
{
    Console.WriteLine($"Error: Source directory not found: {sourceDir}");
    Environment.Exit(1);
}

Console.WriteLine($"Unity Editor: {unityEditorPath}");
Console.WriteLine($"Source: {sourceDir}");
Console.WriteLine();

var csFiles = Directory.GetFiles(sourceDir, "*.cs", SearchOption.AllDirectories);
Console.WriteLine($"Found {csFiles.Length} C# files");

var syntaxTrees = csFiles
    .Select(f => CSharpSyntaxTree.ParseText(
        File.ReadAllText(f),
        CSharpParseOptions.Default.WithLanguageVersion(LanguageVersion.CSharp9),
        path: f))
    .ToList();

var references = new List<MetadataReference>
{
    MetadataReference.CreateFromFile(typeof(object).Assembly.Location),
    MetadataReference.CreateFromFile(typeof(Console).Assembly.Location),
    MetadataReference.CreateFromFile(Path.Combine(managedPath, "UnityEngine.dll")),
    MetadataReference.CreateFromFile(Path.Combine(managedPath, "UnityEditor.dll")),
};

var netstandardPath = Path.GetDirectoryName(typeof(object).Assembly.Location);
var runtimeDir = Path.GetDirectoryName(typeof(object).Assembly.Location);

foreach (var dll in new[] { "System.Runtime.dll", "System.Collections.dll", "System.Threading.dll",
    "System.Net.dll", "System.Net.Primitives.dll", "System.Net.Http.dll", "netstandard.dll",
    "System.Collections.Concurrent.dll", "System.Linq.dll" })
{
    var path = Path.Combine(runtimeDir, dll);
    if (File.Exists(path))
        references.Add(MetadataReference.CreateFromFile(path));
}

if (Directory.Exists(unityEnginePath))
{
    foreach (var dll in Directory.GetFiles(unityEnginePath, "*.dll"))
    {
        try { references.Add(MetadataReference.CreateFromFile(dll)); }
        catch { }
    }
}

var compilation = CSharpCompilation.Create(
    "UnityFlowBridge",
    syntaxTrees,
    references,
    new CSharpCompilationOptions(OutputKind.DynamicallyLinkedLibrary)
        .WithAllowUnsafe(false)
        .WithNullableContextOptions(NullableContextOptions.Disable));

var diagnostics = compilation.GetDiagnostics()
    .Where(d => d.Severity == DiagnosticSeverity.Error)
    .ToList();

if (diagnostics.Count == 0)
{
    Console.WriteLine();
    Console.ForegroundColor = ConsoleColor.Green;
    Console.WriteLine("✓ No compilation errors found");
    Console.ResetColor();
    Environment.Exit(0);
}
else
{
    Console.WriteLine();
    Console.ForegroundColor = ConsoleColor.Red;
    Console.WriteLine($"✗ Found {diagnostics.Count} compilation errors:");
    Console.ResetColor();
    Console.WriteLine();

    foreach (var diag in diagnostics.Take(50))
    {
        var location = diag.Location.GetLineSpan();
        var file = Path.GetFileName(location.Path);
        var line = location.StartLinePosition.Line + 1;
        Console.WriteLine($"  {file}:{line}: {diag.Id} {diag.GetMessage()}");
    }

    if (diagnostics.Count > 50)
        Console.WriteLine($"  ... and {diagnostics.Count - 50} more errors");

    Environment.Exit(1);
}

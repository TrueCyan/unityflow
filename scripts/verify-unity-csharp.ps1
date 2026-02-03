<#
.SYNOPSIS
    Verifies Unity C# code compilation using Roslyn.
.DESCRIPTION
    Compiles unity-bridge C# files against Unity DLLs to check for errors.
    Configure UNITY_EDITOR_PATH in .env.local or pass as parameter.
.PARAMETER UnityEditorPath
    Path to Unity Editor. If not provided, reads from .env.local or environment variable.
.PARAMETER SourcePath
    Path to C# source files (default: unity-bridge/Editor)
#>
param(
    [string]$UnityEditorPath = "",
    [string]$SourcePath = ""
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir

# Load Unity path from config
if (-not $UnityEditorPath) {
    # Check environment variable first
    $UnityEditorPath = $env:UNITY_EDITOR_PATH

    # Then check .env.local
    if (-not $UnityEditorPath) {
        $envLocalPath = Join-Path $repoRoot ".env.local"
        if (Test-Path $envLocalPath) {
            Get-Content $envLocalPath | ForEach-Object {
                if ($_ -match "^\s*UNITY_EDITOR_PATH\s*=\s*(.+)\s*$") {
                    $UnityEditorPath = $Matches[1].Trim()
                }
            }
        }
    }
}

# Show setup instructions if not configured
if (-not $UnityEditorPath) {
    Write-Host ""
    Write-Host "Unity Editor path not configured." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Setup instructions:" -ForegroundColor Cyan
    Write-Host "  1. Copy .env.local.example to .env.local"
    Write-Host "  2. Set UNITY_EDITOR_PATH to your Unity Editor path"
    Write-Host ""
    Write-Host "Example .env.local content:" -ForegroundColor Cyan
    Write-Host "  UNITY_EDITOR_PATH=E:\Unity\2021.3.56f2\Editor"
    Write-Host ""
    Write-Host "Or pass directly:" -ForegroundColor Cyan
    Write-Host "  .\scripts\verify-unity-csharp.ps1 -UnityEditorPath 'E:\Unity\2021.3.56f2\Editor'"
    Write-Host ""
    exit 1
}

# Find source path
if (-not $SourcePath) {
    $SourcePath = Join-Path $repoRoot "unity-bridge\Editor"
}

if (-not (Test-Path $SourcePath)) {
    Write-Host "Error: Source directory not found: $SourcePath" -ForegroundColor Red
    exit 1
}

$managedPath = Join-Path $UnityEditorPath "Data\Managed"
$unityEnginePath = Join-Path $managedPath "UnityEngine"

if (-not (Test-Path $managedPath)) {
    Write-Host "Error: Unity Managed path not found: $managedPath" -ForegroundColor Red
    Write-Host "Check that UNITY_EDITOR_PATH is correct in .env.local" -ForegroundColor Yellow
    exit 1
}

Write-Host "Unity Editor: $UnityEditorPath"
Write-Host "Source: $SourcePath"
Write-Host ""

# Create temp project
$tempDir = Join-Path $env:TEMP "unity-csharp-verify-$(Get-Random)"
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

try {
    # Create project file
    $csproj = @"
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>netstandard2.1</TargetFramework>
    <LangVersion>9.0</LangVersion>
    <Nullable>disable</Nullable>
    <TreatWarningsAsErrors>false</TreatWarningsAsErrors>
    <NoWarn>CS0649;CS0169;CS0414</NoWarn>
  </PropertyGroup>
  <ItemGroup>
    <Reference Include="UnityEngine">
      <HintPath>$managedPath\UnityEngine.dll</HintPath>
    </Reference>
    <Reference Include="UnityEditor">
      <HintPath>$managedPath\UnityEditor.dll</HintPath>
    </Reference>
"@

    # Add UnityEngine module DLLs
    if (Test-Path $unityEnginePath) {
        Get-ChildItem -Path $unityEnginePath -Filter "*.dll" | ForEach-Object {
            $dllName = [System.IO.Path]::GetFileNameWithoutExtension($_.Name)
            $csproj += @"

    <Reference Include="$dllName">
      <HintPath>$($_.FullName)</HintPath>
    </Reference>
"@
        }
    }

    $csproj += @"

  </ItemGroup>
</Project>
"@

    $csprojPath = Join-Path $tempDir "UnityFlowBridge.csproj"
    Set-Content -Path $csprojPath -Value $csproj -Encoding UTF8

    # Copy source files
    $csFiles = Get-ChildItem -Path $SourcePath -Filter "*.cs" -Recurse
    Write-Host "Found $($csFiles.Count) C# files"

    foreach ($file in $csFiles) {
        $relativePath = $file.FullName.Substring($SourcePath.Length + 1)
        $destPath = Join-Path $tempDir $relativePath
        $destDir = Split-Path -Parent $destPath
        if (-not (Test-Path $destDir)) {
            New-Item -ItemType Directory -Path $destDir -Force | Out-Null
        }
        Copy-Item -Path $file.FullName -Destination $destPath
    }

    # Build
    Write-Host ""
    Write-Host "Compiling..." -ForegroundColor Cyan

    $buildOutput = & dotnet build $csprojPath --nologo --verbosity quiet 2>&1
    $exitCode = $LASTEXITCODE

    if ($exitCode -eq 0) {
        Write-Host ""
        Write-Host "OK No compilation errors" -ForegroundColor Green
        exit 0
    } else {
        Write-Host ""
        Write-Host "Compilation errors found:" -ForegroundColor Red
        Write-Host ""

        $buildOutput | ForEach-Object {
            $line = $_.ToString()
            if ($line -match "error CS\d+") {
                # Extract just filename and error
                if ($line -match "([^\\]+\.cs)\((\d+),(\d+)\):\s*error\s*(CS\d+):\s*(.+)$") {
                    Write-Host "  $($Matches[1]):$($Matches[2]): $($Matches[4]) $($Matches[5])" -ForegroundColor Red
                } else {
                    Write-Host "  $line" -ForegroundColor Red
                }
            }
        }
        exit 1
    }
}
finally {
    # Cleanup
    if (Test-Path $tempDir) {
        Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

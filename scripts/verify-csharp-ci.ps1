<#
.SYNOPSIS
    CI script for verifying Unity C# code compilation using stubs.
.DESCRIPTION
    Compiles unity-bridge C# files against Unity API stubs.
    Used in CI where Unity installation is not available.
#>
param(
    [string]$SourcePath = "",
    [string]$StubsPath = ""
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir

if (-not $SourcePath) {
    $SourcePath = Join-Path $repoRoot "unity-bridge\Editor"
}
if (-not $StubsPath) {
    $StubsPath = Join-Path $scriptDir "UnityStubs.cs"
}

if (-not (Test-Path $SourcePath)) {
    Write-Host "Error: Source directory not found: $SourcePath" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $StubsPath)) {
    Write-Host "Error: Unity stubs not found: $StubsPath" -ForegroundColor Red
    exit 1
}

Write-Host "Source: $SourcePath"
Write-Host "Stubs: $StubsPath"
Write-Host ""

$tempDir = Join-Path $env:TEMP "unity-csharp-ci-$(Get-Random)"
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

try {
    @"
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>netstandard2.1</TargetFramework>
    <LangVersion>9.0</LangVersion>
    <Nullable>disable</Nullable>
    <TreatWarningsAsErrors>false</TreatWarningsAsErrors>
    <NoWarn>CS0649;CS0169;CS0414;CS0108;CS0114;CS0067</NoWarn>
  </PropertyGroup>
</Project>
"@ | Set-Content "$tempDir\Check.csproj"

    Copy-Item -Path $StubsPath -Destination $tempDir

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

    Write-Host ""
    Write-Host "Compiling..." -ForegroundColor Cyan

    $buildOutput = & dotnet build "$tempDir\Check.csproj" --nologo --verbosity quiet 2>&1
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
                if ($line -match "([^\\\/]+\.cs)\((\d+),(\d+)\):\s*error\s*(CS\d+):\s*(.+)$") {
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
    if (Test-Path $tempDir) {
        Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

$ErrorActionPreference = "Continue"

$VenvDir = Join-Path $env:USERPROFILE ".unityflow-venv"

function Write-Log { param($Message) Write-Host "[unityflow] $Message" -ForegroundColor Green }
function Write-LogWarn { param($Message) Write-Host "[unityflow] $Message" -ForegroundColor Yellow }
function Write-LogError { param($Message) Write-Host "[unityflow] $Message" -ForegroundColor Red }

function Find-Python {
    $candidates = @("python", "python3", "py")
    foreach ($cmd in $candidates) {
        try {
            $result = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if ($result) {
                $parts = $result.Split('.')
                $major = [int]$parts[0]
                $minor = [int]$parts[1]
                if ($major -ge 3 -and $minor -ge 11) {
                    return $cmd
                }
            }
        } catch {}
    }

    try {
        $result = & py -3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($result) {
            $parts = $result.Split('.')
            $major = [int]$parts[0]
            $minor = [int]$parts[1]
            if ($major -ge 3 -and $minor -ge 11) {
                return "py -3"
            }
        }
    } catch {}

    return $null
}

function Install-Python {
    Write-Log "Python 3.11+ not found. Attempting to install..."

    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Log "Installing Python via winget..."
        winget install Python.Python.3.12 --accept-source-agreements --accept-package-agreements 2>$null
    } elseif (Get-Command choco -ErrorAction SilentlyContinue) {
        Write-Log "Installing Python via chocolatey..."
        choco install python --yes 2>$null
    } else {
        Write-LogError "Cannot auto-install Python on Windows."
        Write-LogError "Please install Python 3.12+ from https://python.org/downloads/"
        return $false
    }

    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    return $true
}

function New-Venv {
    param($PythonCmd)

    if (Test-Path $VenvDir) {
        Write-Log "Virtual environment already exists at $VenvDir"
        return $true
    }

    Write-Log "Creating virtual environment at $VenvDir..."
    if ($PythonCmd -eq "py -3") {
        & py -3 -m venv $VenvDir
    } else {
        & $PythonCmd -m venv $VenvDir
    }
    Write-Log "Virtual environment created."
    return $true
}

function Install-Unityflow {
    $PipCmd = Join-Path $VenvDir "Scripts\pip.exe"

    $installed = & $PipCmd show unityflow 2>$null
    if ($installed) {
        $version = ($installed | Select-String "^Version:").ToString().Split(":")[1].Trim()
        Write-Log "unityflow $version is already installed."
        return $true
    }

    Write-Log "Installing unityflow from PyPI..."
    & $PipCmd install --quiet unityflow

    $installed = & $PipCmd show unityflow 2>$null
    if ($installed) {
        $version = ($installed | Select-String "^Version:").ToString().Split(":")[1].Trim()
        Write-Log "unityflow $version installed successfully!"
        return $true
    } else {
        Write-LogError "Failed to install unityflow"
        return $false
    }
}

function Setup-Path {
    $UnityflowBin = Join-Path $VenvDir "Scripts\unityflow.exe"
    $LocalBin = Join-Path $env:USERPROFILE ".local\bin"

    if (-not (Test-Path $LocalBin)) {
        New-Item -ItemType Directory -Path $LocalBin -Force | Out-Null
    }

    $WrapperPath = Join-Path $LocalBin "unityflow.cmd"
    $WrapperContent = "@echo off`r`n`"$UnityflowBin`" %*`r`n"
    Set-Content -Path $WrapperPath -Value $WrapperContent -NoNewline

    Write-Log "Wrapper created at $WrapperPath"

    $currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($currentPath -notlike "*$LocalBin*") {
        Write-LogWarn "Add $LocalBin to your PATH for easy access."
    }
}

function Main {
    Write-Log "Ensuring unityflow is installed..."

    $pythonCmd = Find-Python
    if (-not $pythonCmd) {
        $installed = Install-Python
        if (-not $installed) {
            Write-LogWarn "Install Python manually: https://python.org/downloads/"
            exit 0
        }
        $pythonCmd = Find-Python
        if (-not $pythonCmd) {
            Write-LogError "Python 3.11+ is required but could not be installed."
            Write-LogWarn "Install Python manually: https://python.org/downloads/"
            exit 0
        }
    }

    Write-Log "Found Python: $pythonCmd"

    $result = New-Venv -PythonCmd $pythonCmd
    if (-not $result) { exit 0 }

    $result = Install-Unityflow
    if (-not $result) { exit 0 }

    Setup-Path

    Write-Host ""
    Write-Host "[UNITYFLOW READY] unityflow command is now available."
    Write-Host ""
}

Main

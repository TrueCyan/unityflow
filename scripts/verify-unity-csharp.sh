#!/bin/bash
# Verify Unity C# code compilation
# Reads UNITY_EDITOR_PATH from .env.local or environment variable
# Usage: ./scripts/verify-unity-csharp.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# Load .env.local if exists
if [ -f "$REPO_ROOT/.env.local" ]; then
    export $(grep -v '^#' "$REPO_ROOT/.env.local" | grep -v '^\s*$' | xargs)
fi

# Pass to PowerShell (it will also check .env.local on Windows side)
powershell.exe -ExecutionPolicy Bypass -File "$SCRIPT_DIR/verify-unity-csharp.ps1"

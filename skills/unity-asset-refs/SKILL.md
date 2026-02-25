---
name: unity-asset-refs
description: Finds all files referencing a specific Unity asset by GUID. Tracks asset usage across prefabs, scenes, ScriptableObjects, and other Unity YAML files. Keywords: reference, GUID, dependency, usage, find references, asset tracking, who uses, where used, unused asset
---

# Unity Asset References Skill

Find which files reference a specific Unity asset using `uvx unityflow refs` CLI.

## Rule: Use uvx unityflow refs

Asset reference searches require GUID-based lookup across Unity YAML files. Use `uvx unityflow refs` to find all files that reference a given asset.

---

## CLI Command Reference

### Basic Usage

```bash
uvx unityflow refs Assets/Scripts/Player.cs
```

Output:
```
Found 3 references to Assets/Scripts/Player.cs:

  Assets/Prefabs/Player.prefab (2 refs)
  Assets/Scenes/Main.unity (1 ref)
  Assets/Prefabs/UI/HUD.prefab (1 ref)
```

### Options

```bash
# JSON output
uvx unityflow refs Assets/Scripts/Player.cs --format json

# Specify Unity project root
uvx unityflow refs Assets/Scripts/Player.cs --project-root /path/to/unity

# Include Library/PackageCache in search
uvx unityflow refs Assets/Scripts/Player.cs --include-packages

# Show progress bar
uvx unityflow refs Assets/Scripts/Player.cs --progress
```

### JSON Output

```bash
uvx unityflow refs Assets/Scripts/Player.cs --format json
```

```json
{
  "asset": "Assets/Scripts/Player.cs",
  "guid": "abc123...",
  "references": [
    {"file": "Assets/Prefabs/Player.prefab", "count": 2},
    {"file": "Assets/Scenes/Main.unity", "count": 1},
    {"file": "Assets/Prefabs/UI/HUD.prefab", "count": 1}
  ],
  "total_files": 3,
  "total_refs": 4
}
```

---

## Workflows

### Dependency Analysis

Combine `refs`, `inspect`, and `hierarchy` for full dependency analysis:

```bash
# 1. Find who uses this script
uvx unityflow refs Assets/Scripts/PlayerController.cs

# 2. Inspect how the script is used in a specific prefab
uvx unityflow inspect Assets/Prefabs/Player.prefab --type MonoBehaviour

# 3. See the prefab's full hierarchy
uvx unityflow hierarchy Assets/Prefabs/Player.prefab
```

### Detect Unused Assets

```bash
# Check if an asset is referenced anywhere
uvx unityflow refs Assets/Materials/OldMaterial.mat
# Output: "No references found for Assets/Materials/OldMaterial.mat"
```

### Refactoring Impact Check

Before renaming, moving, or deleting an asset, check what depends on it:

```bash
# Find all files that will break if this asset is removed
uvx unityflow refs Assets/Scripts/LegacySystem.cs --format json
```

### Package Dependency Check

```bash
# Find references including package files
uvx unityflow refs Assets/Scripts/SharedUtil.cs --include-packages
```

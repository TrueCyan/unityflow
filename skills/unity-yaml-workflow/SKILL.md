---
name: unity-yaml-workflow
description: Edits Unity YAML files (.prefab, .unity, .asset). Handles prefab, scene, and ScriptableObject hierarchy queries, Transform/component value modifications, asset reference linking, etc. Use unity-ui-workflow for UI tasks and unity-animation-workflow for animation tasks. Keywords: prefab, scene, Transform, component, value modification, asset linking, ScriptableObject
---

# Unity YAML Workflow Skill

Edit Unity prefabs (.prefab), scenes (.unity), and ScriptableObject (.asset) files using `unityflow` CLI.

## Rule: Use unityflow CLI

All Unity YAML file operations require the `unityflow` CLI to preserve Unity's special format (tag aliases, deterministic field ordering, reference formats).

Available commands:
- `unityflow hierarchy` - Query hierarchy structure
- `unityflow inspect` - Query specific object/component details
- `unityflow get` - Query value at specific path
- `unityflow set` - Modify values (single value, batch modification)
- `unityflow set --value "@assetpath"` - Link assets

---

## CLI Command Reference

### Querying Hierarchy Structure (hierarchy)

```bash
# View hierarchy structure (components shown by default)
unityflow hierarchy Player.prefab
unityflow hierarchy MainScene.unity

# Hide components for cleaner view
unityflow hierarchy Player.prefab --no-components

# Output in JSON format
unityflow hierarchy Player.prefab --format json

# Display only up to specific depth
unityflow hierarchy Scene.unity --depth 2
```

### Querying Object/Component Details (inspect)

```bash
# View GameObject details (specify by path)
unityflow inspect Player.prefab "Player"
unityflow inspect Scene.unity "Canvas/Panel/Button"

# View component details
unityflow inspect Player.prefab "Player/Transform"
unityflow inspect Scene.unity "Player/SpriteRenderer"

# Output in JSON format
unityflow inspect Player.prefab "Player/Transform" --format json
```

### Querying Values (get)

```bash
# Query Transform position
unityflow get Player.prefab "Player/Transform/m_LocalPosition"

# Query SpriteRenderer color
unityflow get Player.prefab "Player/SpriteRenderer/m_Color"

# Query GameObject name
unityflow get Player.prefab "Player/name"

# Query all component properties
unityflow get Player.prefab "Player/Transform"

# Specify by index when there are multiple components
unityflow get Scene.unity "Canvas/Panel/Image[1]/m_Color"

# Output in text format
unityflow get Player.prefab "Player/Transform/m_LocalPosition" --format text
```

### Modifying Values (set)

The `set` command supports 2 modes (mutually exclusive):
- `--value`: Set single value
- `--batch`: Set multiple fields at once

**Asset Linking**: Specify asset path with `@` prefix.

```bash
# Set Transform position
unityflow set Player.prefab \
    --path "Player/Transform/m_LocalPosition" \
    --value '{"x": 0, "y": 5, "z": 0}'

# Set SpriteRenderer color
unityflow set Player.prefab \
    --path "Player/SpriteRenderer/m_Color" \
    --value '{"r": 1, "g": 0, "b": 0, "a": 1}'

# Change GameObject name
unityflow set Player.prefab \
    --path "Player/name" \
    --value '"NewName"'

# Specify by index when there are multiple components
unityflow set Scene.unity \
    --path "Canvas/Panel/Image[1]/m_Color" \
    --value '{"r": 0, "g": 1, "b": 0, "a": 1}'

# Modify multiple fields at once (batch mode)
unityflow set Scene.unity \
    --path "Player/MonoBehaviour" \
    --batch '{"speed": 5.0, "health": 100}'
```

### Asset Linking (@ prefix)

Use `@` prefix to link assets.

```bash
# Link sprite (Single mode)
unityflow set Player.prefab \
    --path "Player/SpriteRenderer/m_Sprite" \
    --value "@Assets/Sprites/player.png"

# Link sprite (Multiple mode - sub sprite)
unityflow set Player.prefab \
    --path "Player/SpriteRenderer/m_Sprite" \
    --value "@Assets/Sprites/atlas.png:player_idle_0"

# Link prefab reference (MonoBehaviour field)
unityflow set Scene.unity \
    --path "Player/MonoBehaviour/enemyPrefab" \
    --value "@Assets/Prefabs/Enemy.prefab"

# Multiple asset references at once (batch mode)
unityflow set Scene.unity \
    --path "Player/MonoBehaviour" \
    --batch '{
        "playerPrefab": "@Assets/Prefabs/Player.prefab",
        "enemyPrefab": "@Assets/Prefabs/Enemy.prefab",
        "spawnRate": 2.0
    }'
```

**Supported Asset Types:**

| Asset Type | Example |
|------------|---------|
| Script | `@Assets/Scripts/Player.cs` |
| Sprite (Single) | `@Assets/Sprites/icon.png` |
| Sprite (Multiple) | `@Assets/Sprites/atlas.png:idle_0` |
| AudioClip | `@Assets/Audio/jump.wav` |
| Material | `@Assets/Materials/Custom.mat` |
| Prefab | `@Assets/Prefabs/Enemy.prefab` |
| ScriptableObject | `@Assets/Data/Config.asset` |
| Animation | `@Assets/Animations/walk.anim` |

### Internal Object Reference (# prefix)

Use `#` prefix to reference objects/components within the same file.

```bash
# Link to a component on another GameObject
unityflow set Player.prefab \
    --path "Player/MyScript/_target" \
    --value "#Player/Enemy/Transform"

# Link to a GameObject (without component type)
unityflow set Player.prefab \
    --path "Player/MyScript/_spawnPoint" \
    --value "#Player/SpawnPoint"
```

### Adding and Removing Components

```bash
# Add a component to a GameObject
unityflow set Player.prefab --path "Player/Button" --create

# Remove a component from a GameObject
unityflow set Player.prefab --path "Player/OldComponent" --remove
```

### Validation and Normalization

```bash
# Validate file
unityflow validate Player.prefab
unityflow validate MainScene.unity
unityflow validate GameConfig.asset

# Normalize (remove Git noise) - field sorting applied by default
unityflow normalize Player.prefab
unityflow normalize MainScene.unity
```

### File Comparison and Merging

```bash
# Compare two files
unityflow diff old.prefab new.prefab

# Compare in summary format
unityflow diff old.prefab new.prefab --format summary

# 3-way merge
unityflow merge base.prefab ours.prefab theirs.prefab -o merged.prefab
```

---

## Recommended Workflow

1. **Backup**: Use `-o` option to save to a new file
2. **Normalize**: Run `unityflow normalize` after editing to reduce Git noise
3. **Validate**: Run `unityflow validate` to check file integrity

---

## Troubleshooting

### When Parsing Errors Occur

```bash
unityflow validate problematic.prefab --format json
```

---

## Summary

- Use `unityflow` CLI for all Unity YAML operations
- References: `@` for external assets, `#` for internal objects
- Components: `--create` to add, `--remove` to delete
- Workflow: edit → normalize → validate

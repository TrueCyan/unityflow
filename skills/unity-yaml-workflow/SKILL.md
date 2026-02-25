---
name: unity-yaml-workflow
description: Edits Unity YAML files (.prefab, .unity, .asset). Handles prefab, scene, and ScriptableObject hierarchy queries, Transform/component value modifications, asset reference linking, etc. Use unity-ui-workflow for UI tasks and unity-animation-workflow for animation tasks. Keywords: prefab, scene, Transform, component, value modification, asset linking, ScriptableObject
---

# Unity YAML Workflow Skill

Edit Unity prefabs (.prefab), scenes (.unity), and ScriptableObject (.asset) files using `unityflow` CLI.

## Rule: Use unityflow CLI

All Unity YAML file operations require the `unityflow` CLI to preserve Unity's special format (tag aliases, deterministic field ordering, reference formats).

Available commands:
- `uvx unityflow create` - Create new Unity file (.prefab, .unity, .asset)
- `uvx unityflow hierarchy` - Query hierarchy structure
- `uvx unityflow inspect` - Query specific object/component details
- `uvx unityflow get` - Query value at specific path
- `uvx unityflow set` - Modify values (single value, batch modification)
- `uvx unityflow set --add-component` / `--remove-component` - Manage components
- `uvx unityflow set --add-object` / `--remove-object` - Manage child GameObjects

---

## CLI Command Reference

### Querying Hierarchy Structure (hierarchy)

```bash
# View hierarchy structure (components shown by default)
uvx unityflow hierarchy Player.prefab
uvx unityflow hierarchy MainScene.unity

# Hide components for cleaner view
uvx unityflow hierarchy Player.prefab --no-components

# Output in JSON format
uvx unityflow hierarchy Player.prefab --format json

# Display only up to specific depth
uvx unityflow hierarchy Scene.unity --depth 2
```

### Querying Object/Component Details (inspect)

```bash
# View GameObject details (specify by path)
uvx unityflow inspect Player.prefab "Player"
uvx unityflow inspect Scene.unity "Canvas/Panel/Button"

# View component details
uvx unityflow inspect Player.prefab "Player/Transform"
uvx unityflow inspect Scene.unity "Player/SpriteRenderer"

# Output in JSON format
uvx unityflow inspect Player.prefab "Player/Transform" --format json
```

### Querying Values (get)

```bash
# Query Transform position
uvx unityflow get Player.prefab "Player/Transform/m_LocalPosition"

# Query SpriteRenderer color
uvx unityflow get Player.prefab "Player/SpriteRenderer/m_Color"

# Query GameObject name
uvx unityflow get Player.prefab "Player/name"

# Query all component properties
uvx unityflow get Player.prefab "Player/Transform"

# Specify by index when there are multiple components
uvx unityflow get Scene.unity "Canvas/Panel/Image[1]/m_Color"

# Output in text format
uvx unityflow get Player.prefab "Player/Transform/m_LocalPosition" --format text
```

### Modifying Values (set)

The `set` command supports 2 modes (mutually exclusive):
- `--value`: Set single value
- `--batch`: Set multiple fields at once

**Asset Linking**: Specify asset path with `@` prefix.

```bash
# Set Transform position
uvx unityflow set Player.prefab \
    --path "Player/Transform/m_LocalPosition" \
    --value '{"x": 0, "y": 5, "z": 0}'

# Set SpriteRenderer color
uvx unityflow set Player.prefab \
    --path "Player/SpriteRenderer/m_Color" \
    --value '{"r": 1, "g": 0, "b": 0, "a": 1}'

# Change GameObject name
uvx unityflow set Player.prefab \
    --path "Player/name" \
    --value '"NewName"'

# Specify by index when there are multiple components
uvx unityflow set Scene.unity \
    --path "Canvas/Panel/Image[1]/m_Color" \
    --value '{"r": 0, "g": 1, "b": 0, "a": 1}'

# Modify multiple fields at once (batch mode)
uvx unityflow set Scene.unity \
    --path "Player/MonoBehaviour" \
    --batch '{"speed": 5.0, "health": 100}'
```

### Asset Linking (@ prefix)

Use `@` prefix to link assets.

```bash
# Link sprite (Single mode)
uvx unityflow set Player.prefab \
    --path "Player/SpriteRenderer/m_Sprite" \
    --value "@Assets/Sprites/player.png"

# Link sprite (Multiple mode - sub sprite)
uvx unityflow set Player.prefab \
    --path "Player/SpriteRenderer/m_Sprite" \
    --value "@Assets/Sprites/atlas.png:player_idle_0"

# Link prefab reference (MonoBehaviour field)
uvx unityflow set Scene.unity \
    --path "Player/MonoBehaviour/enemyPrefab" \
    --value "@Assets/Prefabs/Enemy.prefab"

# Multiple asset references at once (batch mode)
uvx unityflow set Scene.unity \
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
uvx unityflow set Player.prefab \
    --path "Player/MyScript/_target" \
    --value "#Player/Enemy/Transform"

# Link to a GameObject (without component type)
uvx unityflow set Player.prefab \
    --path "Player/MyScript/_spawnPoint" \
    --value "#Player/SpawnPoint"
```

### Creating New Files (create)

```bash
# Create a new prefab
uvx unityflow create MyPrefab.prefab

# Create with custom root name
uvx unityflow create Enemy.prefab --name "Enemy"

# Create UI prefab with RectTransform
uvx unityflow create MyUI.prefab --name "Root" --type rect-transform
```

### Adding and Removing Components

```bash
# Add a component to a GameObject
uvx unityflow set Player.prefab --path "Player" --add-component "Button"

# Remove a component from a GameObject
uvx unityflow set Player.prefab --path "Player" --remove-component "OldComponent"
```

### Adding and Removing Child GameObjects

```bash
# Add a child GameObject
uvx unityflow set Player.prefab --path "Player" --add-object "Child"

# Add a child with RectTransform (for UI)
uvx unityflow set Player.prefab --path "Player" --add-object "Panel" --type rect-transform

# Remove a child GameObject
uvx unityflow set Player.prefab --path "Player" --remove-object "Child"
```

### Validation and Normalization

```bash
# Validate file
uvx unityflow validate Player.prefab
uvx unityflow validate MainScene.unity
uvx unityflow validate GameConfig.asset

# Normalize (remove Git noise) - field sorting applied by default
uvx unityflow normalize Player.prefab
uvx unityflow normalize MainScene.unity
```

### File Comparison and Merging

```bash
# Compare two files
uvx unityflow diff old.prefab new.prefab

# Compare in summary format
uvx unityflow diff old.prefab new.prefab --format summary

# 3-way merge
uvx unityflow merge base.prefab ours.prefab theirs.prefab -o merged.prefab
```

---

## Recommended Workflow

1. **Backup**: Use `-o` option to save to a new file
2. **Normalize**: Run `uvx unityflow normalize` after editing to reduce Git noise
3. **Validate**: Run `uvx unityflow validate` to check file integrity

---

## Troubleshooting

### When Parsing Errors Occur

```bash
uvx unityflow validate problematic.prefab --format json
```

---

## Summary

- Use `unityflow` CLI for all Unity YAML operations
- Create files: `uvx unityflow create`
- References: `@` for external assets, `#` for internal objects
- Components: `--add-component` to add, `--remove-component` to delete
- Child objects: `--add-object` to add, `--remove-object` to delete
- Workflow: create → edit → normalize → validate

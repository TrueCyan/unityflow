---
name: unity-yaml-workflow
description: Creates and edits Unity YAML files (.prefab, .unity, .asset). Use when user asks to create, modify, or build prefabs, scenes, or assets. Keywords: prefab, scene, create, modify, build, edit, Transform, component, asset linking, ScriptableObject
---

# Unity YAML Workflow Skill

Edit Unity prefabs (.prefab), scenes (.unity), and ScriptableObject (.asset) files using `unityflow` CLI.

Use unity-ui-workflow for UI-specific tasks. Use unity-animation-workflow for animation tasks.

## Rules

1. **Use `hierarchy` first** — understand the structure before inspecting or editing individual objects
2. **Use `--batch` for multiple properties** — set many fields in one call instead of calling set repeatedly
3. **Verify with `diff` after editing** — always run `unityflow diff original.prefab modified.prefab` to confirm changes are correct
4. **One `--add-component` per type** — never add the same component type twice to the same GameObject
5. **Use unityflow CLI for all operations** — never edit Unity YAML files directly; the format requires special handling

---

## Available Commands

- `uvx unityflow create` - Create new Unity file
- `uvx unityflow hierarchy` - View hierarchy structure
- `uvx unityflow inspect` - View object/component details
- `uvx unityflow get` - Get value at path
- `uvx unityflow set` - Modify values, add/remove components and objects
- `uvx unityflow diff` - Compare two files
- `uvx unityflow validate` - Check file integrity
- `uvx unityflow normalize` - Deterministic serialization for Git

---

## Querying

### Hierarchy

```bash
uvx unityflow hierarchy Player.prefab
uvx unityflow hierarchy Player.prefab --no-components
uvx unityflow hierarchy Scene.unity --depth 2
```

### Inspect and Get

```bash
uvx unityflow inspect Player.prefab "Player"
uvx unityflow inspect Player.prefab "Player/Transform"
uvx unityflow get Player.prefab "Player/Transform/m_LocalPosition"
uvx unityflow get Scene.unity "Canvas/Panel/Image[1]/m_Color"
```

---

## Modifying

### Single Value and Batch

```bash
uvx unityflow set Player.prefab \
    --path "Player/Transform/m_LocalPosition" \
    --value '{"x": 0, "y": 5, "z": 0}'

uvx unityflow set Scene.unity \
    --path "Player/MonoBehaviour" \
    --batch '{"speed": 5.0, "health": 100}'
```

### Asset References (@)

```bash
uvx unityflow set Player.prefab \
    --path "Player/SpriteRenderer/m_Sprite" \
    --value "@Assets/Sprites/player.png"

uvx unityflow set Player.prefab \
    --path "Player/SpriteRenderer/m_Sprite" \
    --value "@Assets/Sprites/atlas.png:player_idle_0"
```

### Internal References (#)

```bash
uvx unityflow set Player.prefab \
    --path "Player/MyScript/_target" \
    --value "#Player/Enemy/Transform"
```

---

## Creating and Structuring

### Create File

```bash
uvx unityflow create MyPrefab.prefab
uvx unityflow create Enemy.prefab --name "Enemy"
uvx unityflow create MyUI.prefab --name "Root" --type rect-transform
```

### Add/Remove Objects and Components

```bash
uvx unityflow set Player.prefab --path "Player" --add-object "Child"
uvx unityflow set Player.prefab --path "Player" --add-object "Panel" --type rect-transform
uvx unityflow set Player.prefab --path "Player" --remove-object "Child"

uvx unityflow set Player.prefab --path "Player" --add-component "Button"
uvx unityflow set Player.prefab --path "Player" --remove-component "OldComponent"
```

---

## Verification

```bash
uvx unityflow diff old.prefab new.prefab
uvx unityflow validate Player.prefab
uvx unityflow normalize Player.prefab
```

---
name: unity-yaml-workflow
description: "MUST READ before any Unity YAML work. Creates and edits .prefab, .unity, .asset files via unityflow CLI. Trigger: any task involving Unity files, prefabs, scenes, GameObjects, components, hierarchy. Contains required CLI usage rules, command reference, and examples."
---

# Unity YAML Workflow Skill

Edit Unity prefabs (.prefab), scenes (.unity), and ScriptableObject (.asset) files using `unityflow` CLI.

Use unity-ui-workflow for UI-specific tasks. Use unity-animation-workflow for animation tasks.

## Rules

1. **Always use `uvx unityflow`** — never call `unityflow` directly; `uvx` ensures the latest published version is used
2. **Use `hierarchy` first** — understand the structure before inspecting or editing individual objects
3. **Use `--batch` for multiple properties** — set many fields in one call instead of calling set repeatedly
4. **Verify with `diff` after editing** — always run `uvx unityflow diff original.prefab modified.prefab` to confirm changes are correct
5. **One `--add-component` per type** — never add the same component type twice to the same GameObject
6. **Never edit Unity YAML files directly** — the format requires special handling

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
uvx unityflow hierarchy Player.prefab --detail
uvx unityflow hierarchy Player.prefab --no-components
uvx unityflow hierarchy Scene.unity --depth 2
```

`--detail` shows all component properties inline in the tree, hiding default transform values and internal fields.

hierarchy shows PrefabInstance source paths when project root is available:

```
├── MyButton [Prefab: Assets/Prefabs/Button.prefab]
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

# Batch on component
uvx unityflow set Scene.unity \
    --path "Player/MonoBehaviour" \
    --batch '{"speed": 5.0, "health": 100}'

# Batch on GameObject (m_Layer, m_IsActive, etc.)
uvx unityflow set Player.prefab \
    --path "Player" \
    --batch '{"m_Layer": 5, "m_IsActive": 0}'
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
# Add empty child GameObject
uvx unityflow set Player.prefab --path "Player" --add-object "Child"
uvx unityflow set Player.prefab --path "Player" --add-object "Panel" --type rect-transform
uvx unityflow set Player.prefab --path "Player" --remove-object "Child"

# Add nested prefab instance (@ prefix)
uvx unityflow set file.prefab --path "Root" --add-object "@Assets/Prefabs/Button.prefab"
uvx unityflow set file.prefab --path "Root" --add-object "@Assets/Prefabs/Panel.prefab" --instance-name "MyPanel"

# Use "Core/Image" and "Core/InputField" for Unity built-in components
# (plain "Image" or "InputField" may conflict with TextMeshPro types)
uvx unityflow set Player.prefab --path "Player" --add-component "Button"
uvx unityflow set Player.prefab --path "Player" --remove-component "OldComponent"

# Move component order
uvx unityflow set file.prefab --path "Root" --move-component "Mask[0]" --before "Image"
```

---

## PrefabInstance Properties

Nested prefab instances can be edited with the same path syntax:

```bash
uvx unityflow set file.prefab \
    --path "Root/MyButton/m_Layer" \
    --value "5"

uvx unityflow set file.prefab \
    --path "Root/MyButton" \
    --batch '{"m_Layer": 5, "m_TagString": "Player"}'
```

---

## Verification

```bash
uvx unityflow diff old.prefab new.prefab
uvx unityflow validate Player.prefab
uvx unityflow normalize Player.prefab
```

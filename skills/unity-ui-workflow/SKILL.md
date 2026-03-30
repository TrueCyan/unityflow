---
name: unity-ui-workflow
description: "MUST READ before any Unity UI work. Creates and edits Unity UI (UGUI) prefabs via unityflow CLI. Trigger: any task involving .prefab UI files, Canvas, Button, Image, Text, RectTransform, UGUI components. Contains required CLI usage rules, command reference, and examples."
---

# Unity UI Workflow Skill

Edit Unity UI (UGUI) components using `unityflow` CLI.

## Rules

1. **Always use `uvx unityflow`** — never call `unityflow` directly; `uvx` ensures the latest published version is used
2. **Use `hierarchy` first** — understand the structure before inspecting or editing individual objects
3. **Use `--batch` for multiple properties** — set many fields in one call instead of calling set repeatedly
4. **Verify with `diff` after editing** — always run `uvx unityflow diff original.prefab modified.prefab` to confirm changes are correct
5. **One `--add-component` per type** — never add the same component type twice to the same GameObject
6. **Never edit Unity YAML files directly** — the format requires special handling

---

## Querying

```bash
uvx unityflow hierarchy MainMenu.prefab
uvx unityflow hierarchy MainMenu.prefab --detail
uvx unityflow hierarchy MainMenu.prefab --no-components
uvx unityflow inspect Scene.unity "Canvas/Panel/Button"
uvx unityflow inspect Scene.unity "Canvas/Panel/Image" --json
```

`--detail` shows all component properties inline in the tree, hiding default transform values and internal fields.

hierarchy shows PrefabInstance source paths when project root is available:

```
├── btn_save [Prefab: Assets/UI/common/btn_save.prefab]
├── board_title [Prefab: Assets/UI/common/board_title.prefab]
```

---

## References

```bash
# External asset (@)
uvx unityflow set Scene.unity \
    --path "Canvas/Panel/Button/Image/m_Sprite" \
    --value "@Assets/Sprites/button_normal.png"

# Internal object (#)
uvx unityflow set Prefab.prefab \
    --path "Root/MyScript/_button" \
    --value "#Root/Panel/Button"
```

---

## Image

```bash
uvx unityflow set Scene.unity \
    --path "Canvas/Panel/Image/m_Color" \
    --value '{"r": 0.2, "g": 0.2, "b": 0.2, "a": 1}'

# Sprite type: 0=Simple, 1=Sliced, 2=Tiled, 3=Filled
uvx unityflow set Scene.unity \
    --path "Canvas/Panel/Image/m_Type" \
    --value '1'
```

---

## RectTransform

```bash
uvx unityflow set Scene.unity \
    --path "Canvas/Panel/RectTransform" \
    --batch '{
        "m_AnchorMin": {"x": 0, "y": 0},
        "m_AnchorMax": {"x": 1, "y": 1},
        "m_AnchoredPosition": {"x": 0, "y": 0},
        "m_SizeDelta": {"x": 0, "y": 0},
        "m_Pivot": {"x": 0.5, "y": 0.5}
    }'
```

### Anchor Presets

| Preset | AnchorMin | AnchorMax |
|--------|-----------|-----------|
| center | (0.5, 0.5) | (0.5, 0.5) |
| stretch-all | (0, 0) | (1, 1) |
| top-stretch | (0, 1) | (1, 1) |
| bottom-stretch | (0, 0) | (1, 0) |

---

## Layout

```bash
uvx unityflow set Scene.unity \
    --path "Canvas/Panel/VerticalLayoutGroup" \
    --batch '{
        "m_Spacing": 10,
        "m_ChildAlignment": 0,
        "m_ChildControlWidth": 1,
        "m_ChildControlHeight": 0,
        "m_ChildForceExpandWidth": 1,
        "m_ChildForceExpandHeight": 0
    }'

# ContentSizeFitter (0=Unconstrained, 1=MinSize, 2=PreferredSize)
uvx unityflow set Scene.unity \
    --path "Canvas/Panel/ContentSizeFitter" \
    --batch '{"m_HorizontalFit": 0, "m_VerticalFit": 2}'
```

---

## Mask

Mask uses Image alpha for masking.

```bash
uvx unityflow set Scene.unity \
    --path "Canvas/ScrollView/Mask/m_ShowMaskGraphic" \
    --value '0'
```

---

## Creating UI Prefabs

```bash
uvx unityflow create MyUI.prefab --type rect-transform
uvx unityflow create MainMenu.prefab --name "MainMenu" --type rect-transform
```

---

## GameObject Properties (batch)

```bash
# Set multiple GameObject properties at once
uvx unityflow set Prefab.prefab --path "Canvas/Panel" --batch '{"m_Layer": 5, "m_IsActive": 0}'
```

---

## Adding/Removing Components and Objects

```bash
# Use "Core/Image" and "Core/InputField" for Unity built-in components
# (plain "Image" or "InputField" may conflict with TextMeshPro types)
uvx unityflow set Prefab.prefab --path "Canvas/Panel" --add-component "Core/Image"
uvx unityflow set Prefab.prefab --path "Canvas/Panel" --remove-component "Button"
uvx unityflow set Prefab.prefab --path "Canvas/Panel" --add-object "Child" --type rect-transform
uvx unityflow set Prefab.prefab --path "Canvas/Panel" --remove-object "Child"

# Add nested prefab instance (@ prefix)
uvx unityflow set Prefab.prefab --path "Canvas/Panel" --add-object "@Assets/Prefabs/Button.prefab"
uvx unityflow set Prefab.prefab --path "Canvas/Panel" --add-object "@Assets/Prefabs/Panel.prefab" --instance-name "MyPanel"

# Move component order
uvx unityflow set Prefab.prefab --path "Canvas/Panel" --move-component "Mask[0]" --before "Image"
```

---

## PrefabInstance Properties

Use `inspect --overrides` to see only the property overrides on a PrefabInstance:

```bash
uvx unityflow inspect Scene.unity "Canvas/MyButton" --overrides
uvx unityflow inspect Scene.unity "Canvas/MyButton" --overrides --json
```

Nested prefab instances can be edited with the same path syntax:

```bash
uvx unityflow set Prefab.prefab \
    --path "Canvas/MyButton/m_Layer" \
    --value "5"

uvx unityflow set Prefab.prefab \
    --path "Canvas/MyButton" \
    --batch '{"m_Layer": 5, "m_TagString": "Player"}'
```

## Multiple Components of Same Type

```bash
# Modify second Image component
uvx unityflow set Scene.unity \
    --path "Canvas/Panel/Image[1]/m_Color" \
    --value '{"r": 1, "g": 0, "b": 0, "a": 1}'
```

---

## Supported UI Components

| Category | Components |
|----------|------------|
| **Basic** | Image, Button |
| **Layout** | VerticalLayoutGroup, HorizontalLayoutGroup, ContentSizeFitter |
| **Scroll** | ScrollRect, Mask, RectMask2D |
| **Text** | TextMeshProUGUI, TMP_InputField |
| **Canvas** | CanvasScaler, GraphicRaycaster |

### Name Conflicts

Some components exist in multiple assemblies (e.g., Unity Core vs TextMeshPro).
Use the full path to avoid ambiguity:

| Component | Full Path | Conflicts With |
|-----------|-----------|----------------|
| Image | `Core/Image` | TextMeshPro `TMP_SpriteAsset/Image` |
| InputField | `Core/InputField` | TextMeshPro `TMP_InputField` |

Always use `--add-component "Core/Image"` and `--add-component "Core/InputField"` for Unity built-in versions.

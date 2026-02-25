---
name: unity-ui-workflow
description: Edits Unity UI (UGUI) components. Handles UI elements like Canvas, Panel, Button, Image, Text, TextMeshPro, and RectTransform anchor/pivot/size adjustments, LayoutGroup settings, etc. Keywords: UI, Canvas, Button, Image, Text, RectTransform, anchor, pivot, layout, UGUI
---

# Unity UI Workflow Skill

Edit Unity UI (UGUI) components using `unityflow` CLI.

## Rule: Use unityflow CLI

All Unity UI file operations require the `unityflow` CLI to preserve Unity's special YAML format.

---

## Querying UI Hierarchy

```bash
# View scene UI hierarchy (components shown by default)
uvx unityflow hierarchy Scene.unity

# View UI prefab structure
uvx unityflow hierarchy MainMenu.prefab

# Hide components for cleaner view
uvx unityflow hierarchy MainMenu.prefab --no-components

# Output in JSON format
uvx unityflow hierarchy Scene.unity --format json
```

---

## Querying UI Components

### GameObject Details

```bash
# Canvas details
uvx unityflow inspect Scene.unity "Canvas"

# Panel details
uvx unityflow inspect Scene.unity "Canvas/Panel"

# Button details (find by path)
uvx unityflow inspect Scene.unity "Canvas/Panel/Button"
```

### Component Properties

```bash
# Query Image component
uvx unityflow inspect Scene.unity "Canvas/Panel/Image"

# Query RectTransform
uvx unityflow get Scene.unity "Canvas/Panel/RectTransform"

# Query specific property
uvx unityflow get Scene.unity "Canvas/Panel/Image/m_Color"
uvx unityflow get Scene.unity "Canvas/Panel/RectTransform/m_AnchorMin"
```

---

## Reference Types

### External Asset Reference (@)

Use `@` prefix to reference external assets by path.

```bash
# Link sprite to UI Image
uvx unityflow set Scene.unity \
    --path "Canvas/Panel/Button/Image/m_Sprite" \
    --value "@Assets/Sprites/button_normal.png"
```

### Internal Object Reference (#)

Use `#` prefix to reference objects/components within the same file.

```bash
# Link to a Button component on another GameObject
uvx unityflow set Prefab.prefab \
    --path "Root/MyScript/_button" \
    --value "#Root/Panel/Button"

# Link to a GameObject (without component type)
uvx unityflow set Prefab.prefab \
    --path "Root/MyScript/_targetObject" \
    --value "#Root/Panel"
```

---

## Modifying UI Properties

### Image Properties

```bash
# Set color
uvx unityflow set Scene.unity \
    --path "Canvas/Panel/Image/m_Color" \
    --value '{"r": 0.2, "g": 0.2, "b": 0.2, "a": 1}'

# Link sprite
uvx unityflow set Scene.unity \
    --path "Canvas/Panel/Image/m_Sprite" \
    --value "@Assets/Sprites/panel_bg.png"

# Set sprite type (0=Simple, 1=Sliced, 2=Tiled, 3=Filled)
uvx unityflow set Scene.unity \
    --path "Canvas/Panel/Image/m_Type" \
    --value '1'
```

### Button Color Settings

```bash
# Modify Button color block
uvx unityflow set Scene.unity \
    --path "Canvas/Panel/Button/Button" \
    --batch '{
        "m_NormalColor": {"r": 1, "g": 1, "b": 1, "a": 1},
        "m_HighlightedColor": {"r": 0.96, "g": 0.96, "b": 0.96, "a": 1},
        "m_PressedColor": {"r": 0.78, "g": 0.78, "b": 0.78, "a": 1},
        "m_SelectedColor": {"r": 0.96, "g": 0.96, "b": 0.96, "a": 1},
        "m_DisabledColor": {"r": 0.78, "g": 0.78, "b": 0.78, "a": 0.5}
    }'
```

### TextMeshPro Modification

```bash
# Set text
uvx unityflow set Scene.unity \
    --path "Canvas/Panel/Label/TextMeshProUGUI/m_text" \
    --value '"Hello World"'

# Set font size
uvx unityflow set Scene.unity \
    --path "Canvas/Panel/Label/TextMeshProUGUI/m_fontSize" \
    --value '24'
```

---

## RectTransform Settings

RectTransform determines the position and size of UI elements.

```bash
# Set entire RectTransform (batch mode)
uvx unityflow set Scene.unity \
    --path "Canvas/Panel/RectTransform" \
    --batch '{
        "m_AnchorMin": {"x": 0.5, "y": 0.5},
        "m_AnchorMax": {"x": 0.5, "y": 0.5},
        "m_AnchoredPosition": {"x": 0, "y": 0},
        "m_SizeDelta": {"x": 400, "y": 300},
        "m_Pivot": {"x": 0.5, "y": 0.5}
    }'
```

### Anchor Presets

| Preset | AnchorMin | AnchorMax | Description |
|--------|-----------|-----------|-------------|
| center | (0.5, 0.5) | (0.5, 0.5) | Center, fixed size |
| top-left | (0, 1) | (0, 1) | Top-left, fixed |
| top-right | (1, 1) | (1, 1) | Top-right, fixed |
| bottom-left | (0, 0) | (0, 0) | Bottom-left, fixed |
| bottom-right | (1, 0) | (1, 0) | Bottom-right, fixed |
| stretch-all | (0, 0) | (1, 1) | Stretch all directions |
| stretch-top | (0, 1) | (1, 1) | Stretch horizontal at top |
| stretch-bottom | (0, 0) | (1, 0) | Stretch horizontal at bottom |
| stretch-left | (0, 0) | (0, 1) | Stretch vertical at left |
| stretch-right | (1, 0) | (1, 1) | Stretch vertical at right |

### Example: Full-Screen Panel

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

### Example: Fixed Header at Top (Height 60)

```bash
uvx unityflow set Scene.unity \
    --path "Canvas/Header/RectTransform" \
    --batch '{
        "m_AnchorMin": {"x": 0, "y": 1},
        "m_AnchorMax": {"x": 1, "y": 1},
        "m_AnchoredPosition": {"x": 0, "y": 0},
        "m_SizeDelta": {"x": 0, "y": 60},
        "m_Pivot": {"x": 0.5, "y": 1}
    }'
```

---

## Modifying Layout Components

### VerticalLayoutGroup / HorizontalLayoutGroup

```bash
# Layout settings
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
```

### ContentSizeFitter

```bash
# Settings (0=Unconstrained, 1=MinSize, 2=PreferredSize)
uvx unityflow set Scene.unity \
    --path "Canvas/Panel/ContentSizeFitter" \
    --batch '{"m_HorizontalFit": 0, "m_VerticalFit": 2}'
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
| **System** | EventSystem, InputSystemUIInputModule |

---

## Mask Component

Mask component uses Image alpha for masking. Set alpha to 1 and use `m_ShowMaskGraphic` to control visibility.

```bash
# Set alpha to 1 for Mask
uvx unityflow set Scene.unity \
    --path "Canvas/ScrollView/Image/m_Color" \
    --value '{"r": 1, "g": 1, "b": 1, "a": 1}'

# Hide the mask image visually
uvx unityflow set Scene.unity \
    --path "Canvas/ScrollView/Mask/m_ShowMaskGraphic" \
    --value '0'
```

## Multiple Components of Same Type

Use index to specify which component when multiple exist.

```bash
# Modify second Image component
uvx unityflow set Scene.unity \
    --path "Canvas/Panel/Image[1]/m_Color" \
    --value '{"r": 1, "g": 0, "b": 0, "a": 1}'
```

---

## Creating UI Prefabs

```bash
# Create a UI prefab with RectTransform
uvx unityflow create MyUI.prefab --type rect-transform

# Create with custom root name
uvx unityflow create MainMenu.prefab --name "MainMenu" --type rect-transform
```

---

## Adding and Removing Components

```bash
# Add a Button component to a GameObject
uvx unityflow set Prefab.prefab --path "Canvas/Panel" --add-component "Button"

# Add an Image component
uvx unityflow set Prefab.prefab --path "Canvas/Panel" --add-component "Image"

# Remove a component
uvx unityflow set Prefab.prefab --path "Canvas/Panel" --remove-component "Button"
```

---

## Adding and Removing Child GameObjects

```bash
# Add a UI child object (with RectTransform)
uvx unityflow set Prefab.prefab --path "Canvas/Panel" --add-object "Button" --type rect-transform

# Remove a child object
uvx unityflow set Prefab.prefab --path "Canvas/Panel" --remove-object "Button"
```

---

## Summary

- Use `unityflow` CLI for all Unity UI file operations
- Create UI files: `uvx unityflow create --type rect-transform`
- References: `@` for external assets, `#` for internal objects
- Components: `--add-component` to add, `--remove-component` to delete
- Child objects: `--add-object` to add, `--remove-object` to delete

---
name: unity-ui-workflow
description: Edits Unity UI (UGUI) components. Handles UI elements like Canvas, Panel, Button, Image, Text, TextMeshPro, and RectTransform anchor/pivot/size adjustments, LayoutGroup settings, etc. Keywords: UI, Canvas, Button, Image, Text, RectTransform, anchor, pivot, layout, UGUI
---

# Unity UI Workflow Skill

A skill for programmatically editing the Unity UI system (UGUI).

---

## Mandatory Rule: Use unityflow

**All Unity file operations must be performed through the `unityflow` CLI.**

Do not directly text-edit Unity YAML files!

---

## Querying UI Hierarchy

```bash
# View scene UI hierarchy
unityflow hierarchy Scene.unity --components

# View UI prefab structure
unityflow hierarchy MainMenu.prefab --components

# Output in JSON format
unityflow hierarchy Scene.unity --format json
```

---

## Querying UI Components

### GameObject Details

```bash
# Canvas details
unityflow inspect Scene.unity "Canvas"

# Panel details
unityflow inspect Scene.unity "Canvas/Panel"

# Button details (find by path)
unityflow inspect Scene.unity "Canvas/Panel/Button"
```

### Component Properties

```bash
# Query Image component
unityflow inspect Scene.unity "Canvas/Panel/Image"

# Query RectTransform
unityflow get Scene.unity "Canvas/Panel/RectTransform"

# Query specific property
unityflow get Scene.unity "Canvas/Panel/Image/m_Color"
unityflow get Scene.unity "Canvas/Panel/RectTransform/m_AnchorMin"
```

---

## Modifying UI Properties

### Image Properties

```bash
# Set color
unityflow set Scene.unity \
    --path "Canvas/Panel/Image/m_Color" \
    --value '{"r": 0.2, "g": 0.2, "b": 0.2, "a": 1}'

# Link sprite
unityflow set Scene.unity \
    --path "Canvas/Panel/Image/m_Sprite" \
    --value "@Assets/Sprites/panel_bg.png"

# Set sprite type (0=Simple, 1=Sliced, 2=Tiled, 3=Filled)
unityflow set Scene.unity \
    --path "Canvas/Panel/Image/m_Type" \
    --value '1'
```

### Button Color Settings

```bash
# Modify Button color block
unityflow set Scene.unity \
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
unityflow set Scene.unity \
    --path "Canvas/Panel/Label/TextMeshProUGUI/m_text" \
    --value '"Hello World"'

# Set font size
unityflow set Scene.unity \
    --path "Canvas/Panel/Label/TextMeshProUGUI/m_fontSize" \
    --value '24'
```

---

## RectTransform Settings

RectTransform determines the position and size of UI elements.

```bash
# Set entire RectTransform (batch mode)
unityflow set Scene.unity \
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
unityflow set Scene.unity \
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
unityflow set Scene.unity \
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
unityflow set Scene.unity \
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
unityflow set Scene.unity \
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

## Important Notes

### 1. Mask and Image Alpha Value

When using Mask component, masking won't work if Image alpha is 0.

```bash
# Alpha must be 1 for mask to work
unityflow set Scene.unity \
    --path "Canvas/ScrollView/Image/m_Color" \
    --value '{"r": 1, "g": 1, "b": 1, "a": 1}'

# Use m_ShowMaskGraphic to hide the mask image
unityflow set Scene.unity \
    --path "Canvas/ScrollView/Mask/m_ShowMaskGraphic" \
    --value '0'
```

### 2. Using Index When Multiple Components Exist

Use index to specify when there are multiple components of the same type.

```bash
# Modify second Image component
unityflow set Scene.unity \
    --path "Canvas/Panel/Image[1]/m_Color" \
    --value '{"r": 1, "g": 0, "b": 0, "a": 1}'
```

---

## Linking UI Sprites

```bash
# Link sprite to UI Image
unityflow set Scene.unity \
    --path "Canvas/Panel/Button/Image/m_Sprite" \
    --value "@Assets/Sprites/button_normal.png"

# Set 9-slice border (in Sliced mode)
unityflow set Scene.unity \
    --path "Canvas/Panel/Image/m_FillCenter" \
    --value '1'
```

---
name: unity-ui-workflow
description: Unity UI 작업을 수행합니다. unityflow를 사용하여 Canvas, Panel, Button, Image 등 UI 컴포넌트 생성/수정, RectTransform 레이아웃 조정, EventSystem 설정 등의 작업을 수행합니다.
---

# Unity UI Workflow Skill

Unity UI 시스템(UGUI)을 프로그래매틱하게 편집하기 위한 skill입니다.

---

## ⚠️ 필수 규칙: unityflow 사용 의무

**모든 Unity 파일 조작은 `unityflow` CLI를 통해서만 수행합니다.**

Unity YAML 파일을 직접 텍스트 편집하지 마세요!

---

## UI GameObject 생성

UI용 GameObject는 `--ui` 플래그를 사용하여 RectTransform으로 생성합니다.

```bash
# UI용 GameObject 생성 (RectTransform 포함)
unityflow add-object Scene.unity --name "Panel" --ui --parent "Canvas"
unityflow add-object Scene.unity --name "Button" --ui --parent "Canvas/Panel"
unityflow add-object Scene.unity --name "Icon" --ui --parent "Canvas/Panel/Button"
```

---

## UI 컴포넌트 추가

### Canvas 설정

**모든 UI 요소는 반드시 Canvas의 자식이어야 합니다.** 씬에 Canvas가 없으면 새로 추가해야 합니다.

Canvas를 추가할 때는 **필수 컴포넌트를 반드시 함께 추가**해야 합니다:
- **CanvasScaler**: UI 스케일링 처리
- **GraphicRaycaster**: 클릭/터치 감지 (없으면 UI 클릭이 작동하지 않음!)

```bash
# Canvas GameObject 추가
unityflow add-object Scene.unity --name "Canvas" --ui

# 필수 컴포넌트 추가 (반드시 모두 추가할 것!)
unityflow add-component Scene.unity --to "Canvas" --type Canvas
unityflow add-component Scene.unity --to "Canvas" --type CanvasScaler
unityflow add-component Scene.unity --to "Canvas" --type GraphicRaycaster
```

### Image

```bash
# Image 컴포넌트 추가
unityflow add-component Scene.unity --to "Canvas/Panel" --type Image

# 색상 설정
unityflow set Scene.unity \
    --path "Canvas/Panel/Image/m_Color" \
    --value '{"r": 0.2, "g": 0.2, "b": 0.2, "a": 1}'

# 스프라이트 연결
unityflow set Scene.unity \
    --path "Canvas/Panel/Image/m_Sprite" \
    --value "@Assets/Sprites/panel_bg.png"
```

### Button

```bash
# Button 컴포넌트 추가 (Image가 필요)
unityflow add-component Scene.unity --to "Canvas/Panel/Button" --type Image
unityflow add-component Scene.unity --to "Canvas/Panel/Button" --type Button

# Button 색상 설정
unityflow set Scene.unity \
    --path "Canvas/Panel/Button/Button/m_Colors" \
    --value '{
        "m_NormalColor": {"r": 1, "g": 1, "b": 1, "a": 1},
        "m_HighlightedColor": {"r": 0.96, "g": 0.96, "b": 0.96, "a": 1},
        "m_PressedColor": {"r": 0.78, "g": 0.78, "b": 0.78, "a": 1},
        "m_SelectedColor": {"r": 0.96, "g": 0.96, "b": 0.96, "a": 1},
        "m_DisabledColor": {"r": 0.78, "g": 0.78, "b": 0.78, "a": 0.5}
    }'
```

### TextMeshPro

```bash
# TextMeshProUGUI 추가
unityflow add-component Scene.unity --to "Canvas/Panel/Label" --type TextMeshProUGUI

# 텍스트 설정
unityflow set Scene.unity \
    --path "Canvas/Panel/Label/TextMeshProUGUI/m_text" \
    --value '"Hello World"'

# 폰트 크기 설정
unityflow set Scene.unity \
    --path "Canvas/Panel/Label/TextMeshProUGUI/m_fontSize" \
    --value '24'
```

### ScrollRect

```bash
# ScrollRect 구조 설정
# - ScrollView (ScrollRect + Image + Mask)
#   - Viewport (Image + Mask)
#     - Content (VerticalLayoutGroup)

unityflow add-component Scene.unity --to "Canvas/ScrollView" --type Image
unityflow add-component Scene.unity --to "Canvas/ScrollView" --type ScrollRect
unityflow add-component Scene.unity --to "Canvas/ScrollView" --type Mask

unityflow add-component Scene.unity --to "Canvas/ScrollView/Viewport" --type Image
unityflow add-component Scene.unity --to "Canvas/ScrollView/Viewport" --type RectMask2D

unityflow add-component Scene.unity --to "Canvas/ScrollView/Viewport/Content" --type VerticalLayoutGroup
unityflow add-component Scene.unity --to "Canvas/ScrollView/Viewport/Content" --type ContentSizeFitter
```

### Input Field

```bash
# TMP_InputField 추가
unityflow add-component Scene.unity --to "Canvas/Panel/InputField" --type Image
unityflow add-component Scene.unity --to "Canvas/Panel/InputField" --type TMP_InputField

# Placeholder와 Text 설정
unityflow set Scene.unity \
    --path "Canvas/Panel/InputField/TMP_InputField/m_Placeholder" \
    --value '{"fileID": <placeholder_text_id>}'
```

---

## 레이아웃 컴포넌트

### VerticalLayoutGroup / HorizontalLayoutGroup

```bash
# 수직 레이아웃 추가
unityflow add-component Scene.unity --to "Canvas/Panel" --type VerticalLayoutGroup

# 레이아웃 설정
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
# ContentSizeFitter 추가
unityflow add-component Scene.unity --to "Canvas/Panel" --type ContentSizeFitter

# 설정 (0=Unconstrained, 1=MinSize, 2=PreferredSize)
unityflow set Scene.unity \
    --path "Canvas/Panel/ContentSizeFitter" \
    --batch '{"m_HorizontalFit": 0, "m_VerticalFit": 2}'
```

---

## RectTransform 설정

RectTransform은 UI 요소의 위치와 크기를 결정합니다.

```bash
# RectTransform 전체 설정
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

### 앵커 프리셋

| 프리셋 | AnchorMin | AnchorMax | 설명 |
|--------|-----------|-----------|------|
| center | (0.5, 0.5) | (0.5, 0.5) | 중앙 고정 크기 |
| top-left | (0, 1) | (0, 1) | 좌상단 고정 |
| top-right | (1, 1) | (1, 1) | 우상단 고정 |
| bottom-left | (0, 0) | (0, 0) | 좌하단 고정 |
| bottom-right | (1, 0) | (1, 0) | 우하단 고정 |
| stretch-all | (0, 0) | (1, 1) | 전체 늘이기 |
| stretch-top | (0, 1) | (1, 1) | 상단 가로 늘이기 |
| stretch-bottom | (0, 0) | (1, 0) | 하단 가로 늘이기 |
| stretch-left | (0, 0) | (0, 1) | 좌측 세로 늘이기 |
| stretch-right | (1, 0) | (1, 1) | 우측 세로 늘이기 |

### 예시: 전체 화면 패널

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

### 예시: 상단 고정 헤더 (높이 60)

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

## EventSystem

UI 인터랙션을 위해 씬에 EventSystem이 반드시 필요합니다.

```bash
# EventSystem GameObject 추가
unityflow add-object Scene.unity --name "EventSystem"

# EventSystem 컴포넌트 추가
unityflow add-component Scene.unity --to "EventSystem" --type EventSystem
unityflow add-component Scene.unity --to "EventSystem" --type InputSystemUIInputModule
```

---

## 지원 UI 컴포넌트

| 카테고리 | 컴포넌트 |
|----------|----------|
| **기본** | Image, Button |
| **레이아웃** | VerticalLayoutGroup, HorizontalLayoutGroup, ContentSizeFitter |
| **스크롤** | ScrollRect, Mask, RectMask2D |
| **텍스트** | TextMeshProUGUI, TMP_InputField |
| **Canvas** | CanvasScaler, GraphicRaycaster |
| **시스템** | EventSystem, InputSystemUIInputModule |

---

## 주의사항

### 1. Mask와 Image 알파값

Mask 컴포넌트 사용 시 Image 알파값이 0이면 마스킹이 작동하지 않습니다.

```bash
# 마스크가 작동하려면 알파가 1이어야 함
unityflow set Scene.unity \
    --path "Canvas/ScrollView/Image/m_Color" \
    --value '{"r": 1, "g": 1, "b": 1, "a": 1}'

# 마스크 이미지를 숨기려면 m_ShowMaskGraphic 사용
unityflow set Scene.unity \
    --path "Canvas/ScrollView/Mask/m_ShowMaskGraphic" \
    --value '0'
```

### 2. EventSystem 필수

UI가 클릭에 반응하려면 씬에 반드시 EventSystem이 있어야 합니다.

```bash
# EventSystem이 있는지 확인
unityflow query Scene.unity --find-component "EventSystem"
```

### 3. RectTransform 삭제 불가

RectTransform은 UI GameObject의 필수 컴포넌트이므로 삭제할 수 없습니다.

### 4. GraphicRaycaster 필수

Canvas에 GraphicRaycaster가 없으면 **UI 클릭이 전혀 작동하지 않습니다**.
Canvas를 새로 만들 때 반드시 Canvas, CanvasScaler, GraphicRaycaster를 함께 추가하세요.

---

## UI 스프라이트 연결

```bash
# UI Image 스프라이트 연결
unityflow set Scene.unity \
    --path "Canvas/Panel/Button/Image/m_Sprite" \
    --value "@Assets/Sprites/button_normal.png"

# 스프라이트 타입 설정 (0=Simple, 1=Sliced, 2=Tiled, 3=Filled)
unityflow set Scene.unity \
    --path "Canvas/Panel/Image/m_Type" \
    --value '1'

# 9-slice 테두리 설정 (Sliced 모드에서)
unityflow set Scene.unity \
    --path "Canvas/Panel/Image/m_FillCenter" \
    --value '1'
```

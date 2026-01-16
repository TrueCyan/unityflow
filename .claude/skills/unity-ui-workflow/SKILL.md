---
name: unity-ui-workflow
description: Unity UI(UGUI) 컴포넌트를 편집합니다. Canvas, Panel, Button, Image, Text, TextMeshPro 등 UI 요소와 RectTransform의 앵커/피벗/크기 조정, LayoutGroup 설정 등의 작업을 수행합니다. 키워드: UI, Canvas, Button, Image, Text, RectTransform, 앵커, 피벗, 레이아웃, UGUI
---

# Unity UI Workflow Skill

Unity UI 시스템(UGUI)을 프로그래매틱하게 편집하기 위한 skill입니다.

---

## ⚠️ 필수 규칙: unityflow 사용 의무

**모든 Unity 파일 조작은 `unityflow` CLI를 통해서만 수행합니다.**

Unity YAML 파일을 직접 텍스트 편집하지 마세요!

---

## UI 계층 구조 조회

```bash
# 씬의 UI 계층 구조 보기
unityflow hierarchy Scene.unity --components

# UI 프리팹 구조 보기
unityflow hierarchy MainMenu.prefab --components

# JSON 형식으로 출력
unityflow hierarchy Scene.unity --format json
```

---

## UI 컴포넌트 조회

### GameObject 상세 조회

```bash
# Canvas 상세 정보
unityflow inspect Scene.unity "Canvas"

# Panel 상세 정보
unityflow inspect Scene.unity "Canvas/Panel"

# Button 상세 정보 (경로로 찾기)
unityflow inspect Scene.unity "Canvas/Panel/Button"
```

### 컴포넌트 속성 조회

```bash
# Image 컴포넌트 조회
unityflow inspect Scene.unity "Canvas/Panel/Image"

# RectTransform 조회
unityflow get Scene.unity "Canvas/Panel/RectTransform"

# 특정 속성 조회
unityflow get Scene.unity "Canvas/Panel/Image/m_Color"
unityflow get Scene.unity "Canvas/Panel/RectTransform/m_AnchorMin"
```

---

## UI 속성 수정

### Image 속성 수정

```bash
# 색상 설정
unityflow set Scene.unity \
    --path "Canvas/Panel/Image/m_Color" \
    --value '{"r": 0.2, "g": 0.2, "b": 0.2, "a": 1}'

# 스프라이트 연결
unityflow set Scene.unity \
    --path "Canvas/Panel/Image/m_Sprite" \
    --value "@Assets/Sprites/panel_bg.png"

# 스프라이트 타입 설정 (0=Simple, 1=Sliced, 2=Tiled, 3=Filled)
unityflow set Scene.unity \
    --path "Canvas/Panel/Image/m_Type" \
    --value '1'
```

### Button 색상 설정

```bash
# Button 색상 블록 수정
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

### TextMeshPro 수정

```bash
# 텍스트 설정
unityflow set Scene.unity \
    --path "Canvas/Panel/Label/TextMeshProUGUI/m_text" \
    --value '"Hello World"'

# 폰트 크기 설정
unityflow set Scene.unity \
    --path "Canvas/Panel/Label/TextMeshProUGUI/m_fontSize" \
    --value '24'
```

---

## RectTransform 설정

RectTransform은 UI 요소의 위치와 크기를 결정합니다.

```bash
# RectTransform 전체 설정 (batch 모드)
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

## 레이아웃 컴포넌트 수정

### VerticalLayoutGroup / HorizontalLayoutGroup

```bash
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
# 설정 (0=Unconstrained, 1=MinSize, 2=PreferredSize)
unityflow set Scene.unity \
    --path "Canvas/Panel/ContentSizeFitter" \
    --batch '{"m_HorizontalFit": 0, "m_VerticalFit": 2}'
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

### 2. 여러 컴포넌트가 있을 때 인덱스 사용

동일 타입의 컴포넌트가 여러 개 있으면 인덱스로 지정합니다.

```bash
# 두 번째 Image 컴포넌트 수정
unityflow set Scene.unity \
    --path "Canvas/Panel/Image[1]/m_Color" \
    --value '{"r": 1, "g": 0, "b": 0, "a": 1}'
```

---

## UI 스프라이트 연결

```bash
# UI Image 스프라이트 연결
unityflow set Scene.unity \
    --path "Canvas/Panel/Button/Image/m_Sprite" \
    --value "@Assets/Sprites/button_normal.png"

# 9-slice 테두리 설정 (Sliced 모드에서)
unityflow set Scene.unity \
    --path "Canvas/Panel/Image/m_FillCenter" \
    --value '1'
```

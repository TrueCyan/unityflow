---
name: unity-prefab-scene
description: Unity 프리팹(.prefab)과 씬(.unity) 파일을 편집합니다. prefab-tool을 사용하여 프리팹 분석, JSON 변환, GameObject 생성/수정, UI 레이아웃 조정, 컴포넌트 추가 등의 작업을 수행합니다. 사용자가 Unity 프리팹이나 씬 파일 작업을 요청할 때 사용하세요.
---

# Unity Prefab & Scene Editing Skill

Unity 프리팹(.prefab)과 씬(.unity) 파일을 프로그래매틱하게 편집하기 위한 skill입니다.

## 핵심 도구: prefab-tool

이 프로젝트의 `prefab-tool` CLI와 Python API를 사용하여 Unity YAML 파일을 조작합니다.

## 작업 워크플로우

### 1단계: 파일 분석 (항상 먼저 수행)

```bash
# 파일 통계 확인
prefab-tool stats Player.prefab

# 구조 요약 보기
prefab-tool query Player.prefab

# 특정 데이터 쿼리
prefab-tool query Player.prefab --path "gameObjects/*/name"
prefab-tool query Player.prefab --path "components/*/type" --format json
```

### 2단계: JSON으로 변환 (복잡한 편집용)

LLM이 이해하기 쉬운 JSON 형식으로 변환하여 편집:

```bash
# JSON으로 내보내기
prefab-tool export Player.prefab -o player.json

# JSON 편집 후 다시 프리팹으로 변환
prefab-tool import player.json -o Player.prefab
```

### 3단계: 직접 편집 (간단한 수정용)

```bash
# 특정 값 설정
prefab-tool set Player.prefab \
    --path "components/12345/localPosition" \
    --value '{"x": 0, "y": 5, "z": 0}'

prefab-tool set Player.prefab \
    --path "gameObjects/12345/name" \
    --value '"NewName"'
```

### 4단계: 검증 및 정규화

```bash
# 파일 검증
prefab-tool validate Player.prefab

# 정규화 (Git 노이즈 제거)
prefab-tool normalize Player.prefab
```

---

## Python API 사용법

복잡한 조작이 필요한 경우 Python 스크립트를 작성합니다:

### 기본 사용법

```python
from prefab_tool.parser import (
    UnityYAMLDocument,
    create_game_object,
    create_transform,
    create_rect_transform,
    create_mono_behaviour,
    generate_file_id,
)
from prefab_tool.formats import (
    export_to_json,
    import_from_json,
    create_rect_transform_file_values,
)

# 파일 로드
doc = UnityYAMLDocument.load("Player.prefab")

# 오브젝트 조회
for obj in doc.get_game_objects():
    content = obj.get_content()
    print(f"GameObject: {content['m_Name']}")

# 특정 오브젝트 찾기
obj = doc.get_by_file_id(12345)

# 파일 저장
doc.save("Player_modified.prefab")
```

### 새 GameObject 생성

```python
# 고유 ID 생성
go_id = doc.generate_unique_file_id()
transform_id = doc.generate_unique_file_id()

# GameObject 생성
go = create_game_object(
    name="NewObject",
    file_id=go_id,
    layer=0,
    tag="Untagged",
    is_active=True,
    components=[transform_id],  # Transform 참조
)

# Transform 생성
transform = create_transform(
    game_object_id=go_id,
    file_id=transform_id,
    position={"x": 0, "y": 1, "z": 0},
    rotation={"x": 0, "y": 0, "z": 0, "w": 1},
    scale={"x": 1, "y": 1, "z": 1},
    parent_id=0,  # 루트
)

# 문서에 추가
doc.add_object(go)
doc.add_object(transform)
doc.save("output.prefab")
```

### UI RectTransform 생성

```python
# 앵커 프리셋으로 RectTransform 값 생성
file_vals = create_rect_transform_file_values(
    anchor_preset="stretch-all",  # 전체 스트레치
    pivot=(0.5, 0.5),
    left=10, right=10, top=10, bottom=10,
)

rect_transform = create_rect_transform(
    game_object_id=go_id,
    file_id=rt_id,
    anchor_min=file_vals.anchor_min,
    anchor_max=file_vals.anchor_max,
    anchored_position=file_vals.anchored_position,
    size_delta=file_vals.size_delta,
    pivot=file_vals.pivot,
)
```

### 앵커 프리셋 목록

| 프리셋 | 설명 |
|--------|------|
| `center` | 중앙 (0.5, 0.5) |
| `top-left`, `top-center`, `top-right` | 상단 |
| `middle-left`, `middle-center`, `middle-right` | 중앙 행 |
| `bottom-left`, `bottom-center`, `bottom-right` | 하단 |
| `stretch-top`, `stretch-middle`, `stretch-bottom` | 가로 스트레치 |
| `stretch-left`, `stretch-center`, `stretch-right` | 세로 스트레치 |
| `stretch-all` | 전체 스트레치 |

### MonoBehaviour 추가

```python
mono = create_mono_behaviour(
    game_object_id=go_id,
    script_guid="abc123def456...",  # 스크립트의 GUID
    file_id=mono_id,
    enabled=True,
    properties={
        "speed": 5.0,
        "target": {"fileID": 0},  # 참조
        "items": ["item1", "item2"],
    },
)
```

---

## JSON 형식 이해하기

### 내보낸 JSON 구조

```json
{
  "prefabMetadata": {
    "sourcePath": "Player.prefab",
    "objectCount": 15
  },
  "gameObjects": {
    "12345": {
      "name": "Player",
      "layer": 0,
      "tag": "Player",
      "isActive": true,
      "components": ["12346", "12347"]
    }
  },
  "components": {
    "12346": {
      "type": "Transform",
      "classId": 4,
      "gameObject": "12345",
      "localPosition": {"x": 0, "y": 0, "z": 0},
      "localRotation": {"x": 0, "y": 0, "z": 0, "w": 1},
      "localScale": {"x": 1, "y": 1, "z": 1},
      "parent": null,
      "children": ["12348"]
    },
    "12347": {
      "type": "MonoBehaviour",
      "classId": 114,
      "gameObject": "12345",
      "scriptRef": {
        "fileID": 11500000,
        "guid": "abc123...",
        "type": 3
      },
      "enabled": true,
      "properties": {
        "speed": 5.0
      }
    }
  },
  "_rawFields": {
    "12345": {"m_ObjectHideFlags": 0}
  }
}
```

### RectTransform JSON 구조

RectTransform 컴포넌트는 두 가지 형식으로 값을 제공합니다:

```json
{
  "type": "RectTransform",
  "rectTransform": {
    "anchorMin": {"x": 0, "y": 0},
    "anchorMax": {"x": 1, "y": 1},
    "anchoredPosition": {"x": 0, "y": 0},
    "sizeDelta": {"x": -20, "y": -20},
    "pivot": {"x": 0.5, "y": 0.5}
  },
  "editorValues": {
    "anchorMin": {"x": 0, "y": 0},
    "anchorMax": {"x": 1, "y": 1},
    "pivot": {"x": 0.5, "y": 0.5},
    "posZ": 0,
    "left": 10,
    "right": 10,
    "top": 10,
    "bottom": 10
  }
}
```

**`editorValues`를 수정하면 자동으로 파일 값으로 변환됩니다** (LLM에게 권장)

---

## 일반적인 작업 패턴

### 1. GameObject 이름 변경

```bash
prefab-tool set Player.prefab \
    --path "gameObjects/12345/name" \
    --value '"NewPlayerName"'
```

### 2. 위치 변경

```bash
prefab-tool set Player.prefab \
    --path "components/12346/localPosition" \
    --value '{"x": 10, "y": 0, "z": 5}'
```

### 3. UI 요소 크기 조정 (editorValues 사용)

JSON 편집 시 `editorValues`를 수정:

```json
"editorValues": {
  "posX": 100,
  "posY": 50,
  "width": 200,
  "height": 100
}
```

### 4. 의존성 분석

```bash
# 프리팹이 참조하는 에셋 목록
prefab-tool deps Player.prefab

# 텍스처만 보기
prefab-tool deps Player.prefab --type Texture

# 누락된 에셋 찾기
prefab-tool deps Player.prefab --unresolved-only
```

### 5. 역참조 검색

```bash
# 특정 텍스처를 사용하는 모든 프리팹 찾기
prefab-tool find-refs Textures/player.png
```

---

## Unity Class ID 참조

| ID | 클래스명 |
|----|----------|
| 1 | GameObject |
| 4 | Transform |
| 20 | Camera |
| 23 | MeshRenderer |
| 33 | MeshFilter |
| 54 | Rigidbody |
| 65 | BoxCollider |
| 82 | AudioSource |
| 114 | MonoBehaviour |
| 212 | SpriteRenderer |
| 222 | CanvasRenderer |
| 223 | Canvas |
| 224 | RectTransform |
| 225 | CanvasGroup |
| 1001 | PrefabInstance |

---

## 주의사항

1. **항상 백업**: 원본 파일을 수정하기 전에 백업하거나 `-o` 옵션으로 새 파일에 저장
2. **fileID 충돌 방지**: 새 오브젝트 생성 시 `generate_file_id()` 또는 `doc.generate_unique_file_id()` 사용
3. **정규화 필수**: 편집 후 `prefab-tool normalize`로 정규화하여 Git 노이즈 방지
4. **검증 권장**: 중요한 수정 후 `prefab-tool validate`로 무결성 확인
5. **GUID 보존**: 외부 에셋 참조(스크립트, 텍스처 등)의 GUID는 변경하지 않음

---

## 문제 해결

### 파싱 오류 발생 시

```bash
# 상세 통계로 파일 상태 확인
prefab-tool stats problematic.prefab --format json

# 검증으로 문제점 파악
prefab-tool validate problematic.prefab --format json
```

### 대용량 파일 처리

10MB 이상의 파일은 스트리밍 모드 사용:

```python
doc = UnityYAMLDocument.load_streaming("LargeScene.unity")
doc.save_streaming("output.unity")
```

### JSON 왕복 변환 시 데이터 손실 방지

`_rawFields`를 포함하여 내보내기:

```bash
prefab-tool export Player.prefab -o player.json  # --no-raw 없이
```

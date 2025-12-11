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

| ID | 클래스명 | 설명 |
|----|----------|------|
| 1 | GameObject | 게임 오브젝트 |
| 4 | Transform | 3D 트랜스폼 |
| 20 | Camera | 카메라 |
| 23 | MeshRenderer | 메시 렌더러 |
| 33 | MeshFilter | 메시 필터 |
| 54 | Rigidbody | 강체 물리 |
| 65 | BoxCollider | 박스 콜라이더 |
| 81 | AudioListener | 오디오 리스너 |
| 82 | AudioSource | 오디오 소스 |
| 95 | Animator | 애니메이터 |
| 104 | RenderSettings | 렌더 설정 (씬 전용) |
| 108 | Light | 3D 라이트 |
| 114 | MonoBehaviour | **사용자 스크립트 (기본 사용)** |
| 157 | LightmapSettings | 라이트맵 설정 (씬 전용) |
| 180 | ParticleSystem | 파티클 시스템 |
| 196 | NavMeshSettings | 네비메시 설정 (씬 전용) |
| 212 | SpriteRenderer | 스프라이트 렌더러 |
| 222 | CanvasRenderer | 캔버스 렌더러 |
| 223 | Canvas | UI 캔버스 |
| 224 | RectTransform | UI 트랜스폼 |
| 225 | CanvasGroup | 캔버스 그룹 |
| 1001 | PrefabInstance | 프리팹 인스턴스 |
| 1660057539 | SceneRoots | ⚠️ **씬 루트 목록 (절대 직접 사용 금지!)** |

**참고**: 패키지 컴포넌트(Light2D, TextMeshPro 등)는 `MonoBehaviour(114)`를 사용하며, 스크립트 GUID로 구분됩니다. 아래 "패키지 컴포넌트 GUID 참조" 섹션을 확인하세요.

---

## 주의사항

1. **항상 백업**: 원본 파일을 수정하기 전에 백업하거나 `-o` 옵션으로 새 파일에 저장
2. **fileID 충돌 방지**: 새 오브젝트 생성 시 `generate_file_id()` 또는 `doc.generate_unique_file_id()` 사용
3. **정규화 필수**: 편집 후 `prefab-tool normalize`로 정규화하여 Git 노이즈 방지
4. **검증 권장**: 중요한 수정 후 `prefab-tool validate`로 무결성 확인
5. **GUID 보존**: 외부 에셋 참조(스크립트, 텍스처 등)의 GUID는 변경하지 않음
6. **classId 보존**: **절대로 임의의 classId를 사용하지 마세요!** JSON 변환 시 원본 classId가 보존됩니다. 새 컴포넌트 추가 시 반드시 올바른 classId를 사용하세요.

### classId 관련 중요 경고

⚠️ **절대 SceneRoots classId(1660057539)를 다른 컴포넌트에 사용하지 마세요!**

Unity는 classId를 기반으로 오브젝트 타입을 결정합니다. 잘못된 classId를 사용하면:
- "cast failed from SceneRoots to Component" 오류 발생
- 컴포넌트가 로드되지 않고 제거됨
- 씬 파일이 손상될 수 있음

새 컴포넌트를 추가할 때는:
1. **MonoBehaviour(114)**: 모든 사용자 스크립트에 사용
2. 알 수 없는 Unity 내장 컴포넌트는 원본 파일에서 classId를 복사
3. 확실하지 않으면 Unity에서 직접 생성한 파일 참조

---

## 패키지 컴포넌트 GUID 참조

Unity 패키지(URP, TextMeshPro, Cinemachine 등)의 컴포넌트들은 내장 클래스가 아니라 **MonoBehaviour(classId=114)** 로 구현됩니다. 이들은 스크립트의 GUID로 식별됩니다.

### 알려진 패키지 컴포넌트 GUID

| 패키지 | 컴포넌트 | GUID | fileID |
|--------|----------|------|--------|
| URP 2D | Light2D | `073797afb82c5a1438f328866b10b3f0` | 11500000 |
| URP 2D | ShadowCaster2D | (프로젝트에서 추출 필요) | 11500000 |
| TextMeshPro | TextMeshProUGUI | (프로젝트에서 추출 필요) | 11500000 |
| Cinemachine | CinemachineVirtualCamera | (프로젝트에서 추출 필요) | 11500000 |

> **참고**: 패키지 버전에 따라 GUID가 다를 수 있습니다. 사용 중인 프로젝트에서 직접 추출하는 것을 권장합니다.

### GUID 발견 방법

패키지 컴포넌트의 GUID를 찾는 방법:

#### 방법 1: scan-scripts 명령어 사용 (권장, 자동화)

`prefab-tool scan-scripts` 명령어로 프로젝트 전체의 스크립트 GUID를 자동으로 추출:

```bash
# 단일 파일 스캔
prefab-tool scan-scripts Player.prefab

# 디렉토리 재귀적 스캔
prefab-tool scan-scripts Assets/Prefabs -r

# GUID별로 그룹화하여 보기
prefab-tool scan-scripts Assets/ -r --group-by-guid

# 프로퍼티 키도 함께 보기 (컴포넌트 구조 파악용)
prefab-tool scan-scripts Scene.unity --show-properties

# JSON 출력 (자동화 스크립트용)
prefab-tool scan-scripts *.prefab --format json --group-by-guid
```

출력 예시:
```
Scanned 15 file(s)
Found 8 unique script GUID(s)

============================================================
GUID Summary Table (for SKILL.md):
------------------------------------------------------------
| GUID | fileID | Usage Count |
|------|--------|-------------|
| `f4688fdb7df04437aeb418b961361dc5` | 11500000 | 45 |
| `fe87c0e1cc204ed48ad3b37840f39efc` | 11500000 | 24 |
...
```

#### 방법 2: Python API로 추출

```python
from prefab_tool.parser import UnityYAMLDocument

doc = UnityYAMLDocument.load("YourFile.prefab")
for obj in doc.objects:
    if obj.class_id == 114:  # MonoBehaviour
        content = obj.get_content()
        script = content.get("m_Script", {})
        print(f"GUID: {script.get('guid')}")
        print(f"Properties: {list(content.keys())}")
```

#### 방법 3: scan-meta로 패키지 폴더 스캔

`prefab-tool scan-meta`로 패키지 폴더의 `.meta` 파일에서 직접 GUID 추출:

```bash
# URP 패키지의 모든 스크립트 GUID 추출
prefab-tool scan-meta "Library/PackageCache/com.unity.render-pipelines.universal@*" -r --scripts-only

# Light 관련 스크립트만 필터링
prefab-tool scan-meta "Library/PackageCache/com.unity.render-pipelines.universal@*" -r --filter Light

# TextMeshPro 패키지 스캔
prefab-tool scan-meta "Library/PackageCache/com.unity.textmeshpro@*" -r --scripts-only

# Cinemachine 패키지 스캔
prefab-tool scan-meta "Library/PackageCache/com.unity.cinemachine@*" -r --scripts-only

# JSON 출력 (자동화용)
prefab-tool scan-meta "Library/PackageCache/com.unity.render-pipelines.universal@*" -r --scripts-only --format json
```

출력 예시:
```
Package: com.unity.render-pipelines.universal
Scanned 150 .meta file(s)
Found 45 asset(s) with GUIDs

Scripts:
----------------------------------------------------------------------
Name                                     GUID
----------------------------------------------------------------------
Light2D                                  073797afb82c5a1438f328866b10b3f0
ShadowCaster2D                           xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
...

======================================================================
Markdown Table (for documentation):
----------------------------------------------------------------------
| Script | GUID |
|--------|------|
| Light2D | `073797afb82c5a1438f328866b10b3f0` |
...
```

#### 방법 4: Unity Editor 스크립트 사용

```csharp
// Unity Editor에서 실행
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering.Universal; // URP

public static class GUIDFinder
{
    [MenuItem("Tools/Find Light2D GUID")]
    public static void FindLight2DGUID()
    {
        var script = MonoScript.FromMonoBehaviour(
            new GameObject().AddComponent<Light2D>()
        );
        string path = AssetDatabase.GetAssetPath(script);
        string guid = AssetDatabase.AssetPathToGUID(path);
        Debug.Log($"Light2D GUID: {guid}");
    }
}
```

### 패키지 컴포넌트 생성 예시

#### Light2D (URP 2D) 생성

```python
from prefab_tool.parser import (
    UnityYAMLDocument,
    create_game_object,
    create_transform,
    create_mono_behaviour,
)

doc = UnityYAMLDocument.load("Scene.unity")

# ID 생성
go_id = doc.generate_unique_file_id()
transform_id = doc.generate_unique_file_id()
light2d_id = doc.generate_unique_file_id()

# GameObject 생성
go = create_game_object(
    name="Global Light 2D",
    file_id=go_id,
    components=[transform_id, light2d_id],
)

# Transform 생성
transform = create_transform(
    game_object_id=go_id,
    file_id=transform_id,
)

# Light2D 생성 (MonoBehaviour)
light2d = create_mono_behaviour(
    game_object_id=go_id,
    script_guid="073797afb82c5a1438f328866b10b3f0",  # Light2D GUID
    file_id=light2d_id,
    enabled=True,
    properties={
        "m_LightType": 4,           # Global=4, Point=0, Sprite=2, Freeform=3
        "m_Intensity": 1,
        "m_Color": {"r": 1, "g": 1, "b": 1, "a": 1},
        "m_UseNormalMap": 0,
        "m_ShadowsEnabled": 0,
        "m_ShadowIntensity": 0.75,
        "m_ShadowVolumeIntensity": 0.75,
        "m_ApplyToSortingLayers": [],  # 적용할 Sorting Layer 목록
        "m_LightOrder": 0,
        "m_OverlapOperation": 0,
        "m_BlendStyleIndex": 0,
        # Point Light 전용
        "m_PointLightInnerAngle": 360,
        "m_PointLightOuterAngle": 360,
        "m_PointLightInnerRadius": 0,
        "m_PointLightOuterRadius": 1,
        "m_PointLightDistance": 0,
        # Freeform/Sprite Light 전용
        "m_ShapePath": [],
        "m_ShapeLightFalloffSize": 0.5,
        "m_ShapeLightParametricSides": 5,
        "m_ShapeLightParametricAngleOffset": 0,
        "m_ShapeLightParametricRadius": 1,
    },
)

doc.add_object(go)
doc.add_object(transform)
doc.add_object(light2d)
doc.save("Scene_with_light.unity")
```

### Light2D 타입 상수

| 값 | 타입 | 설명 |
|----|------|------|
| 0 | Point | 점 조명 (원형) |
| 2 | Sprite | 스프라이트 기반 조명 |
| 3 | Freeform | 자유 형태 조명 |
| 4 | Global | 전역 조명 (전체 씬) |

### 패키지 컴포넌트 프로퍼티 분석

새로운 패키지 컴포넌트를 사용하려면 먼저 해당 컴포넌트의 프로퍼티 구조를 분석해야 합니다:

```python
from prefab_tool.parser import UnityYAMLDocument
from prefab_tool.formats import export_to_json
import json

# 해당 컴포넌트가 포함된 파일 분석
doc = UnityYAMLDocument.load("FileWithComponent.prefab")
prefab_json = export_to_json(doc)

# MonoBehaviour 중 원하는 GUID 찾기
for file_id, comp in prefab_json.components.items():
    if comp.get("classId") == 114:
        script_ref = comp.get("scriptRef", {})
        guid = script_ref.get("guid", "")

        if guid == "YOUR_TARGET_GUID":
            print(f"=== Component: {file_id} ===")
            print(f"GUID: {guid}")
            print(f"Properties: {json.dumps(comp.get('properties', {}), indent=2)}")
```

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

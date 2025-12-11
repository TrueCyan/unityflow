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
7. **Mask + Image 알파값 주의**: ScrollRect 등에서 Mask 컴포넌트를 사용할 때, 함께 붙어있는 Image 컴포넌트의 알파값이 0이면 마스킹이 작동하지 않습니다. 마스킹용 Image는 반드시 `m_Color: {r: 1, g: 1, b: 1, a: 1}`로 설정하고, 시각적으로 숨기려면 `m_ShowMaskGraphic: 0`을 사용하세요.

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

Unity 패키지(URP, TextMeshPro, ugui 등)의 컴포넌트들은 내장 클래스가 아니라 **MonoBehaviour(classId=114)** 로 구현됩니다. 이들은 스크립트의 GUID로 식별됩니다.

### Unity UI 컴포넌트 GUID (com.unity.ugui 패키지)

⚠️ **중요**: Unity 6+에서는 UGUI와 TMP가 `com.unity.ugui` 패키지에 통합되어 있습니다.

#### 기본 UI 컴포넌트

| 컴포넌트 | GUID | 설명 |
|----------|------|------|
| Image | `fe87c0e1cc204ed48ad3b37840f39efc` | UI 이미지 |
| Button | `4e29b1a8efbd4b44bb3f3716e73f07ff` | 버튼 |
| ScrollRect | `1aa08ab6e0800fa44ae55d278d1423e3` | 스크롤 뷰 |
| Mask | `31a19414c41e5ae4aae2af33fee712f6` | 마스크 |
| RectMask2D | `3312d7739989d2b4e91e6319e9a96d76` | 2D 마스크 |
| GraphicRaycaster | `dc42784cf147c0c48a680349fa168899` | UI 레이캐스트 |
| CanvasScaler | `0cd44c1031e13a943bb63640046fad76` | 캔버스 스케일러 |

#### 레이아웃 컴포넌트

| 컴포넌트 | GUID | 설명 |
|----------|------|------|
| VerticalLayoutGroup | `59f8146938fff824cb5fd77236b75775` | 세로 레이아웃 |
| HorizontalLayoutGroup | `30649d3a9faa99c48a7b1166b86bf2a0` | 가로 레이아웃 |
| ContentSizeFitter | `3245ec927659c4140ac4f8d17403cc18` | 콘텐츠 크기 맞춤 |

#### TextMeshPro 컴포넌트

| 컴포넌트 | GUID | 설명 |
|----------|------|------|
| TextMeshProUGUI | `f4688fdb7df04437aeb418b961361dc5` | TMP 텍스트 (UI) |
| TMP_InputField | `2da0c512f12947e489f739169773d7ca` | TMP 입력 필드 |

#### EventSystem 컴포넌트

⚠️ **중요**: UI가 클릭에 반응하려면 씬에 반드시 **EventSystem**이 있어야 합니다. Canvas를 배치하기 전에 EventSystem이 있는지 확인하세요.

| 컴포넌트 | GUID | 패키지 |
|----------|------|--------|
| EventSystem | `76c392e42b5098c458856cdf6ecaaaa1` | com.unity.ugui |
| InputSystemUIInputModule | `01614664b831546d2ae94a42149d80ac` | com.unity.inputsystem |

> **참고**: Unity 6+의 새 Input System을 사용하는 경우 `InputSystemUIInputModule`을 사용합니다. 레거시 Input Manager를 사용하는 경우 `StandaloneInputModule`(GUID: `4f231c4fb786f3946a6b90b886c48677`)을 대신 사용합니다.

### 렌더링 컴포넌트 GUID

| 패키지 | 컴포넌트 | GUID |
|--------|----------|------|
| URP 2D | Light2D | `073797afb82c5a1438f328866b10b3f0` |

> **참고**: 패키지 버전에 따라 GUID가 다를 수 있습니다. 아래 방법으로 직접 추출할 수 있습니다.

### GUID 발견 방법

새 프로젝트에서 패키지 컴포넌트의 GUID를 찾는 방법:

#### 방법 0: 패키지 폴더에서 직접 추출 (가장 확실)

Unity 패키지들은 `Library/PackageCache/` 폴더에 저장됩니다. 폴더명에 버전 해시가 포함되어 있습니다:

```bash
# 패키지 폴더 확인
ls Library/PackageCache/ | grep ugui
# 출력: com.unity.ugui@aa507f3228f0

# 특정 컴포넌트의 GUID 직접 확인
grep "guid:" "Library/PackageCache/com.unity.ugui@*/Runtime/UGUI/UI/Core/Button.cs.meta"
# 출력: guid: 4e29b1a8efbd4b44bb3f3716e73f07ff

# TMP 컴포넌트 확인
grep "guid:" "Library/PackageCache/com.unity.ugui@*/Runtime/TMP/TextMeshProUGUI.cs.meta"
# 출력: guid: f4688fdb7df04437aeb418b961361dc5
```

**주요 패키지 경로:**

| 패키지 | 경로 |
|--------|------|
| UGUI | `Library/PackageCache/com.unity.ugui@*/Runtime/UGUI/UI/Core/` |
| TMP | `Library/PackageCache/com.unity.ugui@*/Runtime/TMP/` |
| URP 2D | `Library/PackageCache/com.unity.render-pipelines.universal@*/Runtime/2D/` |

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

#### EventSystem 생성 (UI 필수 요소)

⚠️ **Canvas를 생성하기 전에 반드시 EventSystem이 있는지 확인하세요!** EventSystem이 없으면 UI 버튼 클릭 등이 작동하지 않습니다.

```python
from prefab_tool.parser import (
    UnityYAMLDocument,
    create_game_object,
    create_transform,
    create_mono_behaviour,
)

def ensure_event_system(doc):
    """씬에 EventSystem이 없으면 생성"""

    # EventSystem이 이미 있는지 확인
    for obj in doc.get_game_objects():
        content = obj.get_content()
        if content.get('m_Name') == 'EventSystem':
            print("EventSystem already exists")
            return None

    # EventSystem 생성
    go_id = doc.generate_unique_file_id()
    transform_id = doc.generate_unique_file_id()
    eventsystem_id = doc.generate_unique_file_id()
    inputmodule_id = doc.generate_unique_file_id()

    # GameObject
    go = create_game_object(
        name="EventSystem",
        file_id=go_id,
        layer=0,
        components=[transform_id, eventsystem_id, inputmodule_id],
    )

    # Transform
    transform = create_transform(
        game_object_id=go_id,
        file_id=transform_id,
    )

    # EventSystem 컴포넌트
    eventsystem = create_mono_behaviour(
        game_object_id=go_id,
        script_guid="76c392e42b5098c458856cdf6ecaaaa1",  # EventSystem
        file_id=eventsystem_id,
        enabled=True,
        properties={
            "m_FirstSelected": {"fileID": 0},
            "m_sendNavigationEvents": 1,
            "m_DragThreshold": 10,
        },
    )

    # InputSystemUIInputModule 컴포넌트 (Unity 6+ 새 Input System)
    # UI 기본 입력 액션 에셋 GUID: ca9f5fa95ffab41fb9a615ab714db018
    input_actions_guid = "ca9f5fa95ffab41fb9a615ab714db018"
    inputmodule = create_mono_behaviour(
        game_object_id=go_id,
        script_guid="01614664b831546d2ae94a42149d80ac",  # InputSystemUIInputModule
        file_id=inputmodule_id,
        enabled=True,
        properties={
            "m_SendPointerHoverToParent": 1,
            "m_MoveRepeatDelay": 0.5,
            "m_MoveRepeatRate": 0.1,
            "m_XRTrackingOrigin": {"fileID": 0},
            "m_ActionsAsset": {"fileID": -944628639613478452, "guid": input_actions_guid, "type": 3},
            "m_PointAction": {"fileID": -1654692200621890270, "guid": input_actions_guid, "type": 3},
            "m_MoveAction": {"fileID": -8784545083839296357, "guid": input_actions_guid, "type": 3},
            "m_SubmitAction": {"fileID": 392368643174621059, "guid": input_actions_guid, "type": 3},
            "m_CancelAction": {"fileID": 7727032971491509709, "guid": input_actions_guid, "type": 3},
            "m_LeftClickAction": {"fileID": 3001919216989983466, "guid": input_actions_guid, "type": 3},
            "m_MiddleClickAction": {"fileID": -2185481485913320682, "guid": input_actions_guid, "type": 3},
            "m_RightClickAction": {"fileID": -4090225696740746782, "guid": input_actions_guid, "type": 3},
            "m_ScrollWheelAction": {"fileID": 6240969308177333660, "guid": input_actions_guid, "type": 3},
            "m_TrackedDevicePositionAction": {"fileID": 6564999863303420839, "guid": input_actions_guid, "type": 3},
            "m_TrackedDeviceOrientationAction": {"fileID": 7970375526676320489, "guid": input_actions_guid, "type": 3},
            "m_DeselectOnBackgroundClick": 1,
            "m_PointerBehavior": 0,
            "m_CursorLockBehavior": 0,
            "m_ScrollDeltaPerTick": 6,
        },
    )

    doc.add_object(go)
    doc.add_object(transform)
    doc.add_object(eventsystem)
    doc.add_object(inputmodule)

    print("EventSystem created")
    return go_id

# 사용 예시
doc = UnityYAMLDocument.load("Scene.unity")
ensure_event_system(doc)
# ... Canvas 및 UI 요소 생성 ...
doc.save("Scene.unity")
```

### UI 씬 설정 체크리스트

UI가 포함된 씬을 생성할 때 다음 순서를 따르세요:

1. **EventSystem 확인/생성** - UI 입력 처리를 위해 필수
2. **Canvas 생성** - CanvasScaler, GraphicRaycaster 포함
3. **UI 요소 배치** - Button, Image, Text 등

```python
# 완전한 UI 씬 설정 예시
doc = UnityYAMLDocument.load("Scene.unity")

# 1. EventSystem (없으면 생성)
ensure_event_system(doc)

# 2. Canvas 생성
canvas_go_id = doc.generate_unique_file_id()
# ... Canvas, CanvasScaler, GraphicRaycaster 생성 ...

# 3. UI 요소 생성
# ... Button, Image, Text 등 ...

doc.save("Scene.unity")
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

## 프리팹 참조 연결하기

MonoBehaviour의 프리팹 배열 필드(`GameObject[]` 등)에 프리팹을 연결할 때는 올바른 형식을 사용해야 합니다.

### 프리팹 참조 형식

프리팹 참조는 3가지 값으로 구성됩니다:

```json
{
  "fileID": 3538220432101258543,  // 프리팹 내부 root GameObject의 fileID
  "guid": "abd4ca9175669424ea5690fa080e9251",  // 프리팹 .meta 파일의 GUID
  "type": 3  // PrefabInstance 타입
}
```

### 중요: fileID는 프리팹마다 다름!

⚠️ **각 프리팹은 고유한 root fileID를 가집니다.** 모든 프리팹에 동일한 fileID(예: `5355583096506721055`)를 사용하면 "missing" 오류가 발생합니다.

### fileID 추출 방법

프리팹의 root fileID는 프리팹 파일 내부에 저장되어 있습니다:

```bash
# 프리팹을 JSON으로 내보내기
prefab-tool export "Assets/Prefabs/MyPrefab.prefab" --output temp.json

# Python으로 root fileID 추출
python -c "
import json
with open('temp.json', 'r') as f:
    data = json.load(f)
gos = data.get('gameObjects', {})
if gos:
    root_file_id = list(gos.keys())[0]
    print(f'Root fileID: {root_file_id}')
"
```

### 일괄 추출 예시

여러 프리팹의 fileID와 GUID를 한번에 추출:

```python
import json
import os
import subprocess

def get_prefab_ref(prefab_path):
    """프리팹의 참조 정보(fileID, guid) 추출"""
    # GUID는 .meta 파일에서 추출
    meta_path = f"{prefab_path}.meta"
    guid = None
    if os.path.exists(meta_path):
        with open(meta_path, 'r') as f:
            for line in f:
                if line.startswith('guid:'):
                    guid = line.split(':')[1].strip()
                    break

    # fileID는 프리팹 내부에서 추출
    subprocess.run(['prefab-tool', 'export', prefab_path, '--output', 'temp.json'],
                   capture_output=True)

    file_id = None
    if os.path.exists('temp.json'):
        with open('temp.json', 'r') as f:
            data = json.load(f)
        gos = data.get('gameObjects', {})
        if gos:
            file_id = int(list(gos.keys())[0])
        os.remove('temp.json')

    return {
        "fileID": file_id,
        "guid": guid,
        "type": 3
    }

# 사용 예시
ref = get_prefab_ref("Assets/Prefabs/Player.prefab")
print(ref)
# 출력: {"fileID": 1234567890123456789, "guid": "abc123...", "type": 3}
```

### MonoBehaviour에 프리팹 배열 연결

씬이나 프리팹의 MonoBehaviour에 프리팹 배열을 연결하는 전체 예시:

```python
import json
import subprocess

# 1. 씬 내보내기
subprocess.run(['prefab-tool', 'export', 'Assets/Scenes/Main.unity',
                '--output', 'scene.json'])

with open('scene.json', 'r', encoding='utf-8') as f:
    scene = json.load(f)

# 2. 대상 MonoBehaviour 찾기 (scriptRef의 guid로 식별)
target_guid = "YOUR_SCRIPT_GUID"
target_component_id = None

for file_id, comp in scene.get('components', {}).items():
    if isinstance(comp, dict):
        script_ref = comp.get('scriptRef', {})
        if script_ref.get('guid') == target_guid:
            target_component_id = file_id
            break

# 3. 프리팹 참조 배열 생성
prefab_refs = [
    {"fileID": 3538220432101258543, "guid": "abd4ca917...", "type": 3},
    {"fileID": 1278814736312916979, "guid": "9e7ddb713...", "type": 3},
]

# 4. 프로퍼티 업데이트
scene['components'][target_component_id]['properties']['myPrefabArray'] = prefab_refs

# 5. 저장 및 임포트
with open('scene.json', 'w', encoding='utf-8') as f:
    json.dump(scene, f, indent=2)

subprocess.run(['prefab-tool', 'import', 'scene.json',
                '--output', 'Assets/Scenes/Main.unity'])
```

---

## 에셋 참조 연결하기

MonoBehaviour 필드에 AudioClip, ScriptableObject 등의 에셋을 연결할 때는 에셋 타입별로 올바른 fileID를 사용해야 합니다.

### 에셋 타입별 fileID

⚠️ **중요**: fileID는 에셋 타입에 따라 다릅니다. 잘못된 fileID를 사용하면 "Missing" 오류가 발생합니다.

| 에셋 타입 | fileID | type | 설명 |
|----------|--------|------|------|
| AudioClip (.wav, .mp3, .ogg) | `8300000` | 3 | 오디오 파일 |
| ScriptableObject (.asset) | `11400000` | 2 | ScriptableObject 에셋 |
| Prefab (.prefab) | 프리팹별 다름 | 3 | 프리팹의 root GameObject fileID |
| Texture2D (.png, .jpg) | `2800000` | 3 | 텍스처 파일 |
| Sprite | `21300000` | 3 | 스프라이트 (텍스처에서 추출) |
| Material (.mat) | `2100000` | 2 | 머티리얼 |

### AudioClip 참조 예시

```json
{
  "fileID": 8300000,
  "guid": "64f4d9eeadd03cf428c0a0b29e82648a",
  "type": 3
}
```

### ScriptableObject 참조 예시

```json
{
  "fileID": 11400000,
  "guid": "5b6d5b5cf85254e4b9a4133a62f8488e",
  "type": 2
}
```

### GUID 추출 방법

에셋의 GUID는 `.meta` 파일에서 추출합니다:

```bash
# 단일 파일
grep "guid:" "Assets/Audio/Drum/kick-808.wav.meta"
# 출력: guid: 64f4d9eeadd03cf428c0a0b29e82648a

# 여러 파일 한번에
grep -r "guid:" Assets/Audio/Drum/*.meta | head -10
```

### AudioClip 배열 연결 예시

```python
import json
import subprocess

# 씬 내보내기
subprocess.run(['prefab-tool', 'export', 'Assets/Scenes/Main.unity', '-o', 'scene.json'])

with open('scene.json', 'r', encoding='utf-8') as f:
    scene = json.load(f)

# AudioManager 컴포넌트 찾아서 drumKit 설정
for comp_id, comp in scene.get('components', {}).items():
    if comp.get('classId') == 114:
        props = comp.get('properties', {})
        if 'drumKit' in props:
            # AudioClip 참조: fileID는 8300000!
            props['drumKit']['kick'] = {
                'fileID': 8300000,
                'guid': '64f4d9eeadd03cf428c0a0b29e82648a',
                'type': 3
            }
            props['drumKit']['snare'] = {
                'fileID': 8300000,
                'guid': '8ef0341c78f36174990a9595639302d0',
                'type': 3
            }
            # ... 나머지 클립들

            # _rawFields도 동일하게 업데이트
            if comp_id in scene.get('_rawFields', {}):
                scene['_rawFields'][comp_id]['drumKit'] = props['drumKit']
            break

with open('scene.json', 'w', encoding='utf-8') as f:
    json.dump(scene, f, indent=2)

subprocess.run(['prefab-tool', 'import', 'scene.json', '-o', 'Assets/Scenes/Main.unity'])
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

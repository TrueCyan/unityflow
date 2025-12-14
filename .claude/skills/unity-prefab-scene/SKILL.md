---
name: unity-prefab-scene
description: Unity 프리팹(.prefab), 씬(.unity), ScriptableObject(.asset) 파일을 편집합니다. prefab-tool을 사용하여 프리팹 분석, JSON 변환, GameObject 생성/수정/삭제/복제, UI 레이아웃 조정, 컴포넌트 추가/삭제, 스프라이트 연결, ScriptableObject 편집 등의 작업을 수행합니다.
---

# Unity Prefab, Scene & ScriptableObject Editing Skill

Unity 프리팹(.prefab), 씬(.unity), ScriptableObject(.asset) 파일을 프로그래매틱하게 편집하기 위한 skill입니다.

---

## ⚠️ 필수 규칙: prefab-tool 사용 의무

### 절대 금지 사항

**Unity YAML 파일(.prefab, .unity, .asset)을 직접 텍스트 편집하지 마세요!**

- ❌ `Read` 도구로 YAML 직접 읽기 후 `Edit`/`Write`로 수정
- ❌ Python으로 YAML 파일 직접 파싱/수정
- ❌ sed, awk 등으로 텍스트 치환

### 반드시 해야 할 것

**모든 Unity 파일 조작은 `prefab-tool` CLI를 통해서만 수행합니다:**

- ✅ `prefab-tool query` - 데이터 조회 및 검색
- ✅ `prefab-tool set` - 값 수정 (단일 값, 배치 수정, 새 필드 생성)
- ✅ `prefab-tool add-object` / `delete-object` / `clone-object` - GameObject 조작
- ✅ `prefab-tool add-component` / `delete-component` - 컴포넌트 조작
- ✅ `prefab-tool sprite-link` - 스프라이트 연결
- ✅ `prefab-tool export` + `prefab-tool import` - 복잡한 구조 편집
- ✅ `prefab-tool scan-meta` / `scan-scripts` - GUID 조회

### 이유

Unity YAML은 특수한 형식을 사용합니다:
- 태그 별칭 (`--- !u!1 &12345`)
- 결정론적 필드 순서
- 특수 참조 형식

직접 편집 시 Unity에서 파일을 읽지 못하거나 데이터가 손실될 수 있습니다.

---

## CLI 명령어 레퍼런스

### 조회 명령어

```bash
# 파일 통계 확인
prefab-tool stats Player.prefab
prefab-tool stats MainScene.unity
prefab-tool stats GameConfig.asset

# 구조 요약 보기
prefab-tool query Player.prefab
prefab-tool query MainScene.unity

# 특정 데이터 쿼리
prefab-tool query Player.prefab --path "gameObjects/*/name"
prefab-tool query MainScene.unity --path "components/*/type" --format json

# 이름으로 GameObject 찾기 (와일드카드 지원)
prefab-tool query Scene.unity --find-name "Player*"
prefab-tool query Scene.unity --find-name "*Enemy*"

# 컴포넌트 타입으로 GameObject 찾기
prefab-tool query Scene.unity --find-component "SpriteRenderer"
prefab-tool query Scene.unity --find-component "Light2D"

# 스크립트 GUID로 MonoBehaviour 찾기
prefab-tool query Scene.unity --find-script "abc123def456..."
```

### 값 수정 (set)

```bash
# 단일 값 설정
prefab-tool set Player.prefab \
    --path "components/12345/localPosition" \
    --value '{"x": 0, "y": 5, "z": 0}'

# 이름 변경
prefab-tool set Player.prefab \
    --path "gameObjects/12345/name" \
    --value '"NewName"'

# 여러 필드 한번에 수정 (batch 모드)
prefab-tool set Scene.unity \
    --path "components/495733805" \
    --batch '{"portalAPrefab": {"fileID": 123, "guid": "abc", "type": 3}, "spawnRate": 2.0}' \
    --create

# 새 필드 생성 (--create 플래그)
prefab-tool set Player.prefab \
    --path "components/12345/newProperty" \
    --value '5.0' \
    --create
```

### GameObject 조작

```bash
# 새 GameObject 추가
prefab-tool add-object Scene.unity --name "Player"
prefab-tool add-object Scene.unity --name "Child" --parent 12345
prefab-tool add-object Scene.unity --name "Enemy" --position "10,0,5"
prefab-tool add-object Scene.unity --name "Button" --ui --parent 67890  # UI용 RectTransform

# GameObject 복제
prefab-tool clone-object Scene.unity --id 12345
prefab-tool clone-object Scene.unity --id 12345 --name "Player2"
prefab-tool clone-object Scene.unity --id 12345 --deep  # 자식 포함 복제

# GameObject 삭제
prefab-tool delete-object Scene.unity --id 12345
prefab-tool delete-object Scene.unity --id 12345 --cascade  # 자식 포함 삭제
```

### 컴포넌트 조작

```bash
# 내장 컴포넌트 추가
prefab-tool add-component Scene.unity --to 12345 --type SpriteRenderer
prefab-tool add-component Scene.unity --to 12345 --type Camera

# MonoBehaviour 추가 (스크립트 GUID 필요)
prefab-tool add-component Scene.unity --to 12345 --script "abc123..." \
    --props '{"speed": 5.0, "health": 100}'

# 컴포넌트 삭제
prefab-tool delete-component Scene.unity --id 67890
```

### 스프라이트 연결

```bash
# 기본 사용 (fileID 자동 감지)
prefab-tool sprite-link Player.prefab \
    --component 1234567890 \
    --sprite "Assets/Sprites/player.png"

# Multiple 모드 스프라이트의 특정 서브 스프라이트
prefab-tool sprite-link Player.prefab \
    --component 1234567890 \
    --sprite "Assets/Sprites/atlas.png" \
    --sub-sprite "player_idle_0"

# URP 기본 머티리얼 사용
prefab-tool sprite-link Player.prefab \
    --component 1234567890 \
    --sprite "Assets/Sprites/player.png" \
    --use-urp-default

# 미리보기 (실제 변경 없음)
prefab-tool sprite-link Player.prefab \
    --component 1234567890 \
    --sprite "Assets/Sprites/player.png" \
    --dry-run

# 스프라이트 정보 확인
prefab-tool sprite-info "Assets/Sprites/player.png"
```

### JSON 내보내기/가져오기

구조적 변경(대량 편집, 복잡한 계층 수정)이 필요한 경우:

```bash
# JSON으로 내보내기
prefab-tool export Player.prefab -o player.json
prefab-tool export MainScene.unity -o scene.json
prefab-tool export GameConfig.asset -o config.json

# JSON 파일 편집 후 다시 Unity 파일로 변환
prefab-tool import player.json -o Player.prefab
prefab-tool import scene.json -o MainScene.unity
prefab-tool import config.json -o GameConfig.asset
```

### 검증 및 정규화

```bash
# 파일 검증
prefab-tool validate Player.prefab
prefab-tool validate MainScene.unity
prefab-tool validate GameConfig.asset

# 정규화 (Git 노이즈 제거) - 필드 정렬 기본 적용
prefab-tool normalize Player.prefab
prefab-tool normalize MainScene.unity
```

### GUID 조회

```bash
# 파일에서 사용 중인 스크립트 GUID 추출
prefab-tool scan-scripts Scene.unity --show-properties

# 패키지 폴더에서 GUID 추출
prefab-tool scan-meta "Library/PackageCache/com.unity.ugui@*" -r --filter Button

# 프로젝트 스크립트 GUID 추출
prefab-tool scan-meta Assets/Scripts -r --scripts-only
```

### 기타 유용한 명령어

```bash
# 의존성 분석
prefab-tool deps Player.prefab
prefab-tool deps Player.prefab --type Texture
prefab-tool deps Player.prefab --unresolved-only

# 역참조 검색
prefab-tool find-refs Textures/player.png

# 두 파일 비교
prefab-tool diff Player.prefab Player_backup.prefab
```

---

## JSON 형식

### 내보낸 JSON 구조

```json
{
  "metadata": {
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

**`editorValues`를 수정하면 자동으로 파일 값으로 변환됩니다** (권장)

---

## 에셋 참조 연결하기

MonoBehaviour 필드에 에셋을 연결할 때는 에셋 타입별로 올바른 fileID를 사용해야 합니다.

### 에셋 타입별 fileID

| 에셋 타입 | fileID | type | 설명 |
|----------|--------|------|------|
| AudioClip (.wav, .mp3, .ogg) | `8300000` | 3 | 오디오 파일 |
| ScriptableObject (.asset) | `11400000` | 2 | ScriptableObject 에셋 |
| Prefab (.prefab) | 프리팹별 다름 | 3 | 프리팹의 root GameObject fileID |
| Texture2D (.png, .jpg) | `2800000` | 3 | 텍스처 파일 |
| Sprite (Single) | `21300000` | 3 | 단일 스프라이트 |
| Sprite (Multiple) | meta에서 추출 | 3 | 멀티플 스프라이트 (internalID 사용) |
| Material (.mat) | `2100000` | 2 | 머티리얼 |

### 참조 형식 예시

```json
// AudioClip
{"fileID": 8300000, "guid": "64f4d9eeadd03cf428c0a0b29e82648a", "type": 3}

// ScriptableObject
{"fileID": 11400000, "guid": "5b6d5b5cf85254e4b9a4133a62f8488e", "type": 2}

// Prefab (fileID는 프리팹마다 다름!)
{"fileID": 3538220432101258543, "guid": "abd4ca9175669424ea5690fa080e9251", "type": 3}
```

### GUID 추출 방법

```bash
# .meta 파일에서 추출
grep "guid:" "Assets/Audio/sound.wav.meta"
```

---

## ScriptableObject 편집

ScriptableObject(.asset) 파일도 Unity YAML 형식을 사용합니다.

### YAML 구조

```yaml
%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!114 &11400000
MonoBehaviour:
  m_ObjectHideFlags: 0
  m_CorrespondingSourceObject: {fileID: 0}
  m_PrefabInstance: {fileID: 0}
  m_PrefabAsset: {fileID: 0}
  m_GameObject: {fileID: 0}
  m_Enabled: 1
  m_EditorHideFlags: 0
  m_Script: {fileID: 11500000, guid: YOUR_SCRIPT_GUID, type: 3}
  m_Name: AssetName
  m_EditorClassIdentifier:
  # 스크립트의 SerializeField 값들...
  myField: value
```

**핵심 포인트:**
- classId: `114` (MonoBehaviour)
- fileID: `11400000` (ScriptableObject 표준)
- `m_Script.guid`: ScriptableObject 스크립트의 GUID

### .meta 파일 생성

ScriptableObject 에셋을 생성할 때 반드시 `.meta` 파일도 함께 생성해야 합니다:

```yaml
fileFormatVersion: 2
guid: UNIQUE_GUID_FOR_THIS_ASSET
NativeFormatImporter:
  externalObjects: {}
  mainObjectFileID: 11400000
  userData:
  assetBundleName:
  assetBundleVariant:
```

---

## Python API (복잡한 경우)

대부분의 작업은 CLI로 가능하지만, 복잡한 자동화가 필요한 경우 Python API를 사용합니다.

> ⚠️ **주의**: Python API는 `prefab-tool export` → JSON 수정 → `prefab-tool import` 워크플로우에서 JSON 파일을 수정할 때만 사용하세요.

```python
from prefab_tool.parser import (
    UnityYAMLDocument,
    create_game_object,
    create_transform,
    create_rect_transform,
    create_mono_behaviour,
)
from prefab_tool.formats import (
    export_to_json,
    import_from_json,
    create_rect_transform_file_values,
)

# Unity YAML 파일 로드 (.prefab, .unity, .asset)
doc = UnityYAMLDocument.load("Player.prefab")
doc = UnityYAMLDocument.load("MainScene.unity")
doc = UnityYAMLDocument.load("GameConfig.asset")

# 고유 ID 생성
go_id = doc.generate_unique_file_id()
transform_id = doc.generate_unique_file_id()

# GameObject 생성
go = create_game_object(
    name="NewObject",
    file_id=go_id,
    components=[transform_id],
)

# Transform 생성
transform = create_transform(
    game_object_id=go_id,
    file_id=transform_id,
    position={"x": 0, "y": 1, "z": 0},
)

# 문서에 추가
doc.add_object(go)
doc.add_object(transform)
doc.save("output.prefab")  # 또는 .unity, .asset
```

### 앵커 프리셋 (RectTransform)

| 프리셋 | 설명 |
|--------|------|
| `center` | 중앙 (0.5, 0.5) |
| `top-left`, `top-center`, `top-right` | 상단 |
| `middle-left`, `middle-center`, `middle-right` | 중앙 행 |
| `bottom-left`, `bottom-center`, `bottom-right` | 하단 |
| `stretch-top`, `stretch-middle`, `stretch-bottom` | 가로 스트레치 |
| `stretch-left`, `stretch-center`, `stretch-right` | 세로 스트레치 |
| `stretch-all` | 전체 스트레치 |

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
| 108 | Light | 3D 라이트 |
| 114 | MonoBehaviour | **사용자 스크립트 (기본 사용)** |
| 212 | SpriteRenderer | 스프라이트 렌더러 |
| 222 | CanvasRenderer | 캔버스 렌더러 |
| 223 | Canvas | UI 캔버스 |
| 224 | RectTransform | UI 트랜스폼 |
| 225 | CanvasGroup | 캔버스 그룹 |
| 1001 | PrefabInstance | 프리팹 인스턴스 |

**참고**: 패키지 컴포넌트(Light2D, TextMeshPro 등)는 `MonoBehaviour(114)`를 사용하며, 스크립트 GUID로 구분됩니다.

---

## 패키지 컴포넌트 GUID 참조

Unity 패키지 컴포넌트들은 **MonoBehaviour(classId=114)**로 구현되며, 스크립트 GUID로 식별됩니다.

### Unity UI 컴포넌트 (com.unity.ugui)

| 컴포넌트 | GUID |
|----------|------|
| Image | `fe87c0e1cc204ed48ad3b37840f39efc` |
| Button | `4e29b1a8efbd4b44bb3f3716e73f07ff` |
| ScrollRect | `1aa08ab6e0800fa44ae55d278d1423e3` |
| Mask | `31a19414c41e5ae4aae2af33fee712f6` |
| RectMask2D | `3312d7739989d2b4e91e6319e9a96d76` |
| GraphicRaycaster | `dc42784cf147c0c48a680349fa168899` |
| CanvasScaler | `0cd44c1031e13a943bb63640046fad76` |
| VerticalLayoutGroup | `59f8146938fff824cb5fd77236b75775` |
| HorizontalLayoutGroup | `30649d3a9faa99c48a7b1166b86bf2a0` |
| ContentSizeFitter | `3245ec927659c4140ac4f8d17403cc18` |
| TextMeshProUGUI | `f4688fdb7df04437aeb418b961361dc5` |
| TMP_InputField | `2da0c512f12947e489f739169773d7ca` |
| EventSystem | `76c392e42b5098c458856cdf6ecaaaa1` |
| InputSystemUIInputModule | `01614664b831546d2ae94a42149d80ac` |

### 렌더링 컴포넌트

| 패키지 | 컴포넌트 | GUID |
|--------|----------|------|
| URP 2D | Light2D | `073797afb82c5a1438f328866b10b3f0` |

### GUID 조회 방법

```bash
# 패키지 폴더에서 직접 추출
grep "guid:" "Library/PackageCache/com.unity.ugui@*/Runtime/UGUI/UI/Core/Button.cs.meta"

# scan-meta로 패키지 스캔
prefab-tool scan-meta "Library/PackageCache/com.unity.ugui@*" -r --scripts-only

# 사용 중인 스크립트 GUID 추출
prefab-tool scan-scripts Scene.unity --show-properties
```

---

## 주의사항

1. **항상 백업**: 원본 파일을 수정하기 전에 백업하거나 `-o` 옵션으로 새 파일에 저장
2. **fileID 충돌 방지**: 새 오브젝트 생성 시 `doc.generate_unique_file_id()` 사용
3. **정규화 필수**: 편집 후 `prefab-tool normalize`로 정규화하여 Git 노이즈 방지
4. **검증 권장**: 중요한 수정 후 `prefab-tool validate`로 무결성 확인
5. **GUID 보존**: 외부 에셋 참조(스크립트, 텍스처 등)의 GUID는 변경하지 않음
6. **classId 보존**: **절대로 임의의 classId를 사용하지 마세요!** 새 컴포넌트 추가 시 반드시 올바른 classId 사용
7. **Mask + Image 알파값**: Mask 컴포넌트 사용 시 Image 알파값이 0이면 마스킹이 작동하지 않음. `m_Color.a: 1` 설정 후 `m_ShowMaskGraphic: 0`으로 숨기기
8. **EventSystem 필수**: UI가 클릭에 반응하려면 씬에 반드시 EventSystem이 있어야 함

### classId 관련 중요 경고

⚠️ **절대 SceneRoots classId(1660057539)를 다른 컴포넌트에 사용하지 마세요!**

잘못된 classId 사용 시:
- "cast failed from SceneRoots to Component" 오류 발생
- 컴포넌트가 로드되지 않고 제거됨
- 씬 파일이 손상될 수 있음

---

## 문제 해결

### 파싱 오류 발생 시

```bash
prefab-tool stats problematic.prefab --format json
prefab-tool validate problematic.prefab --format json
```

### JSON 왕복 변환 시 데이터 손실 방지

`_rawFields`를 포함하여 내보내기:

```bash
prefab-tool export Player.prefab -o player.json  # --no-raw 없이
```

---
name: unity-prefab-scene
description: Unity 프리팹(.prefab), 씬(.unity), ScriptableObject(.asset) 파일을 편집합니다. unityflow을 사용하여 프리팹 분석, JSON 변환, GameObject 생성/수정/삭제/복제, UI 레이아웃 조정, 컴포넌트 추가/삭제, 스프라이트 연결, ScriptableObject 편집 등의 작업을 수행합니다.
---

# Unity Prefab, Scene & ScriptableObject Editing Skill

Unity 프리팹(.prefab), 씬(.unity), ScriptableObject(.asset) 파일을 프로그래매틱하게 편집하기 위한 skill입니다.

---

## ⚠️ 필수 규칙: unityflow 사용 의무

### 절대 금지 사항

**Unity YAML 파일(.prefab, .unity, .asset)을 직접 텍스트 편집하지 마세요!**

- ❌ `Read` 도구로 YAML 직접 읽기 후 `Edit`/`Write`로 수정
- ❌ Python으로 YAML 파일 직접 파싱/수정
- ❌ sed, awk 등으로 텍스트 치환

### 반드시 해야 할 것

**모든 Unity 파일 조작은 `unityflow` CLI를 통해서만 수행합니다:**

- ✅ `unityflow query` - 데이터 조회 및 검색
- ✅ `unityflow set` - 값 수정 (단일 값, 배치 수정, 새 필드 생성)
- ✅ `unityflow set --value "@에셋경로"` - 에셋 참조 (GUID/fileID 자동 해석)
- ✅ `unityflow add-object` / `delete-object` / `clone-object` - GameObject 조작
- ✅ `unityflow add-component` / `delete-component` - 컴포넌트 조작
- ✅ `unityflow export` + `unityflow import` - 복잡한 구조 편집
- ✅ `unityflow scan-meta` / `scan-scripts` - GUID 조회

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
unityflow stats Player.prefab
unityflow stats MainScene.unity
unityflow stats GameConfig.asset

# 구조 요약 보기
unityflow query Player.prefab
unityflow query MainScene.unity

# 특정 데이터 쿼리
unityflow query Player.prefab --path "gameObjects/*/name"
unityflow query MainScene.unity --path "components/*/type" --format json

# 이름으로 GameObject 찾기 (와일드카드 지원)
unityflow query Scene.unity --find-name "Player*"
unityflow query Scene.unity --find-name "*Enemy*"

# 컴포넌트 타입으로 GameObject 찾기
unityflow query Scene.unity --find-component "SpriteRenderer"
unityflow query Scene.unity --find-component "Light2D"

# 스크립트 GUID로 MonoBehaviour 찾기
unityflow query Scene.unity --find-script "abc123def456..."
```

### 값 수정 (set)

`set` 명령어는 2가지 모드를 지원합니다 (상호 배타적):
- `--value`: 단일 값 설정
- `--batch`: 여러 필드 한번에 설정

**에셋 참조 자동 해석**: `@` 접두사로 에셋 경로를 지정하면 GUID와 fileID가 자동으로 해석됩니다.

```bash
# Transform 위치 설정
unityflow set Player.prefab \
    --path "Player/Transform/localPosition" \
    --value '{"x": 0, "y": 5, "z": 0}'

# SpriteRenderer 색상 설정
unityflow set Player.prefab \
    --path "Player/SpriteRenderer/m_Color" \
    --value '{"r": 1, "g": 0, "b": 0, "a": 1}'

# GameObject 이름 변경
unityflow set Player.prefab \
    --path "Player/name" \
    --value '"NewName"'

# 에셋 참조 (@ 접두사로 자동 해석)
unityflow set Scene.unity \
    --path "Canvas/Panel/Button/Image/m_Sprite" \
    --value "@Assets/Sprites/icon.png"

# 여러 필드 한번에 수정 (batch 모드)
unityflow set Scene.unity \
    --path "Player/MonoBehaviour" \
    --batch '{"speed": 5.0, "health": 100}' \
    --create
```

### GameObject 조작

```bash
# 새 GameObject 추가
unityflow add-object Scene.unity --name "Player"
unityflow add-object Scene.unity --name "Child" --parent 12345
unityflow add-object Scene.unity --name "Enemy" --position "10,0,5"
unityflow add-object Scene.unity --name "Button" --ui --parent 67890  # UI용 RectTransform

# GameObject 복제
unityflow clone-object Scene.unity --id "Player"
unityflow clone-object Scene.unity --id "Player" --name "Player2"
unityflow clone-object Scene.unity --id "Canvas/Panel" --deep  # 자식 포함 복제

# GameObject 삭제
unityflow delete-object Scene.unity --id "Enemy"
unityflow delete-object Scene.unity --id "Canvas/Panel" --cascade  # 자식 포함 삭제
```

### 컴포넌트 조작

```bash
# 컴포넌트 추가 (경로로 대상 지정)
unityflow add-component Scene.unity --to "Player" --type SpriteRenderer
unityflow add-component Scene.unity --to "Canvas/Panel/Button" --type Image

# MonoBehaviour 추가 (스크립트 GUID 필요)
unityflow add-component Scene.unity --to "Player" --script "abc123..." \
    --props '{"speed": 5.0, "health": 100}'

# 컴포넌트 삭제 (컴포넌트 fileID 필요)
unityflow delete-component Scene.unity --id 67890
```

### 에셋 참조 자동 해석 (@ 접두사)

`@` 접두사를 사용하면 에셋 경로에서 GUID와 fileID가 자동으로 해석됩니다.
에셋의 `.meta` 파일을 읽어서 정확한 참조 정보를 생성합니다.

```bash
# 스프라이트 연결 (Single 모드)
unityflow set Player.prefab \
    --path "Player/SpriteRenderer/m_Sprite" \
    --value "@Assets/Sprites/player.png"

# 스프라이트 연결 (Multiple 모드 - 서브 스프라이트)
unityflow set Player.prefab \
    --path "Player/SpriteRenderer/m_Sprite" \
    --value "@Assets/Sprites/atlas.png:player_idle_0"

# UI Image 스프라이트 연결
unityflow set Scene.unity \
    --path "Canvas/Panel/Button/Image/m_Sprite" \
    --value "@Assets/Sprites/icon.png"

# 프리팹 참조 연결 (MonoBehaviour 필드)
unityflow set Scene.unity \
    --path "Player/MonoBehaviour/enemyPrefab" \
    --value "@Assets/Prefabs/Enemy.prefab" \
    --create

# 여러 에셋 참조를 한번에 (batch 모드)
unityflow set Scene.unity \
    --path "Player/MonoBehaviour" \
    --batch '{
        "playerPrefab": "@Assets/Prefabs/Player.prefab",
        "enemyPrefab": "@Assets/Prefabs/Enemy.prefab",
        "spawnRate": 2.0
    }' \
    --create

# 스프라이트 정보 확인
unityflow sprite-info "Assets/Sprites/player.png"
```

**지원 에셋 타입:**

| 에셋 타입 | 예시 |
|----------|------|
| Script | `@Assets/Scripts/Player.cs` |
| Sprite (Single) | `@Assets/Sprites/icon.png` |
| Sprite (Multiple) | `@Assets/Sprites/atlas.png:idle_0` |
| AudioClip | `@Assets/Audio/jump.wav` |
| Material | `@Assets/Materials/Custom.mat` |
| Prefab | `@Assets/Prefabs/Enemy.prefab` |
| ScriptableObject | `@Assets/Data/Config.asset` |
| Animation | `@Assets/Animations/walk.anim` |

### JSON 내보내기/가져오기

구조적 변경(대량 편집, 복잡한 계층 수정)이 필요한 경우:

```bash
# JSON으로 내보내기
unityflow export Player.prefab -o player.json
unityflow export MainScene.unity -o scene.json
unityflow export GameConfig.asset -o config.json

# JSON 파일 편집 후 다시 Unity 파일로 변환
unityflow import player.json -o Player.prefab
unityflow import scene.json -o MainScene.unity
unityflow import config.json -o GameConfig.asset
```

### 검증 및 정규화

```bash
# 파일 검증
unityflow validate Player.prefab
unityflow validate MainScene.unity
unityflow validate GameConfig.asset

# 정규화 (Git 노이즈 제거) - 필드 정렬 기본 적용
unityflow normalize Player.prefab
unityflow normalize MainScene.unity
```

### GUID 조회

```bash
# 파일에서 사용 중인 스크립트 GUID 추출
unityflow scan-scripts Scene.unity --show-properties

# 패키지 폴더에서 GUID 추출
unityflow scan-meta "Library/PackageCache/com.unity.ugui@*" -r --filter Button

# 프로젝트 스크립트 GUID 추출
unityflow scan-meta Assets/Scripts -r --scripts-only
```

### .meta 파일 생성 (generate-meta)

새 파일이나 폴더를 Unity 프로젝트에 추가할 때 `.meta` 파일이 필요합니다. Unity를 열지 않고도 `.meta` 파일을 생성할 수 있습니다.

```bash
# 단일 파일에 대해 meta 생성
unityflow generate-meta Assets/Scripts/Player.cs

# 여러 파일 한번에 처리
unityflow generate-meta Assets/Textures/*.png

# 폴더 전체를 재귀적으로 처리
unityflow generate-meta Assets/NewFolder -r

# 스프라이트로 생성 (PPU 지정 가능)
unityflow generate-meta icon.png --sprite --ppu 32

# 결정론적 GUID 생성 (재현 가능한 빌드용)
unityflow generate-meta Assets/Data/config.json --seed "config.json"

# 특정 GUID 지정
unityflow generate-meta MyScript.cs --guid "abcd1234efgh5678ijkl9012mnop3456"

# 미리보기 (실제 파일 생성 안함)
unityflow generate-meta Assets/ -r --dry-run

# 기존 meta 파일 덮어쓰기
unityflow generate-meta Player.cs --overwrite
```

**지원 에셋 타입:**
- **스크립트** (.cs) → `MonoImporter`
- **텍스처** (.png, .jpg, .psd, .tga 등) → `TextureImporter`
- **오디오** (.wav, .mp3, .ogg 등) → `AudioImporter`
- **3D 모델** (.fbx, .obj 등) → `ModelImporter`
- **셰이더** (.shader, .hlsl) → `ShaderImporter`
- **Unity YAML** (.prefab, .unity, .asset, .mat) → `DefaultImporter`
- **폴더** → `DefaultImporter` (folderAsset: yes)

### .meta 파일 수정 (modify-meta)

```bash
# 현재 설정 확인
unityflow modify-meta icon.png.meta --info

# 텍스처를 스프라이트로 변경
unityflow modify-meta icon.png --sprite-mode single

# 스프라이트 설정 (PPU, 필터)
unityflow modify-meta icon.png --sprite-mode single --ppu 32 --filter point

# 텍스처 최대 크기 설정
unityflow modify-meta icon.png --max-size 512

# 스크립트 실행 순서 설정
unityflow modify-meta Player.cs --execution-order -100

# 에셋 번들 설정
unityflow modify-meta Player.prefab --bundle-name "characters" --bundle-variant "hd"

# 에셋 번들 해제
unityflow modify-meta Player.prefab --bundle-name ""
```

**수정 가능한 옵션:**
- **텍스처**: `--sprite-mode`, `--ppu`, `--filter`, `--max-size`
- **스크립트**: `--execution-order`
- **모든 에셋**: `--bundle-name`, `--bundle-variant`

### 기타 유용한 명령어

```bash
# 의존성 분석
unityflow deps Player.prefab
unityflow deps Player.prefab --type Texture
unityflow deps Player.prefab --unresolved-only

# 역참조 검색
unityflow find-refs Textures/player.png

# 두 파일 비교
unityflow diff Player.prefab Player_backup.prefab
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

## Python API (복잡한 경우)

대부분의 작업은 CLI로 가능하지만, 복잡한 자동화가 필요한 경우 Python API를 사용합니다.

> ⚠️ **주의**: Python API는 `unityflow export` → JSON 수정 → `unityflow import` 워크플로우에서 JSON 파일을 수정할 때만 사용하세요.

```python
from unityflow.parser import (
    UnityYAMLDocument,
    create_game_object,
    create_transform,
    create_rect_transform,
    create_mono_behaviour,
)
from unityflow.formats import (
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

---

## 컴포넌트 추가 (add-component)

`--to`로 대상 GameObject 경로를 지정하고 `--type`으로 컴포넌트를 추가합니다.

```bash
# 기본 사용
unityflow add-component Scene.unity --to "Player" --type SpriteRenderer
unityflow add-component Scene.unity --to "Canvas/Panel/Button" --type Image

# 같은 경로에 동일 이름이 여러 개일 때 인덱스 사용
unityflow add-component Scene.unity --to "Canvas/Panel/Button[1]" --type Image

# 속성과 함께 추가
unityflow add-component Scene.unity --to "Canvas/Panel" --type Image \
    --props '{"m_Color": {"r": 1, "g": 0, "b": 0, "a": 1}}'
```

### 지원 컴포넌트

| 카테고리 | 컴포넌트 |
|----------|----------|
| **빌트인** | SpriteRenderer, Camera, Light, AudioSource, BoxCollider2D, CircleCollider2D, Rigidbody2D |
| **UI** | Image, Button, ScrollRect, Mask, RectMask2D, GraphicRaycaster, CanvasScaler |
| **레이아웃** | VerticalLayoutGroup, HorizontalLayoutGroup, ContentSizeFitter |
| **텍스트** | TextMeshProUGUI, TMP_InputField |
| **시스템** | EventSystem, InputSystemUIInputModule |
| **렌더링** | Light2D |

### 커스텀 스크립트 추가

프로젝트 스크립트는 `--script` 옵션으로 GUID를 지정합니다:

```bash
unityflow add-component Scene.unity --to "Player" --script "abc123def456..."
```

스크립트 GUID 조회:

```bash
unityflow scan-scripts Scene.unity --show-properties
unityflow scan-meta Assets/Scripts -r --scripts-only
```

---

## 주의사항

1. **항상 백업**: 원본 파일을 수정하기 전에 백업하거나 `-o` 옵션으로 새 파일에 저장
2. **fileID 충돌 방지**: 새 오브젝트 생성 시 `doc.generate_unique_file_id()` 사용
3. **정규화 필수**: 편집 후 `unityflow normalize`로 정규화하여 Git 노이즈 방지
4. **검증 권장**: 중요한 수정 후 `unityflow validate`로 무결성 확인
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
unityflow stats problematic.prefab --format json
unityflow validate problematic.prefab --format json
```

### JSON 왕복 변환 시 데이터 손실 방지

`_rawFields`를 포함하여 내보내기:

```bash
unityflow export Player.prefab -o player.json  # --no-raw 없이
```

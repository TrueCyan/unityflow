---
name: unity-yaml-workflow
description: Unity YAML 파일(.prefab, .unity, .asset)을 편집합니다. unityflow를 사용하여 프리팹 분석, GameObject 생성/수정/삭제/복제, 컴포넌트 추가/삭제, 에셋 연결, ScriptableObject 편집 등의 작업을 수행합니다.
---

# Unity YAML Workflow Skill

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
- ✅ `unityflow set --value "@에셋경로"` - 에셋 연결
- ✅ `unityflow add-object` / `delete-object` / `clone-object` - GameObject 조작
- ✅ `unityflow add-component` / `delete-component` - 컴포넌트 조작

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

# 스크립트로 MonoBehaviour 찾기
unityflow query Scene.unity --find-script "PlayerController"
```

### 값 수정 (set)

`set` 명령어는 2가지 모드를 지원합니다 (상호 배타적):
- `--value`: 단일 값 설정
- `--batch`: 여러 필드 한번에 설정

**에셋 연결**: `@` 접두사로 에셋 경로를 지정합니다.

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
unityflow add-object Scene.unity --name "Child" --parent "Player"
unityflow add-object Scene.unity --name "Enemy" --position "10,0,5"

# GameObject 복제
unityflow clone-object Scene.unity --id "Player"
unityflow clone-object Scene.unity --id "Player" --name "Player2"
unityflow clone-object Scene.unity --id "Player" --deep  # 자식 포함 복제

# GameObject 삭제
unityflow delete-object Scene.unity --id "Enemy"
unityflow delete-object Scene.unity --id "Parent" --cascade  # 자식 포함 삭제
```

### 컴포넌트 조작

```bash
# 컴포넌트 추가 (경로로 대상 지정)
unityflow add-component Scene.unity --to "Player" --type SpriteRenderer
unityflow add-component Scene.unity --to "Player" --type BoxCollider2D

# 속성과 함께 추가
unityflow add-component Scene.unity --to "Player" --type SpriteRenderer \
    --props '{"m_Color": {"r": 1, "g": 0, "b": 0, "a": 1}}'

# 커스텀 스크립트 추가 (스크립트 이름으로 지정)
unityflow add-component Scene.unity --to "Player" --script PlayerController \
    --props '{"speed": 5.0, "health": 100}'

# 컴포넌트 삭제 (경로로 대상 지정)
unityflow delete-component Scene.unity --from "Player" --type SpriteRenderer

# 커스텀 스크립트 삭제 (스크립트 이름으로 지정)
unityflow delete-component Scene.unity --from "Player" --script PlayerController

# 확인 없이 삭제
unityflow delete-component Scene.unity --from "Player" --type SpriteRenderer --force
```

### 지원 컴포넌트 (일반)

| 카테고리 | 컴포넌트 |
|----------|----------|
| **2D** | SpriteRenderer, BoxCollider2D, CircleCollider2D, Rigidbody2D, Light2D |
| **3D** | Camera, Light, AudioSource |

**참고:** Transform은 삭제할 수 없습니다 (GameObject의 필수 컴포넌트).

### 에셋 연결 (@ 접두사)

`@` 접두사를 사용하여 에셋을 연결합니다.

```bash
# 스프라이트 연결 (Single 모드)
unityflow set Player.prefab \
    --path "Player/SpriteRenderer/m_Sprite" \
    --value "@Assets/Sprites/player.png"

# 스프라이트 연결 (Multiple 모드 - 서브 스프라이트)
unityflow set Player.prefab \
    --path "Player/SpriteRenderer/m_Sprite" \
    --value "@Assets/Sprites/atlas.png:player_idle_0"

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

## 주의사항

1. **항상 백업**: 원본 파일을 수정하기 전에 백업하거나 `-o` 옵션으로 새 파일에 저장
2. **정규화 필수**: 편집 후 `unityflow normalize`로 정규화하여 Git 노이즈 방지
3. **검증 권장**: 중요한 수정 후 `unityflow validate`로 무결성 확인

---

## 문제 해결

### 파싱 오류 발생 시

```bash
unityflow stats problematic.prefab --format json
unityflow validate problematic.prefab --format json
```

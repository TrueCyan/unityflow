---
name: unity-yaml-workflow
description: Unity YAML 파일(.prefab, .unity, .asset)을 편집합니다. unityflow를 사용하여 프리팹 분석, 값 조회/수정, 에셋 연결 등의 작업을 수행합니다.
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

- ✅ `unityflow hierarchy` - 계층 구조 조회
- ✅ `unityflow inspect` - 특정 오브젝트/컴포넌트 상세 조회
- ✅ `unityflow get` - 특정 경로의 값 조회
- ✅ `unityflow set` - 값 수정 (단일 값, 배치 수정)
- ✅ `unityflow set --value "@에셋경로"` - 에셋 연결

### 이유

Unity YAML은 특수한 형식을 사용합니다:
- 태그 별칭 (`--- !u!1 &12345`)
- 결정론적 필드 순서
- 특수 참조 형식

직접 편집 시 Unity에서 파일을 읽지 못하거나 데이터가 손실될 수 있습니다.

---

## CLI 명령어 레퍼런스

### 계층 구조 조회 (hierarchy)

```bash
# 기본 계층 구조 보기
unityflow hierarchy Player.prefab
unityflow hierarchy MainScene.unity

# 컴포넌트 포함하여 보기
unityflow hierarchy Player.prefab --components

# JSON 형식으로 출력
unityflow hierarchy Player.prefab --format json

# 특정 깊이까지만 표시
unityflow hierarchy Scene.unity --depth 2
```

### 오브젝트/컴포넌트 상세 조회 (inspect)

```bash
# GameObject 상세 정보 보기 (경로로 지정)
unityflow inspect Player.prefab "Player"
unityflow inspect Scene.unity "Canvas/Panel/Button"

# 컴포넌트 상세 정보 보기
unityflow inspect Player.prefab "Player/Transform"
unityflow inspect Scene.unity "Player/SpriteRenderer"

# JSON 형식으로 출력
unityflow inspect Player.prefab "Player/Transform" --format json
```

### 값 조회 (get)

```bash
# Transform 위치 조회
unityflow get Player.prefab "Player/Transform/m_LocalPosition"

# SpriteRenderer 색상 조회
unityflow get Player.prefab "Player/SpriteRenderer/m_Color"

# GameObject 이름 조회
unityflow get Player.prefab "Player/name"

# 컴포넌트 전체 속성 조회
unityflow get Player.prefab "Player/Transform"

# 여러 컴포넌트가 있을 때 인덱스로 지정
unityflow get Scene.unity "Canvas/Panel/Image[1]/m_Color"

# 텍스트 형식으로 출력
unityflow get Player.prefab "Player/Transform/m_LocalPosition" --format text
```

### 값 수정 (set)

`set` 명령어는 2가지 모드를 지원합니다 (상호 배타적):
- `--value`: 단일 값 설정
- `--batch`: 여러 필드 한번에 설정

**에셋 연결**: `@` 접두사로 에셋 경로를 지정합니다.

```bash
# Transform 위치 설정
unityflow set Player.prefab \
    --path "Player/Transform/m_LocalPosition" \
    --value '{"x": 0, "y": 5, "z": 0}'

# SpriteRenderer 색상 설정
unityflow set Player.prefab \
    --path "Player/SpriteRenderer/m_Color" \
    --value '{"r": 1, "g": 0, "b": 0, "a": 1}'

# GameObject 이름 변경
unityflow set Player.prefab \
    --path "Player/name" \
    --value '"NewName"'

# 여러 컴포넌트가 있을 때 인덱스로 지정
unityflow set Scene.unity \
    --path "Canvas/Panel/Image[1]/m_Color" \
    --value '{"r": 0, "g": 1, "b": 0, "a": 1}'

# 여러 필드 한번에 수정 (batch 모드)
unityflow set Scene.unity \
    --path "Player/MonoBehaviour" \
    --batch '{"speed": 5.0, "health": 100}'
```

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
    --value "@Assets/Prefabs/Enemy.prefab"

# 여러 에셋 참조를 한번에 (batch 모드)
unityflow set Scene.unity \
    --path "Player/MonoBehaviour" \
    --batch '{
        "playerPrefab": "@Assets/Prefabs/Player.prefab",
        "enemyPrefab": "@Assets/Prefabs/Enemy.prefab",
        "spawnRate": 2.0
    }'
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

### 파일 비교 및 병합

```bash
# 두 파일 비교
unityflow diff old.prefab new.prefab

# 요약 형식으로 비교
unityflow diff old.prefab new.prefab --format summary

# 3-way 병합
unityflow merge base.prefab ours.prefab theirs.prefab -o merged.prefab
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
unityflow validate problematic.prefab --format json
```

# Unity Prefab Deterministic Serializer - 개발 문서

## 프로젝트 개요

Unity YAML 파일(프리팹, 씬, 에셋)의 결정적 직렬화를 위한 도구입니다.
Unity의 비결정적 직렬화로 인한 VCS 노이즈를 제거하여 Git diff/merge를 개선합니다.

---

## 구현된 기능

### 핵심 기능

#### 정규화 (`normalizer.py`)
Unity YAML 파일을 결정적 형식으로 정규화:
- 도큐먼트를 fileID 기준 정렬
- `m_Modifications` 배열 정렬 (target.fileID + propertyPath)
- `m_Component`, `m_Children` 배열 정렬
- 쿼터니언 정규화 (w >= 0 보장)
- Float 정규화 (선택적)

```bash
prefab-tool normalize Player.prefab
prefab-tool normalize *.prefab --parallel 4 --progress
prefab-tool normalize --changed-only --staged-only
```

#### 검증 (`validator.py`)
구조적 무결성 검사:
- 참조 유효성 검증
- 순환 참조 탐지
- 중복 fileID 탐지

```bash
prefab-tool validate Player.prefab
prefab-tool validate *.prefab --strict
```

#### 비교/병합 (`diff.py`, `merge.py`)
```bash
prefab-tool diff old.prefab new.prefab
prefab-tool merge base.prefab ours.prefab theirs.prefab -o merged.prefab
```

---

### LLM 통합

#### JSON 내보내기/가져오기 (`formats.py`)
LLM 친화적 JSON 포맷으로 변환:

```bash
# 내보내기
prefab-tool export Player.prefab -o player.json

# 가져오기 (역변환)
prefab-tool import player.json -o Player.prefab
```

출력 스키마:
```json
{
  "prefabMetadata": { "sourcePath": "...", "objectCount": 42 },
  "gameObjects": {
    "100000": { "name": "Player", "layer": 0, "components": ["400000"] }
  },
  "components": {
    "400000": { "type": "Transform", "localPosition": {"x": 0, "y": 0, "z": 0} }
  },
  "_rawFields": { ... }
}
```

#### 경로 기반 쿼리 (`query.py`)
```bash
prefab-tool query Player.prefab --path "gameObjects/*/name"
prefab-tool set Player.prefab --path "gameObjects/100000/m_Name" --value '"NewName"'
```

---

### 에셋 분석

#### 의존성 추적 (`asset_tracker.py`)
프리팹이 참조하는 외부 에셋 분석:

```bash
prefab-tool deps Player.prefab                    # 모든 의존성
prefab-tool deps Player.prefab --binary-only      # 바이너리 에셋만
prefab-tool deps Player.prefab --unresolved-only  # 누락된 에셋만
prefab-tool deps Player.prefab --type Texture     # 타입별 필터
```

#### 역참조 검색
특정 에셋을 참조하는 파일 찾기:

```bash
prefab-tool find-refs Textures/player.png
prefab-tool find-refs Textures/player.png --search-path Assets/Prefabs
```

**지원되는 바이너리 에셋 타입**

| 카테고리 | 확장자 |
|---------|--------|
| Texture | `.png`, `.jpg`, `.jpeg`, `.tga`, `.psd`, `.tiff`, `.exr`, `.hdr` |
| Model | `.fbx`, `.obj`, `.dae`, `.3ds`, `.blend`, `.max`, `.ma`, `.mb` |
| Audio | `.wav`, `.mp3`, `.ogg`, `.aiff`, `.flac`, `.m4a` |
| Video | `.mp4`, `.mov`, `.avi`, `.webm` |
| Font | `.ttf`, `.otf`, `.fon` |
| Shader | `.shader`, `.cginc`, `.hlsl`, `.glsl`, `.compute` |

---

### Git 통합

#### Textconv 드라이버
```bash
# .gitattributes
*.prefab diff=unity
*.unity diff=unity

# .gitconfig
[diff "unity"]
    textconv = prefab-tool git-textconv
```

#### Merge 드라이버
```bash
# .gitconfig
[merge "unity"]
    name = Unity YAML Merge
    driver = prefab-tool merge %O %A %B -o %A --path %P

# .gitattributes
*.prefab merge=unity
```

#### Pre-commit Hooks
```bash
# pre-commit 프레임워크 사용
prefab-tool install-hooks --pre-commit

# 네이티브 git hook 사용
prefab-tool install-hooks --git-hooks
```

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/TrueCyan/prefab-tool
    rev: v0.1.0
    hooks:
      - id: prefab-normalize
      # - id: prefab-validate
```

---

### 성능 최적화

#### 고속 파싱 (`fast_parser.py`)
rapidyaml 백엔드 사용:
- 처리량: ~3,985 KB/s (Python 순수 파서 대비 35배)

#### 대용량 파일 지원
10MB 이상 파일 스트리밍 처리:

```python
doc = UnityYAMLDocument.load_auto("LargeScene.unity")  # 자동 선택
doc = UnityYAMLDocument.load_streaming("LargeScene.unity")  # 강제 스트리밍
```

```bash
prefab-tool stats Boss.unity  # 파싱 없이 통계 조회
```

#### 병렬 처리
```bash
prefab-tool normalize *.prefab --parallel 4 --progress
```

#### 지원 파일 형식 (24개)

| 카테고리 | 확장자 |
|---------|--------|
| Core | `.prefab`, `.unity`, `.asset` |
| Animation | `.anim`, `.controller`, `.overrideController`, `.playable`, `.mask`, `.signal` |
| Rendering | `.mat`, `.renderTexture`, `.flare`, `.shadervariants`, `.spriteatlas`, `.cubemap` |
| Physics | `.physicMaterial`, `.physicsMaterial2D` |
| Terrain | `.terrainlayer`, `.brush` |
| Audio | `.mixer` |
| UI/Editor | `.guiskin`, `.fontsettings`, `.preset`, `.giparams` |

---

## CLI 명령어 요약

```bash
# 정규화
prefab-tool normalize Player.prefab
prefab-tool normalize --changed-only --staged-only
prefab-tool normalize *.prefab --parallel 4 --progress

# 검증
prefab-tool validate Player.prefab --strict

# 비교/병합
prefab-tool diff old.prefab new.prefab
prefab-tool merge base.prefab ours.prefab theirs.prefab

# 쿼리/수정
prefab-tool query Player.prefab --path "gameObjects/*/name"
prefab-tool set Player.prefab --path "..." --value "..."

# JSON 변환
prefab-tool export Player.prefab -o player.json
prefab-tool import player.json -o Player.prefab

# 에셋 분석
prefab-tool deps Player.prefab --binary-only
prefab-tool find-refs Textures/player.png

# 통계
prefab-tool stats Boss.unity

# Git 통합
prefab-tool git-textconv Player.prefab
prefab-tool install-hooks --pre-commit
```

---

## API 사용법

```python
from prefab_tool import (
    UnityYAMLDocument,
    UnityPrefabNormalizer,
    analyze_dependencies,
    find_references_to_asset,
    get_changed_files,
)

# 파싱
doc = UnityYAMLDocument.load_auto("Player.prefab")

# 정규화
normalizer = UnityPrefabNormalizer()
content = normalizer.normalize_file("Player.prefab")

# 의존성 분석
report = analyze_dependencies([Path("Player.prefab")])
for dep in report.get_binary_dependencies():
    print(f"{dep.path} [{dep.asset_type}]")

# Git 연동
changed = get_changed_files(staged_only=True)
```

---

## 파일 구조

```
prefab-tool/
├── src/prefab_tool/
│   ├── parser.py        # Unity YAML 파서
│   ├── fast_parser.py   # rapidyaml 파싱
│   ├── normalizer.py    # 정규화
│   ├── validator.py     # 검증
│   ├── diff.py          # 비교
│   ├── merge.py         # 3-way 병합
│   ├── formats.py       # JSON 변환
│   ├── query.py         # 경로 쿼리
│   ├── git_utils.py     # Git 연동
│   ├── asset_tracker.py # 에셋 추적
│   └── cli.py           # CLI
├── tests/
│   ├── fixtures/
│   └── test_*.py
└── pyproject.toml
```

---

## 향후 개선 사항

- **프로젝트 전체 통계**: `prefab-tool stats --recursive Assets/`
- **GUI 도구**: VS Code 확장, Unity Editor 통합
- **협업 기능**: 프리팹 잠금, 변경 알림

---

## 알려진 제한사항

1. **YAML 1.1 특수 케이스**: 일부 극단적인 구문이 다르게 처리될 수 있음
2. **대용량 파일**: 1GB 이상 파일은 처리 시간이 오래 걸릴 수 있음
3. **바이너리 데이터**: base64 인코딩된 바이너리는 정규화하지 않음
4. **Unity 버전**: Unity 2019+ 테스트됨

---

## 기여 가이드

```bash
git clone https://github.com/TrueCyan/prefab-tool
cd prefab-tool
pip install -e ".[dev]"
pytest tests/
```

## 라이선스

MIT License

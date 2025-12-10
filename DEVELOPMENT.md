# Unity Prefab Deterministic Serializer - 개발 현황

## 프로젝트 개요

Unity YAML 파일(프리팹, 씬, 에셋)의 결정적 직렬화를 위한 도구입니다.
Unity의 비결정적 직렬화로 인한 VCS 노이즈를 제거하여 Git diff/merge를 개선합니다.

## 구현 완료 (Phase 1-5)

### Phase 1: Python 프로토타입 ✅

**파서 (`parser.py`)**
- Unity YAML 1.1 방언 파싱 (`!u!{ClassID} &{fileID}` 태그)
- 멀티 도큐먼트 파일 지원
- `UnityYAMLDocument`, `UnityYAMLObject` 클래스

**정규화 (`normalizer.py`)**
- 도큐먼트를 fileID 기준 정렬
- `m_Modifications` 배열 정렬 (target.fileID + propertyPath)
- `m_Component`, `m_Children` 배열 정렬 (order-independent arrays)
- 쿼터니언 정규화 (w >= 0 보장)
- Float 정규화 (선택적)

**검증 (`validator.py`)**
- 구조적 무결성 검사
- 참조 유효성 검증
- 순환 참조 탐지

**비교 (`diff.py`)**
- 정규화된 상태로 비교
- 의미적 차이 분석

### Phase 2: Git 통합 ✅

**Textconv (`cli.py: git-textconv`)**
```bash
# .gitattributes
*.prefab diff=unity
*.unity diff=unity

# .gitconfig
[diff "unity"]
    textconv = prefab-tool git-textconv
```

**Merge Driver (`merge.py`)**
- diff3 스타일 3-way 병합
- 충돌 마커 생성
- 정규화 후 병합

**설치 스크립트 (`git-setup/`)**
- `install.sh`: 자동 Git 설정
- `gitattributes.example`, `gitconfig.example`

### Phase 3: LLM 친화적 포맷 ✅

**JSON 내보내기 (`formats.py`)**
```python
from prefab_tool.formats import export_to_json, PrefabJSON

prefab_json = export_to_json(doc)
json_str = prefab_json.to_json()
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

**JSON 가져오기 (역변환) (`formats.py`)** ✅
```python
from prefab_tool.formats import import_from_json, import_file_from_json

# PrefabJSON 객체에서 가져오기
doc = import_from_json(prefab_json)
doc.save("modified.prefab")

# 파일에서 직접 가져오기
doc = import_file_from_json("player.json", output_path="Player.prefab")
```

라운드트립 워크플로우:
```bash
# 1. Unity YAML → JSON 내보내기
prefab-tool export Player.prefab -o player.json

# 2. JSON 수정 (LLM 또는 스크립트)
# ... player.json 편집 ...

# 3. JSON → Unity YAML 가져오기
prefab-tool import player.json -o Player.prefab
```

**경로 기반 쿼리 (`query.py`)**
```python
from prefab_tool.query import query_path, set_value, get_value

# 쿼리
results = query_path(doc, "gameObjects/*/name")
results = query_path(doc, "components/400000/localPosition")

# 수정
set_value(doc, "gameObjects/100000/m_Name", "NewName")
```

### Phase 4: 성능 최적화 ✅

**rapidyaml 백엔드 (`fast_parser.py`)**

rapidyaml을 기본 YAML 파서로 사용하여 고성능 파싱 제공:
- **처리 시간**: ~48ms (189KB 파일 기준)
- **처리량**: ~3,985 KB/s
- Python 순수 파서 대비 **35배 빠름**

설치:
```bash
pip install prefab-tool
```

백엔드 확인:
```python
from prefab_tool.parser import get_parser_backend

print(get_parser_backend())  # "rapidyaml"
```

### Phase 5: 증분 정규화 ✅

**Git 연동 유틸리티 (`git_utils.py`)**
- Git 저장소 감지 및 루트 경로 조회
- 변경된 파일 목록 조회 (staged, unstaged, untracked)
- 특정 커밋 이후 변경된 파일 목록 조회
- Unity 파일 확장자 필터링

**배치 정규화 CLI 옵션**
```bash
# 변경된 파일만 정규화 (Git status 기반)
prefab-tool normalize --changed-only

# 스테이징된 파일만 정규화
prefab-tool normalize --changed-only --staged-only

# 특정 커밋 이후 변경된 파일 정규화
prefab-tool normalize --since HEAD~5
prefab-tool normalize --since main

# 패턴으로 필터링
prefab-tool normalize --changed-only --pattern "Assets/Prefabs/**/*.prefab"

# 드라이런 (변경 없이 대상 파일만 확인)
prefab-tool normalize --changed-only --dry-run

# 여러 파일 직접 지정
prefab-tool normalize *.prefab
```

**API 사용법**
```python
from prefab_tool import (
    get_changed_files,
    get_files_changed_since,
    is_git_repository,
    get_repo_root,
)

# 변경된 Unity 파일 목록
changed = get_changed_files()
changed = get_changed_files(staged_only=True)

# 특정 커밋 이후 변경된 파일
changed = get_files_changed_since("HEAD~5")
changed = get_files_changed_since("main")
```

### Phase 6: 확장된 파일 형식 지원 ✅

**지원되는 Unity YAML 파일 형식 (24개)**

| 카테고리 | 확장자 |
|---------|--------|
| Core | `.prefab`, `.unity`, `.asset` |
| Animation | `.anim`, `.controller`, `.overrideController`, `.playable`, `.mask`, `.signal` |
| Rendering | `.mat`, `.renderTexture`, `.flare`, `.shadervariants`, `.spriteatlas`, `.cubemap` |
| Physics | `.physicMaterial`, `.physicsMaterial2D` |
| Terrain | `.terrainlayer`, `.brush` |
| Audio | `.mixer` |
| UI/Editor | `.guiskin`, `.fontsettings`, `.preset`, `.giparams` |

**카테고리별 확장자 집합**
```python
from prefab_tool import (
    UNITY_EXTENSIONS,          # 모든 확장자
    UNITY_CORE_EXTENSIONS,     # Core
    UNITY_ANIMATION_EXTENSIONS, # Animation
    UNITY_RENDERING_EXTENSIONS, # Rendering
    UNITY_PHYSICS_EXTENSIONS,   # Physics
    UNITY_TERRAIN_EXTENSIONS,   # Terrain
    UNITY_AUDIO_EXTENSIONS,     # Audio
    UNITY_UI_EXTENSIONS,        # UI/Editor
)
```

### Phase 7: 대용량 파일 최적화 ✅

**스트리밍 파싱**

10MB 이상의 대용량 파일을 메모리 효율적으로 처리:

```python
from prefab_tool.parser import UnityYAMLDocument

# 자동 선택 (파일 크기에 따라 최적의 방법 선택)
doc = UnityYAMLDocument.load_auto("LargeScene.unity")

# 강제 스트리밍 모드
doc = UnityYAMLDocument.load_streaming("LargeScene.unity")

# 진행 상황 콜백
def on_progress(current, total):
    print(f"Progress: {current}/{total}")

doc = UnityYAMLDocument.load_auto("LargeScene.unity", progress_callback=on_progress)
```

**스트리밍 저장**

대용량 문서를 메모리 효율적으로 저장:

```python
# 일반 저장
doc.save("output.prefab")

# 스트리밍 저장 (대용량 파일에 권장)
doc.save_streaming("output.prefab")
```

**파일 통계 조회**

전체 파싱 없이 빠르게 파일 정보 확인:

```python
stats = UnityYAMLDocument.get_stats("LargeScene.unity")
print(f"Size: {stats['file_size_mb']} MB")
print(f"Documents: {stats['document_count']}")
print(f"Large file: {stats['is_large_file']}")
```

**CLI 지원**

```bash
# 파일 통계 조회
prefab-tool stats Boss.unity
prefab-tool stats *.prefab --format json

# 진행 상황 표시
prefab-tool normalize --changed-only --progress

# 병렬 처리 (4개 워커)
prefab-tool normalize *.prefab --parallel 4

# 진행 상황 + 병렬 처리
prefab-tool normalize *.prefab --parallel 4 --progress
```

### Phase 8: Pre-commit Hook 통합 ✅

**pre-commit 프레임워크 지원 (`.pre-commit-hooks.yaml`)**

커밋 전 자동 정규화를 위한 pre-commit 프레임워크 통합:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/TrueCyan/prefab-tool
    rev: v0.1.0
    hooks:
      - id: prefab-normalize        # 스테이징된 Unity 파일 정규화
      # - id: prefab-normalize-staged # 증분 정규화 (--changed-only --staged-only)
      # - id: prefab-validate         # 유효성 검증
```

**사용 가능한 Hook**
| Hook ID | 설명 |
|---------|------|
| `prefab-normalize` | 스테이징된 모든 Unity 파일 정규화 |
| `prefab-normalize-staged` | `--changed-only --staged-only` 옵션 사용 |
| `prefab-validate` | Unity 파일 구조 유효성 검증 |

**CLI를 통한 설치 (`cli.py: install-hooks`)**
```bash
# pre-commit 프레임워크 사용 (권장)
prefab-tool install-hooks --pre-commit

# 네이티브 git hook 사용 (의존성 없음)
prefab-tool install-hooks --git-hooks

# 기존 hook 덮어쓰기
prefab-tool install-hooks --git-hooks --force
```

**설치 스크립트를 통한 설정**
```bash
# git-setup/install.sh를 사용한 설정
./git-setup/install.sh pre-commit
```

**수동 설정**
```bash
# 1. pre-commit 설치
pip install pre-commit

# 2. .pre-commit-config.yaml 생성 (예제 참조)
cp git-setup/pre-commit-config.example.yaml .pre-commit-config.yaml

# 3. hook 설치
pre-commit install

# 4. 테스트
pre-commit run --all-files
```

## CLI 명령어

```bash
# 정규화
prefab-tool normalize input.prefab -o output.prefab
prefab-tool normalize input.prefab --in-place
prefab-tool normalize *.prefab --progress              # 진행 상황 표시
prefab-tool normalize *.prefab --parallel 4            # 병렬 처리
prefab-tool normalize *.prefab --parallel 4 --progress # 병렬 + 진행 상황

# 파일 통계 (대용량 파일 분석)
prefab-tool stats Boss.unity
prefab-tool stats *.prefab --format json

# 비교
prefab-tool diff file1.prefab file2.prefab

# 검증
prefab-tool validate input.prefab

# 쿼리
prefab-tool query input.prefab --path "gameObjects/*/name"

# JSON 내보내기
prefab-tool export input.prefab -o output.json

# JSON 가져오기 (역변환)
prefab-tool import input.json -o output.prefab

# 값 수정
prefab-tool set input.prefab "gameObjects/100000/m_Name" "NewName" -o output.prefab

# Git textconv
prefab-tool git-textconv input.prefab

# 3-way 병합
prefab-tool merge base.prefab ours.prefab theirs.prefab -o merged.prefab

# Pre-commit hook 설치
prefab-tool install-hooks --pre-commit    # pre-commit 프레임워크 사용
prefab-tool install-hooks --git-hooks     # 네이티브 git hook 사용
```

## 테스트

```bash
# 전체 테스트 (147개)
pytest tests/

# 커버리지
pytest tests/ --cov=prefab_tool --cov-report=html
```

## 파일 구조

```
prefab-tool/
├── src/prefab_tool/
│   ├── __init__.py
│   ├── parser.py        # Unity YAML 파서
│   ├── fast_parser.py   # rapidyaml 파싱 구현
│   ├── normalizer.py    # 정규화 로직
│   ├── validator.py     # 검증 로직
│   ├── diff.py          # 비교 로직
│   ├── merge.py         # 3-way 병합
│   ├── formats.py       # JSON 내보내기
│   ├── query.py         # 경로 기반 쿼리
│   ├── git_utils.py     # Git 연동 유틸리티
│   └── cli.py           # CLI 인터페이스
├── tests/
│   ├── fixtures/        # 테스트용 프리팹
│   └── test_*.py        # 테스트 파일들
├── git-setup/           # Git 설정 파일
└── pyproject.toml
```

---

## 향후 개선 사항

### 중간 우선순위

#### 1. 바이너리 에셋 참조 추적
프리팹이 참조하는 바이너리 에셋(텍스처, 메시 등) 추적:
```bash
prefab-tool deps Player.prefab
# 출력: Textures/player.png, Meshes/player.fbx, ...
```

#### 2. 프로젝트 전체 통계
```bash
prefab-tool stats --recursive Assets/
# 출력:
# Total files: 1,234
# Total size: 456 MB
# By type: .prefab (500), .unity (50), .asset (684)
# Largest files: Boss.unity (25MB), MainScene.unity (18MB), ...
```

### 낮은 우선순위

#### 3. GUI 도구
- VS Code 확장
- Unity Editor 통합
- 웹 기반 뷰어

#### 4. 협업 기능
- 프리팹 잠금 (Lock)
- 변경 알림
- 리뷰 도구

---

## 알려진 제한사항

1. **YAML 1.1 특수 케이스**: 일부 극단적인 YAML 1.1 구문이 다르게 처리될 수 있음 (Unity 파일에서는 거의 발생하지 않음)
2. **대용량 파일**: 10MB 이상 파일은 자동으로 스트리밍 모드 사용. 1GB 이상 파일은 처리 시간이 오래 걸릴 수 있음
3. **바이너리 데이터**: base64 인코딩된 바이너리는 정규화하지 않음
4. **Unity 버전**: Unity 2019+ 테스트됨, 이전 버전은 미확인
5. **rapidyaml 필수**: rapidyaml 라이브러리가 설치되어야 함 (기본 종속성)
6. **병렬 처리**: `--parallel` 옵션 사용 시 파일별로 별도 프로세스가 생성되므로 파일이 적을 경우 오버헤드가 발생할 수 있음

---

## 기여 가이드

```bash
# 개발 환경 설정
git clone https://github.com/TrueCyan/prefab-tool
cd prefab-tool
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 테스트 실행
pytest tests/

# 린터
ruff check src/
black src/ tests/
```

## 라이선스

MIT License

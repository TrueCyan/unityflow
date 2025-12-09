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

## CLI 명령어

```bash
# 정규화
prefab-tool normalize input.prefab -o output.prefab
prefab-tool normalize input.prefab --in-place

# 비교
prefab-tool diff file1.prefab file2.prefab

# 검증
prefab-tool validate input.prefab

# 쿼리
prefab-tool query input.prefab --path "gameObjects/*/name"

# JSON 내보내기
prefab-tool export input.prefab -o output.json

# 값 수정
prefab-tool set input.prefab "gameObjects/100000/m_Name" "NewName" -o output.prefab

# Git textconv
prefab-tool git-textconv input.prefab

# 3-way 병합
prefab-tool merge base.prefab ours.prefab theirs.prefab -o merged.prefab
```

## 테스트

```bash
# 전체 테스트 (137개)
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

### 높은 우선순위

#### 1. JSON → Unity YAML 역변환
현재 JSON 내보내기만 지원. LLM이 수정한 JSON을 다시 Unity YAML로 변환하는 기능 필요.

```python
# 목표 API
from prefab_tool.formats import import_from_json

doc = import_from_json(prefab_json)
doc.save("modified.prefab")
```

구현 시 고려사항:
- `_rawFields` 복원
- Unity 특수 타입 (Vector, Quaternion, Color) 처리
- fileID 참조 무결성 검증

#### 2. Pre-commit Hook 통합
```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: prefab-normalize
        name: Normalize Unity prefabs
        entry: prefab-tool normalize --in-place
        files: \.(prefab|unity)$
```

### 중간 우선순위

#### 3. 씬 파일 최적화
씬 파일은 프리팹보다 훨씬 크고 복잡함. 추가 최적화 필요:
- 스트리밍 파싱 (메모리 효율)
- 병렬 처리
- 청크 기반 정규화

#### 4. 바이너리 에셋 참조 추적
프리팹이 참조하는 바이너리 에셋(텍스처, 메시 등) 추적:
```bash
prefab-tool deps Player.prefab
# 출력: Textures/player.png, Meshes/player.fbx, ...
```

#### 5. 통계 및 분석
```bash
prefab-tool stats Assets/
# 출력:
# Total prefabs: 1,234
# Total GameObjects: 45,678
# Most used components: Transform (100%), SpriteRenderer (45%), ...
# Largest prefabs: Boss.prefab (2.3MB), ...
```

### 낮은 우선순위

#### 6. GUI 도구
- VS Code 확장
- Unity Editor 통합
- 웹 기반 뷰어

#### 7. 협업 기능
- 프리팹 잠금 (Lock)
- 변경 알림
- 리뷰 도구

#### 8. 추가 포맷 지원
- ScriptableObject (.asset)
- AnimationClip (.anim)
- Material (.mat)

---

## 알려진 제한사항

1. **YAML 1.1 특수 케이스**: 일부 극단적인 YAML 1.1 구문이 다르게 처리될 수 있음 (Unity 파일에서는 거의 발생하지 않음)
2. **대용량 파일**: 100MB 이상 파일은 메모리 사용량 주의
3. **바이너리 데이터**: base64 인코딩된 바이너리는 정규화하지 않음
4. **Unity 버전**: Unity 2019+ 테스트됨, 이전 버전은 미확인
5. **rapidyaml 필수**: rapidyaml 라이브러리가 설치되어야 함 (기본 종속성)

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

# prefab-tool

Unity YAML 파일(프리팹, 씬, 에셋)의 결정적 직렬화 도구입니다. Unity의 비결정적 직렬화로 인한 VCS 노이즈를 제거하여 Git diff/merge를 개선합니다.

## 주요 기능

- **정규화**: Unity YAML 파일을 결정적 형식으로 변환하여 불필요한 diff 제거
- **검증**: 참조 유효성, 순환 참조, 중복 fileID 검사
- **비교/병합**: 정규화된 diff 및 3-way 병합 지원
- **JSON 변환**: LLM 친화적 JSON 포맷으로 내보내기/가져오기
- **에셋 추적**: 의존성 분석 및 역참조 검색
- **Git 통합**: textconv, merge 드라이버, pre-commit 훅 지원

## 설치

### GitHub에서 설치

```bash
pip install git+https://github.com/TrueCyan/prefab-tool.git
```

### 소스에서 설치

```bash
git clone https://github.com/TrueCyan/prefab-tool
cd prefab-tool
pip install .
```

### 개발 환경 설치

```bash
git clone https://github.com/TrueCyan/prefab-tool
cd prefab-tool
pip install -e ".[dev]"
```

## 요구 사항

- Python 3.9 이상
- 의존성:
  - `unityparser>=4.0.0`
  - `rapidyaml>=0.10.0`
  - `click>=8.0.0`

## 빠른 시작

### 프리팹 정규화

```bash
# 단일 파일 정규화
prefab-tool normalize Player.prefab

# 여러 파일 정규화
prefab-tool normalize *.prefab

# 병렬 처리 (4 워커)
prefab-tool normalize *.prefab --parallel 4 --progress

# Git에서 변경된 파일만 정규화
prefab-tool normalize --changed-only

# 스테이징된 파일만 정규화
prefab-tool normalize --changed-only --staged-only
```

### 프리팹 검증

```bash
# 단일 파일 검증
prefab-tool validate Player.prefab

# 엄격 모드 (경고도 오류로 처리)
prefab-tool validate Player.prefab --strict
```

### 프리팹 비교

```bash
# 두 파일 비교
prefab-tool diff old.prefab new.prefab

# 정규화 없이 비교
prefab-tool diff old.prefab new.prefab --no-normalize
```

### JSON 변환 (LLM 통합)

```bash
# JSON으로 내보내기
prefab-tool export Player.prefab -o player.json

# JSON에서 가져오기
prefab-tool import player.json -o Player.prefab
```

### 에셋 의존성 분석

```bash
# 모든 의존성 표시
prefab-tool deps Player.prefab

# 바이너리 에셋만 (텍스처, 메시 등)
prefab-tool deps Player.prefab --binary-only

# 특정 에셋을 참조하는 파일 찾기
prefab-tool find-refs Textures/player.png
```

## Git 통합 설정

Unity 프로젝트 루트에서 단일 명령어로 Git 통합을 설정할 수 있습니다:

```bash
# 기본 설정 (diff/merge 드라이버 + .gitattributes)
prefab-tool setup

# pre-commit 훅도 함께 설치
prefab-tool setup --with-hooks

# 글로벌 설정 (모든 저장소에 적용)
prefab-tool setup --global
```

이 명령어는 다음을 자동으로 수행합니다:
- Git diff 드라이버 설정 (정규화된 diff 출력)
- Git merge 드라이버 설정 (Unity 파일 3-way 병합)
- `.gitattributes` 파일 생성/업데이트

### 수동 설정 (선택사항)

수동으로 설정하려면 `.gitconfig`에 추가:
```ini
[diff "unity"]
    textconv = prefab-tool git-textconv

[merge "unity"]
    name = Unity YAML Merge
    driver = prefab-tool merge %O %A %B -o %A --path %P
```

`.gitattributes`에 추가:
```
*.prefab diff=unity merge=unity text eol=lf
*.unity diff=unity merge=unity text eol=lf
*.asset diff=unity merge=unity text eol=lf
```

## Python API 사용법

```python
from prefab_tool import (
    UnityYAMLDocument,
    UnityPrefabNormalizer,
    analyze_dependencies,
    get_changed_files,
)

# 프리팹 로드
doc = UnityYAMLDocument.load("Player.prefab")

# 정규화
normalizer = UnityPrefabNormalizer()
content = normalizer.normalize_file("Player.prefab")

# 의존성 분석
from pathlib import Path
report = analyze_dependencies([Path("Player.prefab")])
for dep in report.get_binary_dependencies():
    print(f"{dep.path} [{dep.asset_type}]")

# Git 변경 파일 조회
changed = get_changed_files(staged_only=True)
```

### 프리팹 프로그래매틱 생성

```python
from prefab_tool.parser import (
    UnityYAMLDocument,
    create_game_object,
    create_transform,
    create_rect_transform,
)

# 새 문서 생성
doc = UnityYAMLDocument()

# 고유 fileID 생성
go_id = doc.generate_unique_file_id()
transform_id = doc.generate_unique_file_id()

# GameObject 생성
go = create_game_object("MyObject", file_id=go_id, components=[transform_id])

# Transform 생성
transform = create_transform(
    game_object_id=go_id,
    file_id=transform_id,
    position={"x": 0, "y": 5, "z": 0},
)

# 문서에 추가 및 저장
doc.add_object(go)
doc.add_object(transform)
doc.save("MyObject.prefab")
```

## 지원 파일 형식

| 카테고리 | 확장자 |
|---------|--------|
| Core | `.prefab`, `.unity`, `.asset` |
| Animation | `.anim`, `.controller`, `.overrideController`, `.playable`, `.mask`, `.signal` |
| Rendering | `.mat`, `.renderTexture`, `.flare`, `.shadervariants`, `.spriteatlas`, `.cubemap` |
| Physics | `.physicMaterial`, `.physicsMaterial2D` |
| Terrain | `.terrainlayer`, `.brush` |
| Audio | `.mixer` |
| UI/Editor | `.guiskin`, `.fontsettings`, `.preset`, `.giparams` |

## CLI 명령어 요약

```bash
prefab-tool setup       # Git 통합 설정 (단일 명령어)
prefab-tool normalize   # Unity YAML 파일 정규화
prefab-tool validate    # 구조적 무결성 검증
prefab-tool diff        # 두 파일 비교
prefab-tool merge       # 3-way 병합
prefab-tool query       # 경로 기반 데이터 조회
prefab-tool set         # 경로 기반 값 설정
prefab-tool export      # JSON으로 내보내기
prefab-tool import      # JSON에서 가져오기
prefab-tool deps        # 에셋 의존성 분석
prefab-tool find-refs   # 역참조 검색
prefab-tool stats       # 파일 통계 조회
```

전체 옵션은 `prefab-tool <command> --help`로 확인하세요.

## 개발

```bash
# 개발 환경 설치
pip install -e ".[dev]"

# 테스트 실행
pytest tests/

# 코드 포맷팅
black src/ tests/
ruff check src/ tests/
```

상세한 개발 문서는 [DEVELOPMENT.md](DEVELOPMENT.md)를 참조하세요.

## 라이선스

MIT License

## 기여

이슈와 풀 리퀘스트를 환영합니다. 자세한 내용은 [DEVELOPMENT.md](DEVELOPMENT.md)를 참조하세요.

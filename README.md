# unityflow

[![PyPI version](https://badge.fury.io/py/unityflow.svg)](https://pypi.org/project/unityflow/)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Unity 워크플로우 자동화 도구입니다. Unity 에디터 없이 프리팹, 씬, 에셋을 편집하고, diff/merge하고, LLM과 통합할 수 있습니다.

## 주요 기능

- **정규화**: Unity YAML 파일을 결정적 형식으로 변환하여 불필요한 diff 제거
- **검증**: 참조 유효성, 순환 참조, 중복 fileID 검사
- **비교/병합**: 정규화된 diff 및 3-way 병합 지원
- **에셋 추적**: 의존성 분석 및 역참조 검색
- **Git 통합**: textconv, merge 드라이버, pre-commit 훅 지원

## 설치

### PyPI에서 설치 (권장)

```bash
pip install unityflow
```

### GitHub에서 설치

```bash
pip install git+https://github.com/TrueCyan/unityflow.git
```

### 소스에서 설치

```bash
git clone https://github.com/TrueCyan/unityflow
cd unityflow
pip install .
```

### 개발 환경 설치

```bash
git clone https://github.com/TrueCyan/unityflow
cd unityflow
pip install -e ".[dev]"
```

## 요구 사항

- Python 3.12 이상
- 의존성:
  - `unityparser>=4.0.0`
  - `rapidyaml>=0.10.0`
  - `click>=8.0.0`

## 빠른 시작

### 파일 정규화

```bash
# 단일 파일 정규화
unityflow normalize Player.prefab
unityflow normalize MainScene.unity
unityflow normalize GameConfig.asset

# 여러 파일 정규화
unityflow normalize *.prefab *.unity *.asset

# 병렬 처리 (4 워커)
unityflow normalize Assets/**/*.prefab --parallel 4 --progress

# Git에서 변경된 파일만 정규화
unityflow normalize --changed-only

# 스테이징된 파일만 정규화
unityflow normalize --changed-only --staged-only
```

### 파일 검증

```bash
# 단일 파일 검증
unityflow validate Player.prefab
unityflow validate MainScene.unity

# 엄격 모드 (경고도 오류로 처리)
unityflow validate Player.prefab --strict
```

### 파일 비교

```bash
# 두 파일 비교
unityflow diff old.prefab new.prefab
unityflow diff Scene_v1.unity Scene_v2.unity

# 정규화 없이 비교
unityflow diff old.prefab new.prefab --no-normalize
```

### 에셋 의존성 분석

```bash
# 모든 의존성 표시
unityflow deps Player.prefab

# 바이너리 에셋만 (텍스처, 메시 등)
unityflow deps Player.prefab --binary-only

# 특정 에셋을 참조하는 파일 찾기
unityflow find-refs Textures/player.png
```

## Git 통합 설정

Unity 프로젝트 루트에서 단일 명령어로 Git 통합을 설정할 수 있습니다:

```bash
# 기본 설정 (diff/merge 드라이버 + .gitattributes)
unityflow setup

# pre-commit 훅도 함께 설치
unityflow setup --with-hooks

# 글로벌 설정 (모든 저장소에 적용)
unityflow setup --global
```

이 명령어는 다음을 자동으로 수행합니다:
- Git diff 드라이버 설정 (정규화된 diff 출력)
- Git merge 드라이버 설정 (Unity 파일 3-way 병합)
- `.gitattributes` 파일 생성/업데이트

### 수동 설정 (선택사항)

수동으로 설정하려면 `.gitconfig`에 추가:
```ini
[diff "unity"]
    textconv = unityflow git-textconv

[merge "unity"]
    name = Unity YAML Merge
    driver = unityflow merge %O %A %B -o %A --path %P
```

`.gitattributes`에 추가:
```
*.prefab diff=unity merge=unity text eol=lf
*.unity diff=unity merge=unity text eol=lf
*.asset diff=unity merge=unity text eol=lf
```

## Python API 사용법

```python
from unityflow import (
    UnityYAMLDocument,
    UnityPrefabNormalizer,
    analyze_dependencies,
    get_changed_files,
)

# Unity YAML 파일 로드 (.prefab, .unity, .asset)
doc = UnityYAMLDocument.load("Player.prefab")
doc = UnityYAMLDocument.load("MainScene.unity")
doc = UnityYAMLDocument.load("GameConfig.asset")

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

### Unity 파일 프로그래매틱 생성

```python
from unityflow.parser import (
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
doc.save("MyObject.prefab")  # 또는 .unity, .asset
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
unityflow setup        # Git 통합 설정
unityflow normalize    # Unity YAML 파일 정규화
unityflow validate     # 구조적 무결성 검증
unityflow diff         # 두 파일 비교
unityflow merge        # 3-way 병합
unityflow get          # 경로 기반 데이터 조회
unityflow set          # 경로 기반 값 설정
unityflow hierarchy    # 계층 구조 표시
unityflow inspect      # GameObject/컴포넌트 상세 조회
unityflow git-textconv # Git diff용 정규화 출력
```

전체 옵션은 `unityflow <command> --help`로 확인하세요.

## 향후 계획

- **프로젝트 전체 통계**: `unityflow stats --recursive Assets/`

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

아키텍처와 API 상세 문서는 [DEVELOPMENT.md](DEVELOPMENT.md)를 참조하세요.

## 라이선스

MIT License

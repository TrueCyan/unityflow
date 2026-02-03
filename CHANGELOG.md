# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2026-02-03

### Added

- **Unity Editor Bridge (MCP)**: Unity Editor와 실시간 통신하는 MCP 서버
  - WSL/Windows 간 HTTP 통신으로 Unity Editor에서 시각적 피드백 제공
  - Claude가 프리팹/씬의 렌더링 결과를 보고 피드백 루프 수행 가능

- **Unity C# Plugin (UPM 패키지)**: `unity-bridge/`
  - `Window > UnityFlow Bridge` EditorWindow UI
  - HTTP 서버 (기본 포트 29184)
  - 8개 API 엔드포인트:
    - `/api/ping`, `/api/editor_state` — 연결 및 에디터 상태
    - `/api/screenshot`, `/api/prefab_preview` — 스크린샷/프리팹 렌더링
    - `/api/animation_frames`, `/api/animator_state` — 애니메이션 캡처/Animator 상태
    - `/api/hierarchy`, `/api/inspector` — 런타임 hierarchy/Inspector 데이터
    - `/api/console` — 콘솔 로그

- **Python MCP Server**: `src/unityflow/bridge/`
  - FastMCP 기반 8개 tool:
    - `capture_screenshot` — Scene/Game View 스크린샷
    - `capture_prefab_preview` — 프리팹 오프스크린 렌더링
    - `capture_animation_frames` — 애니메이션 멀티프레임 캡처
    - `get_animator_state` — Animator 런타임 상태 (Play Mode)
    - `get_runtime_hierarchy` — 동적 오브젝트 포함 런타임 hierarchy
    - `get_inspector` — 컴포넌트 Inspector 데이터
    - `get_console_logs` — 콘솔 로그/에러
    - `get_editor_state` — 에디터 상태

- **`bridge` optional dependency**: `pip install unityflow[bridge]`
- **`unityflow-bridge` CLI 명령어**: MCP 서버 실행

### Installation

**Unity Package** (Package Manager → Add from git URL):
```
https://github.com/TrueCyan/unityflow.git?path=unity-bridge
```

**Python**:
```bash
pip install unityflow[bridge]
```

---

## [0.3.13] - 2026-01-30

### Added

- **`refs` CLI 명령어**: 특정 에셋을 참조하는 모든 파일을 GUID 기반으로 검색
  ```bash
  unityflow refs Assets/Scripts/Player.cs
  unityflow refs Assets/Scripts/Player.cs --format json
  unityflow refs Assets/Scripts/Player.cs --include-packages --progress
  ```
  - text/json 출력 형식 지원
  - `--include-packages`로 패키지 캐시 포함 검색
  - `--progress`로 진행률 표시

- **`unity-asset-refs` 스킬**: 에셋 참조 검색 Claude Code Plugin 스킬 추가

### Fixed

- **Windows SQLite connection leak 수정**: `CachedGUIDIndex`의 DB 연결이 WAL 모드에서 제대로 닫히지 않아 임시 파일 삭제 실패하던 문제 수정
  - `_get_db_connection`을 context manager로 변환하여 connection 자동 정리
  - 테스트에서 `LazyGUIDIndex.close()` 명시적 호출 추가

---

## [0.3.12] - 2026-01-27

### Changed

- **Claude Code Plugin으로 전환**: `init-skills` 명령어를 Claude Code Plugin으로 대체
  - [TrueCyan/claude-plugins](https://github.com/TrueCyan/claude-plugins)에서 설치 가능

- **Cross-platform Hook 지원**: Bash 스크립트를 Node.js로 마이그레이션
  - Windows/macOS/Linux 모든 플랫폼에서 동일하게 동작
  - Bash 의존성 제거

### Removed

- **`init-skills` 명령어 제거**: Claude Code Plugin으로 대체됨
- **legacy `.claude` 및 `hooks/skills` 디렉토리 제거**: Plugin 구조로 통합

### Fixed

- **dev settings 분리**: 개발용 설정과 배포용 설정 분리
- **build_guid_index import 경로 수정**: cli.py에서 올바른 import 경로 사용

---

## [0.3.11] - 2026-01-27

### Fixed

- **Windows hook 호환성 수정**: hook 명령어를 `bash -c`로 래핑하여 Windows 환경에서 정상 동작
  - SessionStart hook 스크립트 실행 시 Windows Git Bash 호환성 개선

---

## [0.3.10] - 2026-01-27

### Added

- **`set --create` 옵션**: 컴포넌트 추가 기능
  ```bash
  unityflow set Prefab.prefab --path "Canvas/Panel/Button" --create
  ```
  - 커스텀 MonoBehaviour 스크립트 지원 (프로젝트 내 .cs 파일 자동 탐색)

- **`set --remove` 옵션**: 컴포넌트 제거 기능
  ```bash
  unityflow set Prefab.prefab --path "Canvas/Panel/Button" --remove
  ```

- **내부 참조 지원 (`#` prefix)**: 같은 파일 내 오브젝트/컴포넌트 참조
  ```bash
  unityflow set Prefab.prefab --path "Root/MyScript/_target" --value "#Root/Panel/Button"
  ```

### Changed

- **`inspect` 출력 개선**: FileID/GUID 숨김, 경로로 해석하여 표시
  - Unity 내부 시스템 요소 노출 없이 CLI 사용 가능

- **스킬 문서 구조 개선**: "Lost in the Middle" 연구 기반 재배치
  - 핵심 지침을 문서 시작/끝에 배치
  - 각 문서 끝에 Summary 섹션 추가
  - fileID 등 내부 용어 참조 제거

---

## [0.3.9] - 2026-01-19

### Added

- **스킬 매니페스트 파일**: `init-skills` 실행 시 `.claude/skills/.unityflow-manifest.json` 생성
  - unityflow가 설치한 스킬 목록 추적
  - 향후 스킬 이름 변경 시 안전한 마이그레이션 지원

### Changed

- **`unity-yaml-resolve` 스킬 개선**: Git/Perforce 컨텍스트 수집을 절차적 단계로 재구성
  - Git: merge, rebase, cherry-pick 충돌 타입별 맥락 수집 지원
  - Git: octopus merge (다중 브랜치 병합) 지원
  - Perforce: 스트림 환경 자동 감지 및 다중 스트림 맥락 수집 지원

### Fixed

- **hooks 스크립트 패키지 배포**: `ensure-unityflow.sh` 스크립트가 패키지에 포함되지 않던 문제 수정

### Migration

- **스킬 이름 변경**: `resolve-conflicts` → `unity-yaml-resolve`
  - 0.3.8 이전 버전 사용자는 기존 `.claude/skills/resolve-conflicts/` 폴더를 수동으로 삭제해주세요
  - 삭제하지 않아도 동작에 문제는 없으나, 중복 스킬이 표시될 수 있습니다

---

## [0.3.8] - 2026-01-19

### Added

- **SessionStart 훅 자동 설치**: `init-skills` 명령어 실행 시 SessionStart 훅이 함께 설치되어 Claude Code 세션 시작 시 unityflow가 자동으로 설치됨
  - 가상환경 생성 및 PyPI에서 최신 버전 설치
  - `/usr/local/bin/unityflow` 심볼릭 링크 자동 생성

### Changed

- **스킬 파일 영어 번역**: 모든 스킬 파일(SKILL.md)을 영어로 번역하여 국제 사용자 지원
  - `unity-yaml-workflow`
  - `unity-ui-workflow`
  - `unity-animation-workflow`
  - `unity-yaml-resolve`

---

## [0.3.7] - 2026-01-16

### Fixed

- **Windows UTF-8 인코딩 수정**: 파일 작업 시 UTF-8 인코딩을 명시적으로 지정하여 Windows 호환성 개선

---

## [0.3.6] - 2026-01-16

### Added

- **`init-skills` 명령어**: Claude Code skills를 프로젝트에 쉽게 설치
  ```bash
  # 현재 프로젝트에 설치
  unityflow init-skills

  # 글로벌 설치 (모든 프로젝트)
  unityflow init-skills --global

  # 기존 스킬 덮어쓰기
  unityflow init-skills --force
  ```

- **`unity-yaml-resolve` skill**: AI 기반 Unity 머지 컨플릭트 해결
  - Git/Perforce VCS 지원
  - Commit/changelist 설명에서 수정 의도 분석
  - 자동 해결 가능한 변경은 자동 병합
  - 충돌 발생 시 사용자와 대화하여 결정

- **Animation 파일 지원**: `.anim`, `.controller` 파일 정규화/비교/병합 지원

### Changed

- **Semantic 모드 전용**: diff/merge가 항상 semantic 모드로 동작
  - `--semantic` 옵션 제거 (기본 동작이 됨)
  - 프로퍼티 레벨 비교로 의미 없는 변경 무시

---

## [0.3.5] - 2026-01-08

### Changed

- **Semantic Diff & Merge**:
  - `unityflow diff`: 프로퍼티 레벨 비교 (fileID 변경, 문서 순서 변경 무시)
  - `unityflow merge`: 프로퍼티 레벨 3-way merge (충돌 최소화)

---

## [0.3.4] - 2026-01-08

### Fixed

- **`HierarchyNode.children` 정렬 순서 수정**: Transform의 `m_Children` 배열 순서에 맞게 자식 노드 정렬
  - Unity Editor에서 표시되는 순서와 동일하게 children 정렬
  - 기존에는 문서 순회 순서(document traversal order)로 정렬되어 Unity Editor와 다른 순서로 표시됨
  - `_sort_children_by_transform_order()` 메서드 추가

---

## [0.3.3] - 2026-01-07

### Fixed

- **`get_property()`/`set_property()` API 일관성 개선**: PrefabInstance 노드에서 수정된 값을 올바르게 반환
  - `set_property()`로 설정한 값이 `get_property()`에서 즉시 반영됨
  - m_Modifications의 effective value를 우선 반환

- **`get_property()` Transform/RectTransform 접근 지원**: GameObject 속성 외에도 Transform 컴포넌트 속성 조회 가능
  - `node.get_property("m_LocalPosition")` 등 Transform 속성 직접 조회 가능
  - UI 프리팹의 RectTransform 속성 (m_AnchoredPosition, m_SizeDelta 등) 조회 가능

- **PrefabInstance `is_ui` 감지 수정**: stripped RectTransform을 가진 PrefabInstance 노드에서 `is_ui=True` 올바르게 감지
  - class_id 224 (RectTransform) 확인하여 UI 노드 식별

### Added

- **`ComponentInfo.modifications` 필드**: 컴포넌트에 적용된 PrefabInstance 수정 사항 저장
- **`ComponentInfo.get_effective_property()` 메서드**: modifications를 반영한 실제 속성값 조회
  ```python
  comp = node.components[0]
  # modifications가 있으면 수정된 값, 없으면 원본 값 반환
  value = comp.get_effective_property("m_LocalPosition.x")
  ```

---

## [0.3.2] - 2026-01-07

### Added

- **로컬 패키지 GUID 캐싱 지원**: `manifest.json`의 `file:` 경로로 참조된 로컬 패키지 인덱싱
  - `get_local_package_paths()` 유틸리티 함수 추가
  - `build_guid_index(include_packages=True)` 시 로컬 패키지 스캔
  - 예: `file:../../NK.Packages/com.domybest.mybox@1.7.0`

---

## [0.3.1] - 2026-01-07

### Added

- **Library/PackageCache GUID 인덱싱**: `build_guid_index(include_packages=True)` 시 Unity 레지스트리 패키지도 스캔
  - `Assets/` (기본)
  - `Packages/` (임베디드 패키지)
  - `Library/PackageCache/` (다운로드된 패키지) - **신규**

### Changed

- **CLASS_IDS를 JSON 파일로 분리**: 하드코딩된 Class ID를 외부 JSON 파일에서 로드
  - `data/class_ids.json`: Unity 공식 ClassIDReference.html에서 파싱한 **334개** Class ID
  - 기존 하드코딩 약 100개에서 3배 이상 확장
  - Unity 버전 업데이트 시 HTML에서 JSON만 재생성하면 됨
  - `importlib.resources`로 패키지 데이터 로드 (fallback 지원)

### Fixed

- **CLASS_IDS 오류 수정**: Unity 6.3 LTS 공식 문서 기준으로 잘못된 매핑 수정
  - ID 156: `TerrainCollider` → `TerrainData`
  - ID 180-208, 246-253 범위 수정
  - 신규 ID 추가: 50 (Rigidbody2D), 55 (PhysicsManager), 150 (PreloadData), 319 (AvatarMask), 320 (PlayableDirector), 328 (VideoPlayer), 329 (VideoClip), 331 (SpriteMask), 363 (OcclusionCullingData)

---

## [0.3.0] - 2026-01-07

### Breaking Changes

**CLI 명령어 대폭 간소화**: 20개의 명령어를 제거하고 10개의 핵심 명령어만 유지

- **제거된 명령어**: `query`, `export`, `import`, `difftool`, `install-hooks`, `stats`, `deps`, `find-refs`, `scan-scripts`, `scan-meta`, `parse-script`, `sprite-info`, `add-object`, `add-component`, `delete-object`, `delete-component`, `clone-object`, `generate-meta`, `modify-meta`

- **유지된 명령어**:
  - `hierarchy` - 계층 구조 조회 (신규)
  - `inspect` - 오브젝트/컴포넌트 상세 조회 (신규)
  - `get` - 값 조회, 이름 기반 경로 지원 (신규)
  - `set` - 값 수정, 이름 기반 경로 지원
  - `normalize` - YAML 정규화
  - `diff` - 파일 비교
  - `validate` - 파일 검증
  - `merge` - 3-way 병합
  - `git-textconv` - Git diff용 텍스트 변환
  - `setup` - Git 설정

### Added

- **`.meta` 파일 자동 생성**: `set` 명령어로 에셋 참조 시 `.meta` 파일이 없으면 자동 생성
  ```bash
  # Player.cs.meta가 없어도 자동 생성됨
  unityflow set Scene.unity \
      --path "Player/MonoBehaviour/m_Script" \
      --value "@Assets/Scripts/Player.cs"
  ```

- **`hierarchy` 명령어**: 프리팹/씬의 GameObject 계층 구조를 트리 형태로 출력
  ```bash
  unityflow hierarchy Player.prefab --components
  ```

- **`inspect` 명령어**: 특정 GameObject나 컴포넌트의 상세 정보 조회
  ```bash
  unityflow inspect Player.prefab "Player/Transform"
  ```

- **`get` 명령어**: 이름 기반 경로로 값 조회
  ```bash
  unityflow get Player.prefab "Player/Transform/m_LocalPosition"
  ```

- **Batch GUID Resolution**: 스크립트 GUID를 배치로 처리하여 대규모 프로젝트에서 성능 향상
  - `GUIDIndex.batch_resolve_names()`: 딕셔너리 기반 일괄 조회
  - `LazyGUIDIndex.batch_resolve_names()`: SQL IN 쿼리 활용

- **Package GUID Indexing 확장**: `manifest.json`의 `file:` 로컬 패키지도 인덱싱에 포함

### Changed

- **`set` 명령어**: 이름 기반 경로 지원 (`"Player/Transform/m_LocalPosition"`)
- **스킬 파일 업데이트**: 새로운 CLI 체계에 맞춰 `unity-yaml-workflow`, `unity-ui-workflow` 스킬 업데이트
- **CLI 코드 약 5000줄 감소**: 불필요한 코드 제거로 유지보수성 향상

### Performance

- Hierarchy 빌드 시 스크립트 이름 해석을 배치 처리로 변경 (O(N) 개별 쿼리 → O(1) 배치 쿼리)

---

## [0.2.9] - 2026-01-07

### Added

- `LazyGUIDIndex`: 대규모 프로젝트를 위한 지연 로딩 GUID 인덱스
- Nested prefab 캐싱으로 반복 로딩 성능 개선

---

## [0.2.8] - 2026-01-06

### Added

- LLM 친화적 프리팹 API 추가

---

## [0.2.7] - 2026-01-05

### Fixed

- 음수 fileID 파싱 지원

---

## [0.2.6] - 2026-01-04

### Added

- Nested prefab을 위한 고수준 Hierarchy API

---

## [0.2.5] - 2026-01-03

### Fixed

- Unity YAML 파서에서 비-딕셔너리 루트 노드 처리

---

## [0.2.0] - Initial Release

### Added

- Unity YAML 파일 파싱 및 직렬화
- 프리팹, 씬, 에셋 파일 지원
- GUID 인덱싱 및 에셋 추적
- Git 통합 (normalize, diff, merge)
- CLI 도구

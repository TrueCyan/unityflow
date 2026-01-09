# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

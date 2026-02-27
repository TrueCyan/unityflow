# unityflow 개발 문서

## 아키텍처

```
unityflow/
├── src/unityflow/
│   ├── parser.py         # Unity YAML 파서, 프리팹 생성 API
│   ├── fast_parser.py    # rapidyaml 기반 고속 파싱
│   ├── normalizer.py     # 결정적 정규화 (상속 체인 해석 포함)
│   ├── validator.py      # 구조적 무결성 검증
│   ├── semantic_diff.py  # 프로퍼티 레벨 비교
│   ├── merge.py          # 3-way 병합
│   ├── hierarchy.py      # GameObject 계층 구조 빌드
│   ├── query.py          # 경로 기반 쿼리
│   ├── script_parser.py  # C# 스크립트 필드 파싱
│   ├── dll_inspector.py  # .NET DLL 메타데이터 파싱, Unity fileID 계산
│   ├── asset_resolver.py # 에셋/내부 참조 해석 (@, #)
│   ├── asset_tracker.py  # GUID 인덱스, 에셋 의존성 추적
│   ├── formats.py        # RectTransform 변환
│   ├── git_utils.py      # Git 연동
│   ├── cli.py            # CLI 엔트리포인트
│   └── bridge/           # Unity Editor MCP 서버
├── tests/
│   ├── fixtures/         # 테스트용 Unity 파일
│   └── test_*.py
└── pyproject.toml
```

---

## 상세 API

### 프리팹 프로그래매틱 생성

```python
from unityflow.parser import (
    UnityYAMLDocument,
    create_game_object,
    create_transform,
    create_rect_transform,
    create_mono_behaviour,
    generate_file_id,
)

# 새 문서 생성
doc = UnityYAMLDocument()

# fileID 자동 생성
go_id = doc.generate_unique_file_id()
rt_id = doc.generate_unique_file_id()
mb_id = doc.generate_unique_file_id()

# GameObject 생성
go = create_game_object("UIPanel", file_id=go_id, components=[rt_id, mb_id])

# RectTransform 생성
rt = create_rect_transform(
    go_id,
    file_id=rt_id,
    anchor_min={"x": 0, "y": 0},
    anchor_max={"x": 1, "y": 1},
)

# MonoBehaviour 생성 (커스텀 스크립트)
mb = create_mono_behaviour(
    go_id,
    script_guid="abcd1234",
    file_id=mb_id,
    properties={"speed": 10},
)

doc.add_object(go)
doc.add_object(rt)
doc.add_object(mb)
doc.save("UIPanel.prefab")
```

**생성 함수:**
- `create_game_object(name, layer, tag, components, ...)`
- `create_transform(game_object_id, position, rotation, scale, parent_id, ...)`
- `create_rect_transform(game_object_id, anchor_min, anchor_max, pivot, ...)`
- `create_mono_behaviour(game_object_id, script_guid, properties, ...)`
- `generate_file_id(existing_ids)` - 고유 fileID 생성

### RectTransform 에디터 값 변환

UI RectTransform은 Unity 에디터와 파일 형식이 다릅니다:

```python
from unityflow.formats import (
    RectTransformEditorValues,
    editor_to_file_values,
    file_to_editor_values,
    create_rect_transform_file_values,
)

# 에디터 값 → 파일 값 변환
editor_vals = RectTransformEditorValues(
    anchor_min_x=0, anchor_min_y=0,
    anchor_max_x=1, anchor_max_y=1,
    left=10, right=10, top=10, bottom=10,
)
file_vals = editor_to_file_values(editor_vals)
# → anchored_position, size_delta 등

# 앵커 프리셋으로 간편 생성
file_vals = create_rect_transform_file_values(
    anchor_preset="stretch-all",
    left=20, right=20, top=10, bottom=10,
)
```

### 성능 옵션

```python
# 대용량 파일 스트리밍 처리 (10MB+)
doc = UnityYAMLDocument.load_streaming("LargeScene.unity")

# 자동 선택 (파일 크기 기반)
doc = UnityYAMLDocument.load_auto("Scene.unity")
```

rapidyaml 백엔드 처리량: ~3,985 KB/s

---

## 알려진 제한사항

1. **YAML 1.1**: 일부 극단적인 구문이 다르게 처리될 수 있음
2. **대용량 파일**: 1GB 이상 파일은 처리 시간이 오래 걸림
3. **바이너리 데이터**: base64 인코딩된 바이너리는 정규화하지 않음
4. **Unity 버전**: Unity 2019+ 테스트됨

---

## 기여 가이드

```bash
# 개발 환경
git clone https://github.com/TrueCyan/unityflow
cd unityflow
pip install -e ".[dev]"

# 테스트
pytest tests/

# 린트
black src/ tests/
ruff check src/ tests/
```

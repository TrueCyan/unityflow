# prefab-tool 개발 문서

## 아키텍처

```
prefab-tool/
├── src/prefab_tool/
│   ├── parser.py        # Unity YAML 파서, 프리팹 생성 API
│   ├── fast_parser.py   # rapidyaml 기반 고속 파싱
│   ├── normalizer.py    # 결정적 정규화
│   ├── validator.py     # 구조적 무결성 검증
│   ├── diff.py          # 비교
│   ├── merge.py         # 3-way 병합
│   ├── formats.py       # JSON 변환, RectTransform 변환
│   ├── query.py         # 경로 기반 쿼리
│   ├── git_utils.py     # Git 연동
│   ├── asset_tracker.py # 에셋 의존성 추적
│   └── cli.py           # CLI 엔트리포인트
├── tests/
│   ├── fixtures/        # 테스트용 Unity 파일
│   └── test_*.py
└── pyproject.toml
```

---

## 상세 API

### 프리팹 프로그래매틱 생성

```python
from prefab_tool.parser import (
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
from prefab_tool.formats import (
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

### JSON 스키마

`prefab-tool export` 출력 형식:

```json
{
  "metadata": {
    "sourcePath": "Player.prefab",
    "objectCount": 42
  },
  "gameObjects": {
    "100000": {
      "name": "Player",
      "layer": 0,
      "components": ["400000"]
    }
  },
  "components": {
    "400000": {
      "type": "Transform",
      "localPosition": {"x": 0, "y": 0, "z": 0}
    }
  },
  "_rawFields": { }
}
```

RectTransform 컴포넌트는 `editorValues` 필드도 포함:

```json
{
  "type": "RectTransform",
  "rectTransform": {
    "anchorMin": {"x": 0, "y": 0},
    "anchorMax": {"x": 1, "y": 1},
    "anchoredPosition": {"x": 0, "y": 0},
    "sizeDelta": {"x": -20, "y": -20}
  },
  "editorValues": {
    "left": 10, "right": 10, "top": 10, "bottom": 10
  }
}
```

Import 시 `editorValues`로 직관적 설정 가능.

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
git clone https://github.com/TrueCyan/prefab-tool
cd prefab-tool
pip install -e ".[dev]"

# 테스트
pytest tests/

# 린트
black src/ tests/
ruff check src/ tests/
```

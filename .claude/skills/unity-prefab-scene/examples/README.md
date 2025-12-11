# 예시 스크립트

이 디렉토리에는 prefab-tool을 사용한 프리팹/씬 편집 예시 스크립트들이 있습니다.

## 스크립트 목록

### 1. create_ui_panel.py

새로운 UI Panel 프리팹을 생성합니다.

```bash
# 기본 출력 (UIPanel.prefab)
python create_ui_panel.py

# 커스텀 출력 경로
python create_ui_panel.py MyPanel.prefab
```

생성되는 구조:
```
Panel (root)
├── Title
├── CloseButton
└── Content
```

### 2. modify_via_json.py

JSON 변환을 통해 프리팹을 수정합니다.

```bash
# 기본 수정 (이름 변경, 스케일 2배)
python modify_via_json.py modify Player.prefab

# 일괄 이름 변경
python modify_via_json.py rename Player.prefab "old_" "new_"

# 모든 GameObject 활성화/비활성화
python modify_via_json.py toggle Player.prefab off
python modify_via_json.py toggle Player.prefab on
```

### 3. analyze_prefab.py

프리팹/씬 파일을 분석합니다.

```bash
# 텍스트 형식 분석
python analyze_prefab.py Player.prefab

# JSON 형식 출력
python analyze_prefab.py Player.prefab --json

# 두 프리팹 비교
python analyze_prefab.py compare old.prefab new.prefab

# 이름으로 검색
python analyze_prefab.py find Player.prefab "Button"
```

## CLI 명령어 빠른 참조

```bash
# 파일 분석
prefab-tool stats Player.prefab
prefab-tool query Player.prefab
prefab-tool validate Player.prefab

# JSON 변환
prefab-tool export Player.prefab -o player.json
prefab-tool import player.json -o Player.prefab

# 값 수정
prefab-tool set Player.prefab --path "gameObjects/*/name" --value '"NewName"'

# 정규화
prefab-tool normalize Player.prefab

# 의존성
prefab-tool deps Player.prefab
prefab-tool find-refs Textures/icon.png
```

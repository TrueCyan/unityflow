---
name: unity-prefab-scene
description: Unity 프리팹(.prefab), 씬(.unity), ScriptableObject(.asset) 파일을 편집합니다. prefab-tool을 사용하여 프리팹 분석, JSON 변환, GameObject 생성/수정/삭제/복제, UI 레이아웃 조정, 컴포넌트 추가/삭제, 스프라이트 연결, ScriptableObject 편집 등의 작업을 수행합니다.
---

# Unity Prefab/Scene/ScriptableObject 편집 스킬

## ⚠️ 필수: prefab-tool만 사용

Unity YAML 파일을 직접 편집하지 마세요. 모든 조작은 `prefab-tool` CLI로 수행합니다.

---

## 핵심 명령어

### 조회
```bash
prefab-tool stats Player.prefab
prefab-tool query Player.prefab --path "gameObjects/*/name"
prefab-tool query Scene.unity --find-name "Player*"
prefab-tool query Scene.unity --find-component "SpriteRenderer"
```

### 값 수정
```bash
# 단일 값
prefab-tool set File.prefab --path "components/12345/localPosition" --value '{"x": 0, "y": 5, "z": 0}'

# 여러 필드 (batch)
prefab-tool set File.prefab --path "components/12345" --batch '{"field1": 1, "field2": 2}' --create

# 스프라이트 (fileID 자동 감지)
prefab-tool set File.prefab --path "components/12345/m_Sprite" --sprite "Assets/Sprites/player.png"
prefab-tool set File.prefab --path "components/12345/m_Sprite" --sprite "Assets/Sprites/atlas.png" --sub-sprite "idle_0"
```

### GameObject 조작
```bash
prefab-tool add-object Scene.unity --name "Player"
prefab-tool add-object Scene.unity --name "Child" --parent 12345
prefab-tool add-object Scene.unity --name "Button" --ui --parent 67890  # RectTransform
prefab-tool clone-object Scene.unity --id 12345 --deep
prefab-tool delete-object Scene.unity --id 12345 --cascade
```

### 컴포넌트 조작
```bash
prefab-tool add-component Scene.unity --to 12345 --type SpriteRenderer
prefab-tool add-component Scene.unity --to 12345 --script "abc123..." --props '{"speed": 5.0}'
prefab-tool delete-component Scene.unity --id 67890
```

### JSON 변환 (복잡한 편집용)
```bash
prefab-tool export Player.prefab -o player.json
# JSON 편집 후
prefab-tool import player.json -o Player.prefab
```

### GUID 조회
```bash
prefab-tool scan-scripts Scene.unity --show-properties
prefab-tool scan-meta "Library/PackageCache/com.unity.ugui@*" -r --filter Button
```

### 검증/정규화
```bash
prefab-tool validate Player.prefab
prefab-tool normalize Player.prefab
```

---

## Unity UI 설계 규칙

### 1. Canvas에는 GraphicRaycaster 필수
UI 클릭이 작동하려면 Canvas에 반드시 GraphicRaycaster를 추가해야 합니다.

### 2. 한 오브젝트 = 하나의 LayoutGroup
같은 오브젝트에 VerticalLayoutGroup + HorizontalLayoutGroup 동시 사용 금지. 레이아웃 충돌 발생.

### 3. 기능 단위 그룹화
UI 요소를 기능별로 묶어서 구성합니다. 배치 방향에 따라 적절한 LayoutGroup 사용:
- 세로 배치: VerticalLayoutGroup
- 가로 배치: HorizontalLayoutGroup
- 격자 배치: GridLayoutGroup

```
Panel (VLG)
├── TitleText
├── ControlGroup (HLG)  ← 가로로 배치할 요소들
│   ├── MinusBtn
│   ├── ValueText
│   └── PlusBtn
└── ToggleBtn
```

### 4. ContentSizeFitter 주의
부모와 자식 모두에 ContentSizeFitter 사용 시 순환 의존성 발생. 최상위 컨테이너에만 사용.

### 5. EventSystem 필수
씬에 EventSystem이 있어야 UI 입력이 작동합니다.

### 6. Mask + Image 알파값
Mask 사용 시 Image 알파가 0이면 마스킹 안 됨. `m_Color.a: 1` 설정 후 `m_ShowMaskGraphic: 0`으로 숨기기.

---

## 참조 테이블

### 에셋 fileID
| 에셋 타입 | fileID | type |
|----------|--------|------|
| AudioClip | `8300000` | 3 |
| ScriptableObject | `11400000` | 2 |
| Texture2D | `2800000` | 3 |
| Sprite (Single) | `21300000` | 3 |
| Material | `2100000` | 2 |

### Unity Class ID
| ID | 클래스 |
|----|--------|
| 1 | GameObject |
| 4 | Transform |
| 114 | MonoBehaviour |
| 212 | SpriteRenderer |
| 223 | Canvas |
| 224 | RectTransform |
| 225 | CanvasGroup |

### UI 컴포넌트 GUID (com.unity.ugui)
| 컴포넌트 | GUID |
|----------|------|
| Image | `fe87c0e1cc204ed48ad3b37840f39efc` |
| Button | `4e29b1a8efbd4b44bb3f3716e73f07ff` |
| GraphicRaycaster | `dc42784cf147c0c48a680349fa168899` |
| CanvasScaler | `0cd44c1031e13a943bb63640046fad76` |
| VerticalLayoutGroup | `59f8146938fff824cb5fd77236b75775` |
| HorizontalLayoutGroup | `30649d3a9faa99c48a7b1166b86bf2a0` |
| ContentSizeFitter | `3245ec927659c4140ac4f8d17403cc18` |
| TextMeshProUGUI | `f4688fdb7df04437aeb418b961361dc5` |
| EventSystem | `76c392e42b5098c458856cdf6ecaaaa1` |

---

## 주의사항

1. 편집 전 백업 또는 `-o` 옵션으로 새 파일에 저장
2. 편집 후 `prefab-tool normalize`로 Git 노이즈 방지
3. classId는 절대 임의로 사용하지 않음 (SceneRoots 1660057539 특히 주의)

---
name: resolve-conflicts
description: Unity YAML 파일의 머지 컨플릭트를 해결합니다. Git/Perforce 로그를 분석하여 수정 맥락을 파악하고, 자동 해결이 가능한 부분은 해결하고, 겹치는 부분은 사용자와 대화하여 결정합니다.
---

## ⚠️ 필수: unityflow CLI 사용

이 skill의 모든 `unityflow` 명령어는 가상환경에 설치된 CLI를 사용합니다.

**명령어 실행 방법** (PATH에 없을 경우):
```bash
~/.unityflow-venv/bin/unityflow <command>
```

SessionStart hook이 자동으로 설치하므로, 일반적으로 `unityflow` 명령어가 바로 작동합니다.

---

# Unity Merge Conflict Resolution Skill

Unity 파일(.prefab, .unity, .asset)의 머지 컨플릭트를 **지능적으로** 해결하는 skill입니다.

---

## 이 Skill의 목적

1. **VCS 컨텍스트 분석**: Git commit 또는 Perforce changelist 설명에서 수정 의도 파악
2. **Semantic 3-way Merge**: 텍스트가 아닌 property 레벨에서 정교한 병합
3. **자동 해결**: 겹치지 않는 변경은 자동으로 병합
4. **대화형 해결**: 겹치는 부분은 사용자와 함께 결정

---

## 워크플로우

### 1단계: 컨플릭트 파일 확인

```bash
# Git의 경우
git status --porcelain | grep "^UU"
git diff --name-only --diff-filter=U

# Perforce의 경우
p4 resolve -n
```

### 2단계: 수정 맥락 분석

**Git:**
```bash
# 우리 브랜치의 변경 내용
git log --oneline HEAD~5..HEAD -- <파일경로>
git show HEAD:<파일경로> > /tmp/ours.yaml

# 상대 브랜치의 변경 내용
git log --oneline MERGE_HEAD~5..MERGE_HEAD -- <파일경로>
git show MERGE_HEAD:<파일경로> > /tmp/theirs.yaml

# 공통 조상
git show $(git merge-base HEAD MERGE_HEAD):<파일경로> > /tmp/base.yaml
```

**Perforce:**
```bash
# changelist 설명 확인
p4 changes -l -m 5 <파일경로>

# 파일 히스토리
p4 filelog -m 10 <파일경로>

# changelist 상세 정보
p4 describe -s <changelist번호>
```

### 3단계: Semantic Merge 수행

```bash
# 3-way semantic merge
unityflow merge /tmp/base.yaml /tmp/ours.yaml /tmp/theirs.yaml -o merged.yaml

# 또는 자동 해결 시도
unityflow resolve --dry-run  # 먼저 미리보기
unityflow resolve            # 실제 해결
```

### 4단계: 컨플릭트 분석 및 사용자 질문

merge 결과에 컨플릭트가 있으면:

1. **컨플릭트 내용 표시**
   ```
   [Conflict 1] Player/Transform
     Property: m_LocalPosition.x
     Base:   0
     Ours:   10 (commit abc123: "플레이어 시작 위치 수정")
     Theirs: 5  (commit def456: "레벨 디자인 조정")
   ```

2. **맥락 기반 제안**
   - commit/changelist 설명에서 의도 파악
   - 어떤 쪽이 더 의도적인 변경인지 분석
   - 제안과 이유 설명

3. **사용자에게 질문**
   ```
   이 충돌에 대해:
   - (o) ours: 10 사용 - "플레이어 시작 위치 수정"
   - (t) theirs: 5 사용 - "레벨 디자인 조정"
   - (b) base: 0 사용 - 원래 값 유지

   어떤 값을 선택하시겠습니까?
   ```

### 5단계: 결과 적용

```bash
# 해결된 파일 저장
unityflow normalize merged.yaml  # 정규화

# Git: 해결 완료 표시
git add <파일경로>

# Perforce: 해결 완료 표시
p4 resolve -ae <파일경로>
```

---

## AI 분석 가이드라인

### Commit/Changelist 설명에서 힌트 찾기

| 키워드 | 의미 | 우선순위 |
|--------|------|----------|
| fix, bug, crash | 버그 수정 | 높음 |
| position, layout, align | 레이아웃 변경 | 맥락 확인 필요 |
| add, new, implement | 새 기능 | 보통 |
| refactor, cleanup | 리팩토링 | 낮음 |
| revert | 되돌리기 | 맥락 확인 필요 |

### 자동 해결 가능한 경우

1. **서로 다른 오브젝트 수정**: 한쪽은 Player, 다른쪽은 Enemy 수정
2. **서로 다른 컴포넌트 수정**: 한쪽은 Transform, 다른쪽은 SpriteRenderer
3. **서로 다른 속성 수정**: 한쪽은 position, 다른쪽은 color

### 사용자 확인이 필요한 경우

1. **같은 속성을 다르게 수정**: 둘 다 position.x를 수정
2. **한쪽이 삭제, 다른쪽이 수정**: 오브젝트 삭제 vs 속성 변경
3. **의미적 충돌**: sorting order가 둘 다 증가

---

## 사용 예시

### 사용자 요청 예시

```
Player.prefab에 머지 컨플릭트가 있어. 해결해줘.
```

### AI 응답 예시

```
Player.prefab의 컨플릭트를 분석하겠습니다.

[컨텍스트 분석]
- 우리 브랜치 (abc123): "플레이어 이동 속도 조정"
- 상대 브랜치 (def456): "레벨 밸런싱"

[자동 해결됨]
✅ Player/Rigidbody2D/m_Mass: 1.5 (theirs) - 겹치지 않는 변경
✅ Player/SpriteRenderer/m_Color: rgba(1,1,1,1) (ours) - 겹치지 않는 변경

[충돌 발생]
❌ Player/MonoBehaviour/moveSpeed
   - Base: 5.0
   - Ours: 7.0 ("플레이어 이동 속도 조정")
   - Theirs: 4.0 ("레벨 밸런싱")

이 속성은 두 브랜치 모두에서 의도적으로 수정되었습니다.
"플레이어 이동 속도 조정"이 더 구체적인 변경 같습니다.

어떤 값을 사용하시겠습니까?
1. 7.0 (ours) - 속도 증가
2. 4.0 (theirs) - 속도 감소
3. 5.0 (base) - 원래 값 유지
4. 다른 값 직접 입력
```

---

## 주의사항

1. **항상 백업**: 머지 전 원본 파일 백업 권장
2. **unityflow 사용**: Unity YAML은 반드시 unityflow로 처리
3. **검증**: 머지 후 `unityflow validate`로 무결성 확인
4. **테스트**: Unity에서 실제 동작 확인 권장

---

## 관련 명령어

```bash
# 컨플릭트 미리보기
unityflow resolve --dry-run

# 자동 해결만 (대화 없이)
unityflow resolve --accept ours
unityflow resolve --accept theirs

# 특정 파일만 해결
unityflow resolve-file base.yaml ours.yaml theirs.yaml -o result.yaml

# diff 확인
unityflow diff old.prefab new.prefab

# 결과 검증
unityflow validate merged.prefab
```

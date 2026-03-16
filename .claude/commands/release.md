---
description: "버전 업데이트, 커밋, 푸시, GitHub 릴리즈 생성"
---

릴리즈를 진행합니다. 아래 단계를 순서대로 실행하세요.

## 1. 기존 변경사항 커밋

`git status`로 커밋되지 않은 변경이 있는지 확인합니다.
변경이 있으면 버전 범프와 별도로 먼저 커밋합니다 (내용에 맞는 커밋 메시지 사용).

## 2. 버전 확인

현재 버전을 확인합니다:
- `pyproject.toml`의 `version`
- `.claude-plugin/plugin.json`의 `version`

사용자에게 새 버전 번호를 확인합니다. 인자로 `$ARGUMENTS`가 주어졌다면 해당 버전을 사용합니다.

## 3. 버전 업데이트

두 파일의 버전을 동시에 업데이트합니다:
- `pyproject.toml` → `version = "새버전"`
- `.claude-plugin/plugin.json` → `"version": "새버전"`

## 4. 검증

```bash
.venv/bin/ruff check src/ tests/
.venv/bin/black --check src/ tests/
PYTHONPATH=src .venv/bin/pytest tests/ -v
```

하나라도 실패하면 중단하고 수정합니다.

## 5. 커밋 & 푸시 & 릴리즈

`git log` 로 이전 릴리즈 태그 이후의 커밋을 확인하고, 변경 내용을 요약하여 릴리즈 노트를 작성합니다.
릴리즈 노트는 `## What's New` 섹션 아래에 주요 변경사항을 한국어로 작성합니다.

버전 범프 커밋, 푸시, 릴리즈 생성을 **하나의 bash 명령으로** 실행합니다:

```bash
git add pyproject.toml .claude-plugin/plugin.json uv.lock && \
git commit -m "chore: bump version to v{새버전}" && \
git push && \
gh release create v{새버전} --title "v{새버전}" --notes "{릴리즈 노트}"
```

# Claude Code Instructions for unityflow

## Environment Setup

작업 시작 전 반드시 환경을 세팅합니다:

```bash
# 의존성 설치
pip install rapidyaml pytest click

# 테스트 실행 (PYTHONPATH 설정 필수)
PYTHONPATH=src python -m pytest tests/ -v
```

### 주의사항

- Python 3.12+ 권장이지만, Python 3.11에서도 PYTHONPATH 설정으로 동작
- `pip install -e .`는 Python 버전 제약으로 실패할 수 있음 → PYTHONPATH 방식 사용

## Before Completing Any Task

Always run these checks before committing:

```bash
# 1. Lint check
ruff check src/ tests/

# 2. Format check
black --check src/ tests/

# 3. Run tests
pytest tests/ -v
```

If any check fails, fix the issues before committing.

## Quick Fix Commands

```bash
# Auto-fix lint issues
ruff check src/ tests/ --fix

# Auto-format code
black src/ tests/
```

## Project Structure

- `src/unityflow/` - Main package source
- `tests/` - Test files
- Python 3.12+ required

## Code Style

- Line length: 120 characters
- Formatter: black
- Linter: ruff (E, F, W, I, N, UP, B, C4 rules)

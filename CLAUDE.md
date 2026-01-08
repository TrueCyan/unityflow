# Claude Code Instructions for unityflow

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

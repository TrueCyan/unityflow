# Claude Code Instructions for unityflow

## Environment Setup

작업 시작 전 반드시 환경을 세팅합니다:

```bash
# 의존성 설치 (dev + bridge, pyproject.toml의 버전 제약 포함)
pip install -e ".[all]"

# 테스트 실행
pytest tests/
```

### 주의사항

- Python 3.12 이상 필요 (pyproject.toml `requires-python` 기준)
- 의존성 버전은 pyproject.toml을 따름 (rapidyaml은 `>=0.10.0,<0.12`로 핀 — 0.12부터 Unity 멀티라인 스칼라 로딩이 깨짐)
- pytest는 pyproject.toml의 `pythonpath = ["src"]` 설정으로 소스를 찾으므로 별도 PYTHONPATH 설정 없이 동작
- tests/test_bridge.py는 `mcp` 패키지를 요구하므로 `[all]` extra로 설치해야 전체 테스트가 통과

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

### Design Principles

#### Structure
- Separate concepts into trustworthy units whose internals can be ignored
- Minimize state: reduce count, lifetime, and scope
- Lower modules must not know upper context; pass only what's needed (use a config class if there's too much to pass)

#### Constraints
- Make invalid operations impossible (enforce at compile time via types and access modifiers)
- Don't write defensive code for impossible states; if a state can't exist, the code path shouldn't exist

#### Clarity
- Explicit over implicit; avoid hidden behaviors
- Minimize side effects; when unavoidable, make them obvious
- Names must fully describe the role (include all important details even if long; omit what's obvious from context)

#### Consistency
- Same word means same thing; new terms require team agreement
- Same problem, same solution pattern

#### Code Organization
- Check for existing utilities before creating new ones
- Keep utilities in a common location
- Place related code close together
- Extract domain-independent reusable logic into utilities

#### Error Handling
- Errors must clearly indicate where and why they occurred
- Prefer switch or pattern matching over if-else chains; all cases should be visible together

#### Change Management
- Make only the minimum changes needed to achieve the goal
- Propagate structural improvements immediately before bad patterns spread
- Consolidate business logic that changes for the same reason
- Duplication of simple utilities or stable infrastructure is acceptable

#### Performance
- Wrap performance-optimized code that sacrifices readability, so callers can use it cleanly
- Minimize the boundary between performance-critical and normal code
- Be careful with logic called from Update/LateUpdate/FixedUpdate (per-frame hot paths)
- Optimize based on profiling; verify effectiveness on the current version

#### No Comments Policy

Do not add comments to code. Code should be self-explanatory.

- Use clear variable and function names instead of comments
- Extract complex logic into functions with descriptive names
- If you feel a comment is needed, refactor the code to clarify intent
- Remove existing comments when modifying code

## Pull Request Guidelines

PR 제목과 설명은 해당 브랜치에서 실제로 작업한 내용만 포함합니다.

- `git log origin/main..HEAD`로 이 브랜치의 커밋 확인
- Summary는 이 브랜치의 커밋 내용만 간결하게 나열

## Documentation Style

Write documentation in positive, context-independent form.

- Describe what the current implementation does
- State actions directly (e.g., "Use X" rather than "Don't use Y")
- Readers should understand without knowing the change history

## Communication

When the user provides a new perspective or points out something not considered, acknowledge learning directly:
- "I hadn't considered that"
- "That changes my understanding"
- State what changed in your thinking

## Cost Estimation

AI assistance changes the cost structure of software work. When estimating effort:
- Large-scale code modifications: low cost (AI writes quickly)
- Pattern consistency across many files: low cost (AI maintains accuracy)
- Test generation: low cost (AI writes alongside changes)

Verification becomes the bottleneck. Decompose it:
- Compilation: automated
- Existing tests: automated
- Design intent validation: sampling review or AI-assisted review
- Runtime behavior: existing QA process
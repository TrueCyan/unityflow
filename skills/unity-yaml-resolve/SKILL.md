---
name: unity-yaml-resolve
description: Resolves merge conflicts in Unity YAML files. Analyzes Git/Perforce logs to understand modification context, automatically resolves non-overlapping changes, and interactively resolves overlapping conflicts with user input.
---

# Unity Merge Conflict Resolution Skill

Resolve merge conflicts in Unity files (.prefab, .unity, .asset) using VCS context analysis and semantic 3-way merge.

## Resolution Guidelines

### Auto-Resolvable Cases

1. **Different objects modified**: One side modifies Player, other modifies Enemy
2. **Different components modified**: One side modifies Transform, other modifies SpriteRenderer
3. **Different properties modified**: One side modifies position, other modifies color

### Cases Requiring User Confirmation

1. **Same property modified differently**: Both modified position.x
2. **One deleted, other modified**: Object deletion vs property change
3. **Semantic conflict**: Both increased sorting order

### Commit Message Hints

| Keyword | Meaning | Priority |
|---------|---------|----------|
| fix, bug, crash | Bug fix | High |
| position, layout, align | Layout change | Context check needed |
| add, new, implement | New feature | Medium |
| refactor, cleanup | Refactoring | Low |
| revert | Rollback | Context check needed |

---

## Workflow

### Step 1: Identify Conflict Files

```bash
# For Git
git status --porcelain | grep "^UU"
git diff --name-only --diff-filter=U

# For Perforce
p4 resolve -n
```

### Step 2: Analyze Modification Context

**Git:**

Follow this procedure in order:

**Step 2-1: Identify conflict type**
```bash
# Check which operation caused the conflict
if [ -f .git/MERGE_HEAD ]; then
    echo "MERGE conflict"
elif [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then
    echo "REBASE conflict"
elif [ -f .git/CHERRY_PICK_HEAD ]; then
    echo "CHERRY-PICK conflict"
else
    echo "Unknown conflict type"
fi

# For octopus merge, check if multiple MERGE_HEADs exist
cat .git/MERGE_HEAD 2>/dev/null | wc -l
```

**Step 2-2: Get file history and branch context**
```bash
# Current branch history
git log --oneline -10 -- <filepath>

# Find which branches touched this file recently
git log --oneline --all -20 -- <filepath>

# Show commit details with full message
git log -1 --format=full <commit_hash>
```

**Step 2-3: Gather context based on conflict type**

*For MERGE conflicts:*
```bash
# Our branch changes
git log --oneline HEAD~5..HEAD -- <filepath>

# Their branch changes (single merge)
git log --oneline MERGE_HEAD~5..MERGE_HEAD -- <filepath>

# For octopus merge (multiple branches), iterate:
for head in $(cat .git/MERGE_HEAD); do
    echo "=== Branch: $head ==="
    git log --oneline $head~5..$head -- <filepath>
done
```

*For REBASE conflicts:*
```bash
# Original branch being rebased
git log --oneline REBASE_HEAD~5..REBASE_HEAD -- <filepath>

# Target branch (onto)
git log --oneline HEAD~5..HEAD -- <filepath>

# Current commit being applied
cat .git/rebase-merge/current-commit 2>/dev/null || cat .git/rebase-apply/original-commit
```

*For CHERRY-PICK conflicts:*
```bash
# The commit being cherry-picked
git log -1 CHERRY_PICK_HEAD -- <filepath>
git show CHERRY_PICK_HEAD --stat

# Current branch context
git log --oneline HEAD~5..HEAD -- <filepath>
```

**Step 2-4: Extract file versions for 3-way merge**
```bash
# Base version (common ancestor)
# For merge:
git show $(git merge-base HEAD MERGE_HEAD):<filepath> > /tmp/base.yaml
# For rebase/cherry-pick:
git show $(git merge-base HEAD REBASE_HEAD 2>/dev/null || git merge-base HEAD CHERRY_PICK_HEAD):<filepath> > /tmp/base.yaml

# Our version (current HEAD)
git show HEAD:<filepath> > /tmp/ours.yaml

# Their version
# For merge:
git show MERGE_HEAD:<filepath> > /tmp/theirs.yaml
# For rebase:
git show REBASE_HEAD:<filepath> > /tmp/theirs.yaml
# For cherry-pick:
git show CHERRY_PICK_HEAD:<filepath> > /tmp/theirs.yaml
```

**Perforce:**

Follow this procedure in order:

**Step 2-1: Check if using streams**
```bash
# Check current client's stream (empty = not using streams)
p4 client -o | grep "^Stream:"

# If using streams, identify current stream
p4 info | grep "clientStream"
```

**Step 2-2: Get file history and changelist context**
```bash
# File history with integration info
p4 filelog -m 10 <filepath>

# Recent changelists affecting this file
p4 changes -l -m 5 <filepath>

# Get details of specific changelist
p4 describe -s <changelist_number>
```

**Step 2-3: If streams detected, gather cross-stream context**
```bash
# View stream hierarchy to understand parent/child relationships
p4 streams //depot/...

# Check integration history (where changes came from)
p4 integrated <filepath>

# Check unmerged changes between current stream and parent
p4 interchanges -S <current_stream> <parent_stream>

# Get integration status
p4 istat <current_stream>/...
```

**Step 2-4: Extract file versions for 3-way merge**
```bash
# Base version (common ancestor)
p4 print <filepath>#have > /tmp/base.yaml

# Our version (current workspace)
cp <filepath> /tmp/ours.yaml

# Their version (from source stream or revision)
p4 print <source_stream>/<filepath>#head > /tmp/theirs.yaml
# Or specific revision:
p4 print <filepath>#<revision> > /tmp/theirs.yaml
```

### Step 3: Perform Semantic Merge

```bash
# 3-way semantic merge
unityflow merge /tmp/base.yaml /tmp/ours.yaml /tmp/theirs.yaml -o merged.yaml

# Or attempt automatic resolution
unityflow resolve --dry-run  # Preview first
unityflow resolve            # Actual resolution
```

### Step 4: Analyze Conflicts and Query User

If merge results contain conflicts:

1. **Display Conflict Details**
   ```
   [Conflict 1] Player/Transform
     Property: m_LocalPosition.x
     Base:   0
     Ours:   10 (commit abc123: "Adjust player start position")
     Theirs: 5  (commit def456: "Level design adjustments")
   ```

2. **Context-Based Suggestions**
   - Understand intent from commit/changelist descriptions
   - Analyze which side represents a more intentional change
   - Explain suggestion and reasoning

3. **Query User**
   ```
   For this conflict:
   - (o) ours: Use 10 - "Adjust player start position"
   - (t) theirs: Use 5 - "Level design adjustments"
   - (b) base: Use 0 - Keep original value

   Which value would you like to use?
   ```

### Step 5: Apply Results

```bash
# Save resolved file
unityflow normalize merged.yaml  # Normalize

# Git: Mark as resolved
git add <filepath>

# Perforce: Mark as resolved
p4 resolve -ae <filepath>
```

---

## Usage Examples

### User Request Example

```
There's a merge conflict in Player.prefab. Please resolve it.
```

### AI Response Example

```
I'll analyze the conflict in Player.prefab.

[Context Analysis]
- Our branch (abc123): "Adjust player movement speed"
- Their branch (def456): "Level balancing"

[Auto-Resolved]
✅ Player/Rigidbody2D/m_Mass: 1.5 (theirs) - Non-overlapping change
✅ Player/SpriteRenderer/m_Color: rgba(1,1,1,1) (ours) - Non-overlapping change

[Conflict Detected]
❌ Player/MonoBehaviour/moveSpeed
   - Base: 5.0
   - Ours: 7.0 ("Adjust player movement speed")
   - Theirs: 4.0 ("Level balancing")

This property was intentionally modified in both branches.
"Adjust player movement speed" appears to be a more specific change.

Which value would you like to use?
1. 7.0 (ours) - Increase speed
2. 4.0 (theirs) - Decrease speed
3. 5.0 (base) - Keep original value
4. Enter a different value
```

---

## Recommended Workflow

1. **Backup**: Save original files before merging
2. **Merge**: Use `unityflow merge` to process Unity YAML format
3. **Validate**: Run `unityflow validate` to check file integrity
4. **Test**: Verify behavior in Unity Editor

---

## Related Commands

```bash
# Preview conflicts
unityflow resolve --dry-run

# Auto-resolve only (no interaction)
unityflow resolve --accept ours
unityflow resolve --accept theirs

# Resolve specific file only
unityflow resolve-file base.yaml ours.yaml theirs.yaml -o result.yaml

# Check diff
unityflow diff old.prefab new.prefab

# Verify result
unityflow validate merged.prefab
```

---

## Summary

- Auto-resolve: different objects/components/properties → safe to merge automatically
- User confirmation: same property changed, deletion vs modification, semantic conflicts
- Commit keywords guide priority: fix/bug (high) > add/new (medium) > refactor (low)

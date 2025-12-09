#!/bin/bash
# Install prefab-tool git integration
# Run this script from your Unity project root

set -e

echo "=== prefab-tool Git Integration Setup ==="
echo

# Check if prefab-tool is installed
if ! command -v prefab-tool &> /dev/null; then
    echo "Error: prefab-tool is not installed or not in PATH"
    echo "Install it with: pip install prefab-tool"
    exit 1
fi

PREFAB_TOOL_PATH=$(which prefab-tool)
echo "Found prefab-tool at: $PREFAB_TOOL_PATH"

# Setup options
SCOPE="${1:-local}"  # local or global

if [ "$SCOPE" = "global" ]; then
    echo "Setting up GLOBAL git configuration..."
    GIT_CONFIG_CMD="git config --global"
else
    echo "Setting up LOCAL git configuration (project only)..."
    GIT_CONFIG_CMD="git config"

    # Check if we're in a git repo
    if ! git rev-parse --git-dir > /dev/null 2>&1; then
        echo "Error: Not in a git repository"
        echo "Run this script from your Unity project root, or use 'install.sh global'"
        exit 1
    fi
fi

# Configure diff driver
echo "Configuring diff driver..."
$GIT_CONFIG_CMD diff.unity.textconv "prefab-tool git-textconv"
$GIT_CONFIG_CMD diff.unity.cachetextconv true

# Configure merge driver
echo "Configuring merge driver..."
$GIT_CONFIG_CMD merge.unity.name "Unity YAML Merge (prefab-tool)"
$GIT_CONFIG_CMD merge.unity.driver "prefab-tool merge %O %A %B -o %A --path %P"
$GIT_CONFIG_CMD merge.unity.recursive binary

echo

# Setup .gitattributes if local
if [ "$SCOPE" = "local" ]; then
    GITATTRIBUTES=".gitattributes"

    # Check if .gitattributes exists
    if [ -f "$GITATTRIBUTES" ]; then
        echo "Found existing .gitattributes"

        # Check if unity diff/merge is already configured
        if grep -q "diff=unity" "$GITATTRIBUTES"; then
            echo "Unity diff already configured in .gitattributes"
        else
            echo "Adding Unity file patterns to .gitattributes..."
            echo "" >> "$GITATTRIBUTES"
            echo "# Unity YAML files - use prefab-tool for diff and merge" >> "$GITATTRIBUTES"
            echo "*.prefab diff=unity merge=unity text eol=lf" >> "$GITATTRIBUTES"
            echo "*.unity diff=unity merge=unity text eol=lf" >> "$GITATTRIBUTES"
            echo "*.asset diff=unity merge=unity text eol=lf" >> "$GITATTRIBUTES"
        fi
    else
        echo "Creating .gitattributes..."
        cat > "$GITATTRIBUTES" << 'EOF'
# Unity YAML files - use prefab-tool for diff and merge
*.prefab diff=unity merge=unity text eol=lf
*.unity diff=unity merge=unity text eol=lf
*.asset diff=unity merge=unity text eol=lf
*.mat diff=unity merge=unity text eol=lf
*.controller diff=unity merge=unity text eol=lf
*.anim diff=unity merge=unity text eol=lf

# Unity meta files
*.meta text eol=lf
EOF
    fi
fi

echo
echo "=== Setup Complete ==="
echo
echo "Git is now configured to use prefab-tool for Unity files."
echo
echo "Benefits:"
echo "  - git diff shows meaningful changes (no serialization noise)"
echo "  - git merge handles Unity files more intelligently"
echo
echo "Test it with:"
echo "  git diff HEAD~1 -- '*.prefab'"
echo

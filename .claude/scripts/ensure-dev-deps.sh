#!/bin/bash
# ensure-dev-deps.sh
# Installs development dependencies for unityflow development

set -e

GREEN='\033[0;32m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[unityflow-dev]${NC} $1"
}

# Check if we're in the unityflow repo
if [ ! -f "pyproject.toml" ] || ! grep -q "name = \"unityflow\"" pyproject.toml 2>/dev/null; then
    # Not in unityflow repo, skip
    exit 0
fi

log_info "Installing development dependencies..."

# Remove old black from user local to avoid PATH conflicts
rm -f /root/.local/bin/black 2>/dev/null || true

# Install dev dependencies (pinned versions matching pyproject.toml)
pip install --quiet --upgrade "black~=26.1.0" "ruff~=0.14.0" "pytest~=9.0.0"

log_info "Development tools ready (black 26.1.x, ruff 0.14.x, pytest 9.0.x)"

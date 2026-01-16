#!/bin/bash
# ensure-unityflow.sh
# Automatically installs unityflow in an isolated virtual environment
# This script is idempotent - safe to run multiple times

set -e

# Configuration
VENV_DIR="${HOME}/.unityflow-venv"
UNITYFLOW_REPO="https://github.com/TrueCyan/unityflow.git"

# Colors for output (optional, works in most terminals)
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[unityflow]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[unityflow]${NC} $1"
}

log_error() {
    echo -e "${RED}[unityflow]${NC} $1"
}

# Check if Python 3.12+ is available
check_python() {
    if command -v python3.12 &> /dev/null; then
        PYTHON_CMD="python3.12"
    elif command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
        MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)
        if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 12 ]; then
            PYTHON_CMD="python3"
        else
            log_warn "Python 3.12+ recommended, but found Python $PYTHON_VERSION"
            log_warn "Will try to proceed with Python 3..."
            PYTHON_CMD="python3"
        fi
    else
        log_error "Python 3 not found. Please install Python 3.12+"
        exit 1
    fi
}

# Create virtual environment if it doesn't exist
create_venv() {
    if [ ! -d "$VENV_DIR" ]; then
        log_info "Creating virtual environment at $VENV_DIR..."
        $PYTHON_CMD -m venv "$VENV_DIR"
        log_info "Virtual environment created."
    else
        log_info "Virtual environment already exists at $VENV_DIR"
    fi
}

# Install unityflow if not installed
install_unityflow() {
    # Activate venv
    source "$VENV_DIR/bin/activate"

    # Check if unityflow is already installed
    if pip show unityflow &> /dev/null; then
        INSTALLED_VERSION=$(pip show unityflow | grep "^Version:" | cut -d' ' -f2)
        log_info "unityflow $INSTALLED_VERSION is already installed."

        # Optional: Check for updates
        # pip install --upgrade unityflow
    else
        log_info "Installing unityflow from PyPI..."
        pip install --quiet unityflow

        if pip show unityflow &> /dev/null; then
            INSTALLED_VERSION=$(pip show unityflow | grep "^Version:" | cut -d' ' -f2)
            log_info "unityflow $INSTALLED_VERSION installed successfully!"
        else
            log_error "Failed to install unityflow"
            exit 1
        fi
    fi

    deactivate
}

# Create wrapper script for easy access
create_wrapper() {
    WRAPPER_PATH="$VENV_DIR/bin/unityflow-wrapper"

    cat > "$WRAPPER_PATH" << 'WRAPPER_EOF'
#!/bin/bash
# Wrapper script to run unityflow from its virtual environment
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
VENV_DIR="$(dirname "$SCRIPT_DIR")"
source "$VENV_DIR/bin/activate"
unityflow "$@"
WRAPPER_EOF

    chmod +x "$WRAPPER_PATH"
    log_info "Wrapper script created at $WRAPPER_PATH"
}

# Create a symlink in a common path for easy access
setup_path() {
    # Try to create symlink in ~/.local/bin (usually in PATH)
    LOCAL_BIN="$HOME/.local/bin"
    if [ ! -d "$LOCAL_BIN" ]; then
        mkdir -p "$LOCAL_BIN"
    fi

    # Create symlink if it doesn't exist or is broken
    if [ ! -L "$LOCAL_BIN/unityflow" ] || [ ! -e "$LOCAL_BIN/unityflow" ]; then
        ln -sf "$VENV_DIR/bin/unityflow" "$LOCAL_BIN/unityflow"
        log_info "Symlink created: $LOCAL_BIN/unityflow -> $VENV_DIR/bin/unityflow"
    fi
}

# Print usage instructions (for Claude to understand)
print_instructions() {
    echo ""
    echo "[UNITYFLOW SETUP COMPLETE]"
    echo "Virtual environment: $VENV_DIR"
    echo "Symlink: ~/.local/bin/unityflow"
    echo ""
    echo "You can now use 'unityflow' command directly if ~/.local/bin is in PATH."
    echo "Otherwise use: $VENV_DIR/bin/unityflow <command>"
    echo ""
}

# Main
main() {
    log_info "Ensuring unityflow is installed..."
    check_python
    create_venv
    install_unityflow
    create_wrapper
    setup_path
    print_instructions
}

main

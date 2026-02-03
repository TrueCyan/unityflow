#!/bin/sh
set -e

VENV_DIR="${HOME}/.unityflow-venv"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { printf "${GREEN}[unityflow]${NC} %s\n" "$1"; }
log_warn() { printf "${YELLOW}[unityflow]${NC} %s\n" "$1"; }
log_error() { printf "${RED}[unityflow]${NC} %s\n" "$1"; }

find_python() {
    for cmd in python3.12 python3.11 python3 python; do
        if command -v "$cmd" >/dev/null 2>&1; then
            version=$("$cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null) || continue
            major=$(echo "$version" | cut -d. -f1)
            minor=$(echo "$version" | cut -d. -f2)
            if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
                echo "$cmd"
                return 0
            fi
        fi
    done
    return 1
}

install_python() {
    log_info "Python 3.11+ not found. Attempting to install..."

    if command -v brew >/dev/null 2>&1; then
        log_info "Installing Python via Homebrew..."
        brew install python@3.12 || true
    elif command -v apt-get >/dev/null 2>&1; then
        log_info "Installing Python via apt..."
        sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip || true
    elif command -v dnf >/dev/null 2>&1; then
        log_info "Installing Python via dnf..."
        sudo dnf install -y python3 python3-pip || true
    elif command -v pacman >/dev/null 2>&1; then
        log_info "Installing Python via pacman..."
        sudo pacman -S --noconfirm python python-pip || true
    else
        log_error "Cannot auto-install Python."
        log_error "Please install Python 3.11+ from https://python.org/downloads/"
        return 1
    fi
}

create_venv() {
    python_cmd="$1"
    if [ -d "$VENV_DIR" ]; then
        log_info "Virtual environment already exists at $VENV_DIR"
        return 0
    fi

    log_info "Creating virtual environment at $VENV_DIR..."
    "$python_cmd" -m venv "$VENV_DIR"
    log_info "Virtual environment created."
}

install_unityflow() {
    pip_cmd="$VENV_DIR/bin/pip"

    if "$pip_cmd" show unityflow >/dev/null 2>&1; then
        version=$("$pip_cmd" show unityflow | grep "^Version:" | cut -d' ' -f2)
        log_info "unityflow $version is already installed."
        return 0
    fi

    log_info "Installing unityflow[bridge] from PyPI..."
    "$pip_cmd" install --quiet "unityflow[bridge]"

    if "$pip_cmd" show unityflow >/dev/null 2>&1; then
        version=$("$pip_cmd" show unityflow | grep "^Version:" | cut -d' ' -f2)
        log_info "unityflow $version installed successfully!"
    else
        log_error "Failed to install unityflow"
        return 1
    fi
}

setup_path() {
    unityflow_bin="$VENV_DIR/bin/unityflow"
    unityflow_bridge_bin="$VENV_DIR/bin/unityflow-bridge"

    if [ -w "/usr/local/bin" ]; then
        ln -sf "$unityflow_bin" "/usr/local/bin/unityflow"
        ln -sf "$unityflow_bridge_bin" "/usr/local/bin/unityflow-bridge"
        log_info "Symlink: /usr/local/bin/unityflow"
        log_info "Symlink: /usr/local/bin/unityflow-bridge"
    else
        local_bin="$HOME/.local/bin"
        mkdir -p "$local_bin"
        ln -sf "$unityflow_bin" "$local_bin/unityflow"
        ln -sf "$unityflow_bridge_bin" "$local_bin/unityflow-bridge"
        log_info "Symlink: $local_bin/unityflow"
        log_info "Symlink: $local_bin/unityflow-bridge"
    fi
}

main() {
    log_info "Ensuring unityflow is installed..."

    python_cmd=$(find_python) || {
        install_python
        python_cmd=$(find_python) || {
            log_error "Python 3.11+ is required but could not be installed."
            log_warn "Install Python manually: https://python.org/downloads/"
            exit 0
        }
    }

    log_info "Found Python: $python_cmd"

    create_venv "$python_cmd" || exit 0
    install_unityflow || exit 0
    setup_path || exit 0

    echo ""
    echo "[UNITYFLOW READY] unityflow command is now available."
    echo ""
}

main

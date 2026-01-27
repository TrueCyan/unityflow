#!/usr/bin/env node
const { execSync, spawnSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const isWindows = os.platform() === "win32";
const isMac = os.platform() === "darwin";
const homeDir = os.homedir();
const venvDir = path.join(homeDir, ".unityflow-venv");

const GREEN = "\x1b[32m";
const YELLOW = "\x1b[33m";
const RED = "\x1b[31m";
const NC = "\x1b[0m";

function log(msg) {
  console.log(`${GREEN}[unityflow]${NC} ${msg}`);
}

function warn(msg) {
  console.log(`${YELLOW}[unityflow]${NC} ${msg}`);
}

function error(msg) {
  console.log(`${RED}[unityflow]${NC} ${msg}`);
}

function commandExists(cmd) {
  try {
    if (isWindows) {
      execSync(`where ${cmd}`, { stdio: "ignore" });
    } else {
      execSync(`command -v ${cmd}`, { stdio: "ignore" });
    }
    return true;
  } catch {
    return false;
  }
}

function runCommand(cmd, options = {}) {
  try {
    return execSync(cmd, {
      encoding: "utf8",
      stdio: options.silent ? "pipe" : "inherit",
      ...options,
    });
  } catch (e) {
    if (options.ignoreError) return null;
    throw e;
  }
}

function getPythonVersion(pythonCmd) {
  try {
    const output = execSync(
      `${pythonCmd} -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"`,
      { encoding: "utf8", stdio: "pipe" }
    );
    return output.trim();
  } catch {
    return null;
  }
}

function findPython() {
  const candidates = isWindows
    ? ["python", "python3", "py -3"]
    : ["python3.12", "python3.11", "python3", "python"];

  for (const cmd of candidates) {
    if (commandExists(cmd.split(" ")[0])) {
      const version = getPythonVersion(cmd);
      if (version) {
        const [major, minor] = version.split(".").map(Number);
        if (major >= 3 && minor >= 11) {
          return { cmd, version };
        }
      }
    }
  }
  return null;
}

function installPython() {
  log("Python 3.11+ not found. Attempting to install...");

  if (isWindows) {
    if (commandExists("winget")) {
      log("Installing Python via winget...");
      runCommand("winget install Python.Python.3.12 --accept-source-agreements --accept-package-agreements", {
        ignoreError: true,
      });
    } else if (commandExists("choco")) {
      log("Installing Python via chocolatey...");
      runCommand("choco install python --yes", { ignoreError: true });
    } else {
      error("Cannot auto-install Python on Windows.");
      error("Please install Python 3.12+ from https://python.org/downloads/");
      throw new Error("Python auto-install not available");
    }
  } else if (isMac) {
    if (commandExists("brew")) {
      log("Installing Python via Homebrew...");
      runCommand("brew install python@3.12", { ignoreError: true });
    } else {
      error("Cannot auto-install Python on macOS without Homebrew.");
      error("Install Homebrew: /bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"");
      error("Or install Python from https://python.org/downloads/");
      throw new Error("Python auto-install not available");
    }
  } else {
    if (commandExists("apt-get")) {
      log("Installing Python via apt...");
      runCommand("sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip", {
        ignoreError: true,
      });
    } else if (commandExists("dnf")) {
      log("Installing Python via dnf...");
      runCommand("sudo dnf install -y python3 python3-pip", { ignoreError: true });
    } else if (commandExists("pacman")) {
      log("Installing Python via pacman...");
      runCommand("sudo pacman -S --noconfirm python python-pip", { ignoreError: true });
    } else {
      error("Cannot auto-install Python. Please install Python 3.12+ manually.");
      throw new Error("Python auto-install not available");
    }
  }

  const python = findPython();
  if (!python) {
    error("Python installation failed. Please install Python 3.11+ manually.");
    throw new Error("Python installation failed");
  }
  return python;
}

function createVenv(pythonCmd) {
  if (fs.existsSync(venvDir)) {
    log(`Virtual environment already exists at ${venvDir}`);
    return;
  }

  log(`Creating virtual environment at ${venvDir}...`);
  runCommand(`${pythonCmd} -m venv "${venvDir}"`);
  log("Virtual environment created.");
}

function getPipCmd() {
  if (isWindows) {
    return `"${path.join(venvDir, "Scripts", "pip.exe")}"`;
  }
  return `"${path.join(venvDir, "bin", "pip")}"`;
}

function getUnityflowCmd() {
  if (isWindows) {
    return path.join(venvDir, "Scripts", "unityflow.exe");
  }
  return path.join(venvDir, "bin", "unityflow");
}

function installUnityflow() {
  const pipCmd = getPipCmd();

  try {
    const output = execSync(`${pipCmd} show unityflow`, {
      encoding: "utf8",
      stdio: "pipe",
    });
    const versionMatch = output.match(/^Version:\s*(.+)$/m);
    if (versionMatch) {
      log(`unityflow ${versionMatch[1]} is already installed.`);
      return;
    }
  } catch {
    // Not installed
  }

  log("Installing unityflow from PyPI...");
  runCommand(`${pipCmd} install --quiet unityflow`);

  try {
    const output = execSync(`${pipCmd} show unityflow`, {
      encoding: "utf8",
      stdio: "pipe",
    });
    const versionMatch = output.match(/^Version:\s*(.+)$/m);
    if (versionMatch) {
      log(`unityflow ${versionMatch[1]} installed successfully!`);
    }
  } catch {
    throw new Error("Failed to install unityflow");
  }
}

function createWrapper() {
  if (isWindows) {
    const wrapperPath = path.join(venvDir, "Scripts", "unityflow-wrapper.cmd");
    const content = `@echo off\r\n"${getUnityflowCmd()}" %*\r\n`;
    fs.writeFileSync(wrapperPath, content);
    log(`Wrapper script created at ${wrapperPath}`);
  } else {
    const wrapperPath = path.join(venvDir, "bin", "unityflow-wrapper");
    const content = `#!/bin/bash
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
VENV_DIR="$(dirname "$SCRIPT_DIR")"
source "$VENV_DIR/bin/activate"
unityflow "$@"
`;
    fs.writeFileSync(wrapperPath, content, { mode: 0o755 });
    log(`Wrapper script created at ${wrapperPath}`);
  }
}

function setupPath() {
  const unityflowBin = getUnityflowCmd();

  if (isWindows) {
    const localBin = path.join(homeDir, ".local", "bin");
    if (!fs.existsSync(localBin)) {
      fs.mkdirSync(localBin, { recursive: true });
    }
    const linkPath = path.join(localBin, "unityflow.cmd");
    const content = `@echo off\r\n"${unityflowBin}" %*\r\n`;
    fs.writeFileSync(linkPath, content);
    log(`Wrapper created at ${linkPath}`);
    warn(`Add ${localBin} to your PATH if not already added.`);
  } else {
    const usrLocalBin = "/usr/local/bin";
    const localBin = path.join(homeDir, ".local", "bin");
    let targetDir;

    try {
      fs.accessSync(usrLocalBin, fs.constants.W_OK);
      targetDir = usrLocalBin;
    } catch {
      targetDir = localBin;
      if (!fs.existsSync(localBin)) {
        fs.mkdirSync(localBin, { recursive: true });
      }
    }

    const linkPath = path.join(targetDir, "unityflow");
    try {
      fs.unlinkSync(linkPath);
    } catch {
      // File doesn't exist
    }
    fs.symlinkSync(unityflowBin, linkPath);
    log(`Symlink: ${linkPath}`);
  }
}

function main() {
  try {
    log("Ensuring unityflow is installed...");

    let python = findPython();
    if (!python) {
      python = installPython();
      if (!python) {
        error("Python 3.11+ is required but could not be installed.");
        return;
      }
    } else {
      log(`Found Python ${python.version}`);
    }

    createVenv(python.cmd);
    installUnityflow();
    createWrapper();
    setupPath();

    console.log("");
    console.log("[UNITYFLOW READY] unityflow command is now available.");
    console.log("");
  } catch (e) {
    error(`Setup failed: ${e.message}`);
    warn("You can install unityflow manually: pip install unityflow");
  }
}

main();

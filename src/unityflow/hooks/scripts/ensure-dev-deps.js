#!/usr/bin/env node
const { execSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const GREEN = "\x1b[32m";
const NC = "\x1b[0m";

function log(msg) {
  console.log(`${GREEN}[unityflow-dev]${NC} ${msg}`);
}

function main() {
  const pyprojectPath = path.join(process.cwd(), "pyproject.toml");

  if (!fs.existsSync(pyprojectPath)) {
    return;
  }

  const content = fs.readFileSync(pyprojectPath, "utf8");
  if (!content.includes('name = "unityflow"')) {
    return;
  }

  log("Installing development dependencies...");

  try {
    execSync('pip install --quiet --upgrade "black~=26.1.0" "ruff~=0.14.0" "pytest~=9.0.0"', {
      stdio: "inherit",
    });
    log("Development tools ready (black 26.1.x, ruff 0.14.x, pytest 9.0.x)");
  } catch (e) {
    console.error("Failed to install development dependencies:", e.message);
  }
}

main();

#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLIENT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON_BIN=""

usage() {
  cat <<'EOF'
Usage: ./install/unix/verify_client.sh [options]

Options:
  --python PATH      Python executable to use when not verifying through .venv
  -h, --help         Show this help message
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --python)
      shift
      [[ $# -gt 0 ]] || { echo "Missing value for --python" >&2; exit 1; }
      PYTHON_BIN="$1"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
  shift
done

if [[ -n "${PYTHON_BIN}" ]]; then
  ACTIVE_PYTHON="${PYTHON_BIN}"
elif [[ -x "${CLIENT_ROOT}/.venv/bin/python" ]]; then
  ACTIVE_PYTHON="${CLIENT_ROOT}/.venv/bin/python"
elif command -v python3.11 >/dev/null 2>&1; then
  ACTIVE_PYTHON="python3.11"
else
  echo "No Python interpreter available for verification." >&2
  echo "Use ./install/unix/verify_client.sh --python python3.11 or create .venv first." >&2
  exit 1
fi

echo "Checking required Python packages"
"${ACTIVE_PYTHON}" - <<'PY'
import importlib

required = ["aiohttp", "jinja2", "numpy", "scipy"]
bundled = ["aiortc", "cv2"]

for name in required:
    importlib.import_module(name)
    print(f"[ok] required package: {name}")

for name in bundled:
    importlib.import_module(name)
    print(f"[ok] bundled package: {name}")
PY

echo "Checking TLS files"
for path in "${CLIENT_ROOT}/config/cert.pem" "${CLIENT_ROOT}/config/key.pem"; do
  if [[ ! -f "${path}" ]]; then
    echo "Missing TLS file: ${path}" >&2
    exit 1
  fi
  echo "[ok] ${path}"
done

echo "Compiling Python sources"
"${ACTIVE_PYTHON}" -m compileall "${CLIENT_ROOT}/main.py" "${CLIENT_ROOT}/backend" >/dev/null

echo
echo "Environment verification complete."

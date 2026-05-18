#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLIENT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON_BIN="python3.11"
FORCE_CERT=0
USE_VENV=""

usage() {
  cat <<'EOF'
Usage: ./install/unix/bootstrap_client.sh [options]

Options:
  --python PATH      Python executable to use
  --venv yes|no      Create a Python 3.11 virtual environment or skip it
  --force-cert       Regenerate local relay TLS files even if they exist
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
    --venv)
      shift
      [[ $# -gt 0 ]] || { echo "Missing value for --venv" >&2; exit 1; }
      case "$1" in
        yes|YES|Yes|y|Y)
          USE_VENV="yes"
          ;;
        no|NO|No|n|N)
          USE_VENV="no"
          ;;
        *)
          echo "Invalid value for --venv: $1" >&2
          echo "Use --venv yes or --venv no" >&2
          exit 1
          ;;
      esac
      ;;
    --force-cert)
      FORCE_CERT=1
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

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Python executable not found: ${PYTHON_BIN}" >&2
  exit 1
fi

echo "Using Python: ${PYTHON_BIN}"
"${PYTHON_BIN}" -c 'import sys; assert sys.version_info[:2] == (3, 11), "Python 3.11 is required"'

if [[ -z "${USE_VENV}" ]]; then
  read -r -p "Do you want to install a Python 3.11 virtual environment? (yes/no): " USE_VENV
fi

case "${USE_VENV}" in
  yes|YES|Yes|y|Y)
    USE_VENV="yes"
    ;;
  no|NO|No|n|N)
    USE_VENV="no"
    ;;
  *)
    echo "Please answer yes or no." >&2
    exit 1
    ;;
esac

if [[ "${USE_VENV}" == "yes" ]]; then
  if [[ ! -d "${CLIENT_ROOT}/.venv" ]]; then
    echo "Creating virtual environment at ${CLIENT_ROOT}/.venv"
    "${PYTHON_BIN}" -m venv "${CLIENT_ROOT}/.venv"
  fi
  ACTIVE_PYTHON="${CLIENT_ROOT}/.venv/bin/python"
else
  echo "Skipping virtual environment installation"
  ACTIVE_PYTHON="${PYTHON_BIN}"
fi

echo "Upgrading pip tooling"
"${ACTIVE_PYTHON}" -m pip install --upgrade pip setuptools wheel

echo "Installing dependencies"
"${ACTIVE_PYTHON}" -m pip install -r "${CLIENT_ROOT}/install/requirements.txt"

CERT_ARGS=()
if [[ ${FORCE_CERT} -eq 1 ]]; then
  CERT_ARGS+=(--force)
fi

"${SCRIPT_DIR}/generate_dev_cert.sh" "${CERT_ARGS[@]}"

echo
echo "Bootstrap complete."
if [[ "${USE_VENV}" == "yes" ]]; then
  echo "Activate venv: source .venv/bin/activate"
  echo "Verify env:    ./install/unix/verify_client.sh"
  echo "Run client:    .venv/bin/python main.py"
else
  echo "Verify env:    ./install/unix/verify_client.sh --python ${PYTHON_BIN}"
  echo "Run client:    ${PYTHON_BIN} main.py"
fi

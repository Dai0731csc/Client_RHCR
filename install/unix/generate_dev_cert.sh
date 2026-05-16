#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLIENT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
CONFIG_DIR="${CLIENT_ROOT}/config"
CERT_PATH="${CONFIG_DIR}/cert.pem"
KEY_PATH="${CONFIG_DIR}/key.pem"
FORCE=0

if [[ "${1:-}" == "--force" ]]; then
  FORCE=1
fi

if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl is required to generate TLS certificates." >&2
  exit 1
fi

mkdir -p "${CONFIG_DIR}"

if [[ ${FORCE} -eq 0 && -f "${CERT_PATH}" && -f "${KEY_PATH}" ]]; then
  echo "TLS files already exist, keeping current cert.pem and key.pem"
  exit 0
fi

HOSTNAME_VALUE="$(hostname)"
SHORT_HOSTNAME="${HOSTNAME_VALUE%%.*}"
OPENSSL_CONFIG="$(mktemp)"
trap 'rm -f "${OPENSSL_CONFIG}"' EXIT

cat > "${OPENSSL_CONFIG}" <<EOF
[req]
default_bits = 2048
prompt = no
default_md = sha256
distinguished_name = dn
x509_extensions = v3_req

[dn]
CN = ${HOSTNAME_VALUE}

[v3_req]
subjectAltName = @alt_names
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth

[alt_names]
DNS.1 = localhost
DNS.2 = ${HOSTNAME_VALUE}
DNS.3 = ${SHORT_HOSTNAME}
IP.1 = 127.0.0.1
IP.2 = ::1
EOF

openssl req \
  -x509 \
  -nodes \
  -days 825 \
  -newkey rsa:2048 \
  -keyout "${KEY_PATH}" \
  -out "${CERT_PATH}" \
  -config "${OPENSSL_CONFIG}"

chmod 600 "${KEY_PATH}"
echo "Generated ${CERT_PATH} and ${KEY_PATH}"

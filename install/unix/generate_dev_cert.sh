#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLIENT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CONFIG_DIR="${CLIENT_ROOT}/config"
CERT_DIR="${CONFIG_DIR}/certificate/local"
CA_KEY_PATH="${CERT_DIR}/ca.key"
CA_CERT_PATH="${CERT_DIR}/ca.crt"
CERT_PATH="${CERT_DIR}/cert.pem"
KEY_PATH="${CERT_DIR}/key.pem"
CSR_PATH="${CERT_DIR}/cert.csr"
SERIAL_PATH="${CERT_DIR}/ca.srl"
FORCE=0

if [[ "${1:-}" == "--force" ]]; then
  FORCE=1
fi

if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl is required to generate TLS certificates." >&2
  exit 1
fi

mkdir -p "${CERT_DIR}"

if [[ ${FORCE} -eq 0 && -f "${CA_CERT_PATH}" && -f "${CERT_PATH}" && -f "${KEY_PATH}" ]]; then
  echo "TLS files already exist, keeping current local CA and relay certificate"
  exit 0
fi

HOSTNAME_VALUE="$(hostname)"
SHORT_HOSTNAME="${HOSTNAME_VALUE%%.*}"
OPENSSL_CONFIG="$(mktemp)"
trap 'rm -f "${OPENSSL_CONFIG}"' EXIT

cat > "${OPENSSL_CONFIG}" <<EOF
[v3_req]
subjectAltName = @alt_names
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth

[alt_names]
DNS.1 = localhost
DNS.2 = ${HOSTNAME_VALUE}
DNS.3 = ${SHORT_HOSTNAME}
IP.1 = 127.0.0.1
IP.2 = ::1
EOF

openssl genrsa -out "${CA_KEY_PATH}" 2048 >/dev/null 2>&1
openssl req \
  -x509 \
  -new \
  -nodes \
  -key "${CA_KEY_PATH}" \
  -sha256 \
  -days 825 \
  -out "${CA_CERT_PATH}" \
  -subj "/CN=RHCR Local Relay CA"

openssl genrsa -out "${KEY_PATH}" 2048 >/dev/null 2>&1
openssl req \
  -new \
  -key "${KEY_PATH}" \
  -out "${CSR_PATH}" \
  -subj "/CN=localhost"

openssl x509 \
  -req \
  -in "${CSR_PATH}" \
  -CA "${CA_CERT_PATH}" \
  -CAkey "${CA_KEY_PATH}" \
  -CAcreateserial \
  -out "${CERT_PATH}" \
  -days 825 \
  -sha256 \
  -extfile "${OPENSSL_CONFIG}" \
  -extensions v3_req

rm -f "${CSR_PATH}" "${SERIAL_PATH}"
chmod 600 "${CA_KEY_PATH}" "${KEY_PATH}"
echo "Generated ${CA_CERT_PATH}, ${CERT_PATH}, and ${KEY_PATH}"

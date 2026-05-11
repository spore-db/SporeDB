#!/usr/bin/env bash
# Generate Ed25519 keypair for SporeDB cloud tier JWT signing.
set -euo pipefail

KEYS_DIR="${1:-keys}"

mkdir -p "$KEYS_DIR"

echo "Generating Ed25519 keypair in ${KEYS_DIR}/..."

openssl genpkey -algorithm Ed25519 -out "${KEYS_DIR}/cloud_private.pem"
openssl pkey -in "${KEYS_DIR}/cloud_private.pem" -pubout -out "${KEYS_DIR}/cloud_public.pem"

chmod 600 "${KEYS_DIR}/cloud_private.pem"
chmod 644 "${KEYS_DIR}/cloud_public.pem"

echo "Keys generated:"
echo "  Private: ${KEYS_DIR}/cloud_private.pem (mode 600)"
echo "  Public:  ${KEYS_DIR}/cloud_public.pem  (mode 644)"

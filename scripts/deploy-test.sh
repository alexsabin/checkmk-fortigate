#!/usr/bin/env bash
# Deploys the local plugin tree into the running cmk-test Docker container
# and runs validation. Safe to run repeatedly.
#
# Usage:  ./scripts/deploy-test.sh
set -euo pipefail

CONTAINER="${CONTAINER:-cmk-test}"
SITE="${SITE:-cmk}"
FAMILY="${FAMILY:-fortigate_firmware}"

SRC_DIR="local/lib/python3/cmk_addons/plugins/${FAMILY}"
DEST_PARENT="/omd/sites/${SITE}/local/lib/python3/cmk_addons/plugins"
DEST_DIR="${DEST_PARENT}/${FAMILY}"

if [[ ! -d "${SRC_DIR}" ]]; then
    echo "ERROR: source directory not found: ${SRC_DIR}"
    echo "Run this script from the repo root."
    exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}\$"; then
    echo "ERROR: container '${CONTAINER}' is not running"
    echo "Start it first, then re-run this script."
    exit 1
fi

echo ">> Cleaning caches in source tree"
find "${SRC_DIR}" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
find "${SRC_DIR}" -name '*.pyc' -delete 2>/dev/null || true

echo ">> Removing old copy inside container (if any)"
docker exec "${CONTAINER}" rm -rf "${DEST_DIR}"

echo ">> Copying plugin tree into container"
docker cp "${SRC_DIR}" "${CONTAINER}:${DEST_PARENT}/"

echo ">> Fixing ownership and permissions"
docker exec "${CONTAINER}" chown -R "${SITE}:${SITE}" "${DEST_DIR}"
# Make every file in libexec/ executable (not just agent_fortigate, future-proof)
docker exec "${CONTAINER}" find "${DEST_DIR}/libexec" -type f -exec chmod 755 {} \;

echo ">> Running cmk-validate-plugins"
if docker exec -u "${SITE}" "${CONTAINER}" bash -lc 'cmk-validate-plugins'; then
    echo ">> Validation passed"
else
    echo ">> Validation reported issues above"
    exit 1
fi

echo ">> Reloading Checkmk core (cmk -R)"
docker exec -u "${SITE}" "${CONTAINER}" bash -lc 'cmk -R' || {
    echo "NOTE: cmk -R failed. This is expected before any host is configured."
    echo "      Once you have a host, reload will work."
}

echo ">> Done"

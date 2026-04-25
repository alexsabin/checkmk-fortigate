#!/usr/bin/env bash
# Deploys the local plugin tree into the running cmk-test Docker container,
# runs validation, and restarts the right services based on what changed.
# Safe to run repeatedly.
#
# Usage:
#   ./scripts/deploy-test.sh           # auto-detect what to restart
#   ./scripts/deploy-test.sh --full    # force full omd restart
#   ./scripts/deploy-test.sh --reload  # force cmk -R only (skip Apache)
set -euo pipefail

CONTAINER="${CONTAINER:-cmk-test}"
SITE="${SITE:-cmk}"
FAMILY="${FAMILY:-fortigate_firmware}"

SRC_DIR="local/lib/python3/cmk_addons/plugins/${FAMILY}"
DEST_PARENT="/omd/sites/${SITE}/local/lib/python3/cmk_addons/plugins"
DEST_DIR="${DEST_PARENT}/${FAMILY}"

MODE="auto"
case "${1:-}" in
    --full)   MODE="full"   ;;
    --reload) MODE="reload" ;;
    "")       MODE="auto"   ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
esac

if [[ ! -d "${SRC_DIR}" ]]; then
    echo "ERROR: source directory not found: ${SRC_DIR}"
    echo "Run this script from the repo root."
    exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}\$"; then
    echo "ERROR: container '${CONTAINER}' is not running"
    exit 1
fi

# Decide what to restart by hashing files that affect GUI/registration.
# rulesets/, server_side_calls/, graphing/ -> need Apache restart
# agent_based/, libexec/, checkman/ -> just cmk -R is enough
GUI_HASH_FILE="/tmp/.${CONTAINER}-${FAMILY}-gui-hash"

DIRS_TO_HASH=()
for d in rulesets server_side_calls graphing; do
    [ -d "${SRC_DIR}/${d}" ] && DIRS_TO_HASH+=("${SRC_DIR}/${d}")
done

if [ ${#DIRS_TO_HASH[@]} -eq 0 ]; then
    GUI_CURRENT="no-gui-files"
else
    GUI_CURRENT=$(find "${DIRS_TO_HASH[@]}" -type f -name '*.py' \
        | sort | xargs sha256sum 2>/dev/null | sha256sum | awk '{print $1}')
fi

GUI_CHANGED="no"
if [[ "${MODE}" == "full" ]]; then
    GUI_CHANGED="yes"
elif [[ "${MODE}" == "reload" ]]; then
    GUI_CHANGED="no"
elif [[ ! -f "${GUI_HASH_FILE}" ]] || [[ "$(cat "${GUI_HASH_FILE}" 2>/dev/null)" != "${GUI_CURRENT}" ]]; then
    GUI_CHANGED="yes"
fi

echo ">> Cleaning caches in source tree"
find "${SRC_DIR}" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
find "${SRC_DIR}" -name '*.pyc' -delete 2>/dev/null || true

echo ">> Removing old copy inside container"
docker exec "${CONTAINER}" rm -rf "${DEST_DIR}"

echo ">> Copying plugin tree into container"
docker cp "${SRC_DIR}" "${CONTAINER}:${DEST_PARENT}/"

echo ">> Fixing ownership and permissions"
docker exec "${CONTAINER}" chown -R "${SITE}:${SITE}" "${DEST_DIR}"
docker exec "${CONTAINER}" find "${DEST_DIR}/libexec" -type f -exec chmod 755 {} \; 2>/dev/null || true

echo ">> Running cmk-validate-plugins"
if ! docker exec -u "${SITE}" "${CONTAINER}" bash -lc 'cmk-validate-plugins'; then
    echo ">> Validation reported issues above"
    exit 1
fi

if [[ "${GUI_CHANGED}" == "yes" ]]; then
    echo ">> GUI-affecting files changed (or first run / forced) -> omd restart"
    docker exec "${CONTAINER}" omd restart "${SITE}"
    echo "${GUI_CURRENT}" > "${GUI_HASH_FILE}"
    echo ">> Hard-refresh your browser (Ctrl+F5) to pick up GUI changes"
else
    echo ">> Only check logic changed -> cmk -R (faster)"
    docker exec -u "${SITE}" "${CONTAINER}" bash -lc 'cmk -R' || {
        echo "NOTE: cmk -R failed (often expected before any host is configured)"
    }
fi

echo ">> Done"

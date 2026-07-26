#!/usr/bin/env bash
# Run all Phone Locator tests (local — no GitHub CI).
#
# Usage:
#   ./scripts/test.sh
#   ./scripts/test.sh --integration
#   ./scripts/test.sh --android
#
# Integration:
#   export PHONE_LOCATOR_TEST_URL=http://192.168.1.26:8000/locator
#   export PHONE_LOCATOR_API_TOKEN=<token>

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER_DIR="${REPO_ROOT}/server"
VENV="${SERVER_DIR}/venv"

INTEGRATION=0
ANDROID=0
for arg in "$@"; do
  case "$arg" in
    --integration) INTEGRATION=1 ;;
    --android) ANDROID=1 ;;
  esac
done

echo "==> Phone Locator tests"

if [[ ! -d "${VENV}" ]]; then
  echo "==> Creating server venv"
  python3 -m venv "${VENV}"
fi

echo "==> Installing server dependencies"
"${VENV}/bin/pip" install -q -U pip
"${VENV}/bin/pip" install -q -r "${SERVER_DIR}/requirements-dev.txt"

echo "==> Server unit tests"
(
  cd "${SERVER_DIR}"
  "${VENV}/bin/python" -m unittest discover -s tests -p "test_phase1.py" -v
)

if [[ "${INTEGRATION}" -eq 1 ]]; then
  export PHONE_LOCATOR_TEST_URL="${PHONE_LOCATOR_TEST_URL:-http://192.168.1.26:8000/locator}"
  if [[ -z "${PHONE_LOCATOR_API_TOKEN:-}" ]]; then
    echo "ERROR: Set PHONE_LOCATOR_API_TOKEN for integration tests" >&2
    exit 1
  fi
  echo "==> Integration tests against ${PHONE_LOCATOR_TEST_URL}"
  (
    cd "${SERVER_DIR}"
    "${VENV}/bin/python" -m unittest tests.test_integration -v
  )
fi

if [[ "${ANDROID}" -eq 1 ]] || [[ -f "${REPO_ROOT}/android/gradlew" ]]; then
  if [[ ! -f "${REPO_ROOT}/android/gradlew" ]]; then
    echo "ERROR: android/ not scaffolded yet" >&2
    exit 1
  fi
  echo "==> Android unit tests"
  (cd "${REPO_ROOT}/android" && ./gradlew test)
fi

echo "==> All requested tests passed"

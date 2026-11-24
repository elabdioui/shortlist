#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"
EXAMPLE_FILE="${SCRIPT_DIR}/.env.example"

if [[ ! -f "${ENV_FILE}" ]]; then
  cp "${EXAMPLE_FILE}" "${ENV_FILE}"
  echo "Created ${ENV_FILE} from .env.example"
fi

generate_fernet_key() {
  if command -v python3 >/dev/null 2>&1; then
    python3 -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
  else
    openssl rand -base64 32 | tr '+/' '-_'
  fi
}

CURRENT_KEY="$(grep -E '^SHORTLIST_SECRET_KEY=' "${ENV_FILE}" | head -n1 | cut -d'=' -f2- || true)"
if [[ -z "${CURRENT_KEY}" || "${CURRENT_KEY}" == "change-me-to-a-strong-random-fernet-key" ]]; then
  NEW_KEY="$(generate_fernet_key)"
  if grep -qE '^SHORTLIST_SECRET_KEY=' "${ENV_FILE}"; then
    # Portable in-place replacement (Linux & macOS)
    TMP_FILE="$(mktemp)"
    sed "s|^SHORTLIST_SECRET_KEY=.*|SHORTLIST_SECRET_KEY=${NEW_KEY}|" "${ENV_FILE}" > "${TMP_FILE}"
    mv "${TMP_FILE}" "${ENV_FILE}"
  else
    printf "\nSHORTLIST_SECRET_KEY=%s\n" "${NEW_KEY}" >> "${ENV_FILE}"
  fi
  echo "Generated fresh Fernet SHORTLIST_SECRET_KEY in ${ENV_FILE}"
else
  echo "SHORTLIST_SECRET_KEY is already configured in ${ENV_FILE}"
fi

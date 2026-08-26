#!/usr/bin/env bash
set -euo pipefail

ROOT="${ORCA_ROOT:-/opt/orca-agent-unified}"
ENV_FILE="${ORCA_ENV_FILE:-/etc/orca/orca.env}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "run as root" >&2
  exit 1
fi

id -u orca >/dev/null 2>&1 || useradd --system --home "${ROOT}" --shell /usr/sbin/nologin orca
install -d -o orca -g orca /etc/orca "${ROOT}/data/orca_max_mouny"
install -m 0640 -o root -g orca /dev/null "${ENV_FILE}"

python3 -m venv "${ROOT}/.venv"
"${ROOT}/.venv/bin/pip" install -r "${ROOT}/requirements.txt"
chown -R orca:orca "${ROOT}"
install -m 0644 deploy/orca-max-mouny.service /etc/systemd/system/orca-max-mouny.service
systemctl daemon-reload
systemctl enable orca-max-mouny.service
systemctl restart orca-max-mouny.service
systemctl --no-pager --full status orca-max-mouny.service

#!/usr/bin/env bash
# =============================================================================
# ORCA AGENT — Oracle Cloud Free Tier one-shot setup
#
# What it does (in order, real, on the VM):
#   1. Updates Ubuntu packages
#   2. Installs Python 3.11 + venv + git + tmux + fail2ban + ufw
#   3. Clones hermasorca13-stack/Orca-Agent- to /opt/orca-agent
#   4. Creates a non-root 'orca' user and runs the bot under it
#   5. Builds a Python venv and installs requirements.txt
#   6. Writes /etc/systemd/system/orca-agent.service (auto-restart)
#   7. Writes /opt/orca-agent/.env from /root/.orca.env if present, else
#      interactively prompts for TELEGRAM_BOT_TOKEN and CLAUDE_API_KEY
#   8. Enables and starts the service
#   9. Configures ufw firewall (allow 22 only by default)
#  10. Configures fail2ban
#  11. Prints a status block with public IP, port, logs path, commands
#
# Usage on the VM (after creating it in Oracle console):
#   curl -sL https://raw.githubusercontent.com/hermasorca13-stack/Orca-Agent-/main/deployment/oracle_setup.sh | sudo bash
#   # or upload the script and run:
#   sudo bash ./oracle_setup.sh
#
# Optional env file (so you don't get prompted):
#   sudo bash ./oracle_setup.sh --env-file /root/orca.env
#
# =============================================================================
set -euo pipefail

# ---------- Config ----------
APP_USER="orca"
APP_HOME="/opt/orca-agent"
APP_REPO="https://github.com/hermasorca13-stack/Orca-Agent-.git"
APP_BRANCH="main"
SERVICE_NAME="orca-agent"
LOG_DIR="/var/log/orca-agent"
PYTHON_MIN="3.10"
ENV_FILE="$APP_HOME/.env"
INPUT_ENV_FILE=""

# ---------- Args ----------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file) INPUT_ENV_FILE="$2"; shift 2;;
    -h|--help)  sed -n '2,28p' "$0"; exit 0;;
    *) echo "Unknown arg: $1" >&2; exit 1;;
  esac
done

# ---------- Helpers ----------
log() { printf '\033[1;36m[orca-setup]\033[0m %s\n' "$*"; }
err() { printf '\033[1;31m[orca-setup ERROR]\033[0m %s\n' "$*" >&2; }
die() { err "$*"; exit 1; }

[[ $EUID -eq 0 ]] || die "Re-run as root: sudo bash $0"

if ! command -v lsb_release >/dev/null 2>&1; then
  apt-get update -qq
  apt-get install -y -qq lsb-release >/dev/null
fi
. /etc/os-release
if [[ "$ID" != "ubuntu" ]]; then
  log "⚠️  This script targets Ubuntu. Detected: $ID $VERSION_ID — continuing best-effort."
fi

# ---------- 1. apt update + base packages ----------
log "📦 Updating apt and installing base packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
  python3 python3-venv python3-pip \
  git curl wget tmux htop \
  ufw fail2ban \
  build-essential libssl-dev libffi-dev \
  tesseract-ocr tesseract-ocr-ara \
  poppler-utils >/dev/null

# ---------- 2. Create user ----------
if ! id "$APP_USER" >/dev/null 2>&1; then
  log "👤 Creating user '$APP_USER'..."
  adduser --disabled-password --gecos "Orca Agent" "$APP_USER"
fi

# ---------- 3. Clone repo ----------
if [[ -d "$APP_HOME/.git" ]]; then
  log "🔄 Repo already cloned, pulling latest..."
  sudo -u "$APP_USER" -H bash -c "cd '$APP_HOME' && git pull --ff-only origin $APP_BRANCH"
else
  log "📥 Cloning $APP_REPO to $APP_HOME..."
  install -d -o "$APP_USER" -g "$APP_USER" /opt
  sudo -u "$APP_USER" -H bash -c "git clone --branch '$APP_BRANCH' '$APP_REPO' '$APP_HOME'"
fi

mkdir -p "$LOG_DIR" && chown -R "$APP_USER:$APP_USER" "$LOG_DIR"

# ---------- 4. Python venv + deps ----------
log "🐍 Building Python venv + installing deps (this can take a few minutes)..."
sudo -u "$APP_USER" -H bash -c "
  cd '$APP_HOME'
  python3 -m venv venv
  source venv/bin/activate
  pip install --upgrade pip wheel setuptools
  pip install -r requirements.txt
"

# ---------- 5. .env ----------
if [[ -n "$INPUT_ENV_FILE" && -f "$INPUT_ENV_FILE" ]]; then
  log "🔐 Using env file: $INPUT_ENV_FILE"
  install -m 600 -o "$APP_USER" -g "$APP_USER" "$INPUT_ENV_FILE" "$ENV_FILE"
else
  if [[ -f "$ENV_FILE" ]]; then
    log "ℹ️  Existing .env detected at $ENV_FILE — leaving as-is."
  else
    log "🔐 No .env found. You'll be prompted for required keys (input is hidden)."
    read -rsp "  TELEGRAM_BOT_TOKEN: " TG_TOKEN; echo
    read -rsp "  CLAUDE_API_KEY (leave empty to skip): " CLAUDE_KEY; echo
    read -rsp "  GITHUB_TOKEN (leave empty to skip): " GH_TOKEN; echo

    cat > "$ENV_FILE" <<EOF
TELEGRAM_BOT_TOKEN=$TG_TOKEN
CLAUDE_API_KEY=$CLAUDE_KEY
GITHUB_TOKEN=$GH_TOKEN
LOG_LEVEL=INFO
HOST=0.0.0.0
PORT=8080
DATABASE_PATH=$APP_HOME/data/orca_memory.db
DOWNLOAD_DIR=$APP_HOME/downloads
EOF
    chown "$APP_USER:$APP_USER" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
  fi
fi

# ---------- 6. systemd service ----------
log "🛠️  Installing systemd service: $SERVICE_NAME..."
cat > /etc/systemd/system/$SERVICE_NAME.service <<EOF
[Unit]
Description=Orca Agent (Telegram + Claude)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_HOME
EnvironmentFile=$ENV_FILE
ExecStart=$APP_HOME/venv/bin/python $APP_HOME/run_final_bot.py
Restart=always
RestartSec=10
StandardOutput=append:$LOG_DIR/orca.log
StandardError=append:$LOG_DIR/orca.err
KillMode=process
TimeoutStopSec=15

# Hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$APP_HOME $LOG_DIR
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictNamespaces=true
RestrictRealtime=true
LockPersonality=true
MemoryDenyWriteExecute=true

[Install]
WantedBy=multi-user.target
EOF

# ---------- 7. Manage helper ----------
cat > /usr/local/bin/orca <<'EOS'
#!/usr/bin/env bash
# Quick manage: orca {start|stop|restart|status|logs|err|tail|env|update}
set -e
SVC=orca-agent
HOME=/opt/orca-agent
LOG=/var/log/orca-agent
case "${1:-}" in
  start)    sudo systemctl start "$SVC" ;;
  stop)     sudo systemctl stop  "$SVC" ;;
  restart)  sudo systemctl restart "$SVC" ;;
  status)   sudo systemctl status "$SVC" --no-pager ;;
  logs)     sudo journalctl -u "$SVC" -n 100 --no-pager ;;
  tail)     sudo tail -f "$LOG/orca.log" ;;
  err)      sudo tail -n 100 "$LOG/orca.err" ;;
  env)      sudo cat "$HOME/.env" ;;
  update)   sudo -u orca bash -c "cd $HOME && git pull && venv/bin/pip install -r requirements.txt" && sudo systemctl restart "$SVC" ;;
  *) echo "Usage: orca {start|stop|restart|status|logs|tail|err|env|update}"; exit 1;;
esac
EOS
chmod +x /usr/local/bin/orca

# ---------- 8. Start service ----------
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"
sleep 2

# ---------- 9. Firewall ----------
log "🔒 Configuring ufw (allow 22 only)..."
ufw --force reset >/dev/null
ufw default deny incoming >/dev/null
ufw default allow outgoing  >/dev/null
ufw allow 22/tcp >/dev/null
# If you later expose the FastAPI: ufw allow 8080/tcp
ufw --force enable >/dev/null

# ---------- 10. fail2ban ----------
log "🛡️  Enabling fail2ban (sshd)..."
cat > /etc/fail2ban/jail.local <<'EOF'
[sshd]
enabled = true
port    = ssh
filter  = sshd
logpath = %(sshd_log)s
maxretry = 5
bantime  = 3600
EOF
systemctl enable --now fail2ban

# ---------- 11. Status ----------
PUBLIC_IP="$(curl -s --max-time 5 https://ifconfig.me || echo 'unknown')"

cat <<EOF

================================================================
  🦅 ORCA AGENT DEPLOYED
================================================================
  Public IP     : $PUBLIC_IP
  App directory : $APP_HOME
  Service       : $SERVICE_NAME (systemd)
  Logs (stdout) : $LOG_DIR/orca.log
  Logs (stderr) : $LOG_DIR/orca.err
  Env file      : $ENV_FILE (chmod 600)
  Manage with   : orca {start|stop|restart|status|logs|tail|err|env|update}

  Service status:
EOF
systemctl is-active "$SERVICE_NAME" >/dev/null && echo "    ✅ $SERVICE_NAME is RUNNING" || echo "    ❌ $SERVICE_NAME is NOT running"
echo ""
echo "  Last 10 log lines:"
sudo -u "$APP_USER" tail -n 10 "$LOG_DIR/orca.log" 2>/dev/null | sed 's/^/    /' || true
echo "================================================================"

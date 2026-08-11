#!/usr/bin/env bash
# ===========================================
# Lina's Laser AI Bot - Deployment Script
# ===========================================
# Run with: bash deploy.sh (or: bash /opt/linasbot/deploy.sh)
# ===========================================

set -e

REPO_ROOT="/opt/linasbot"
CANONICAL_SUBDIR="$REPO_ROOT/linaslaserbot-2.7.22"
APP_DIR="$REPO_ROOT"
if [ -f "$CANONICAL_SUBDIR/main.py" ]; then
  APP_DIR="$CANONICAL_SUBDIR"
fi

SERVICE_NAME="linasbot"
PYTHON_CMD="python3"
command -v python3.11 &>/dev/null && PYTHON_CMD="python3.11"
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

# Must run as root
if [ "$(id -u)" -ne 0 ]; then
    echo -e "${RED}Please run as root (use sudo)${NC}"
    exit 1
fi

cd "$REPO_ROOT" || { echo -e "${RED}Error: $REPO_ROOT not found${NC}"; exit 1; }

echo -e "${BLUE}==========================================${NC}"
echo -e "${BLUE}  Lina's Laser AI Bot - Deployment${NC}"
echo -e "${BLUE}==========================================${NC}"
echo ""
echo -e "Using app directory: ${YELLOW}$APP_DIR${NC}"
echo ""

# Step 1: System dependencies (skip if already present – apt mirrors can be flaky)
echo -e "${YELLOW}[1/8] Installing system dependencies...${NC}"
DEPS_NEEDED=()
command -v python3 &>/dev/null || DEPS_NEEDED+=(python3)
command -v ffmpeg &>/dev/null || DEPS_NEEDED+=(ffmpeg)
command -v node &>/dev/null || command -v nodejs &>/dev/null || DEPS_NEEDED+=(nodejs)
command -v npm &>/dev/null || DEPS_NEEDED+=(npm)
command -v curl &>/dev/null || DEPS_NEEDED+=(curl)
# Only check venv/pip if python3 exists
if command -v python3 &>/dev/null; then
  python3 -c "import venv" 2>/dev/null || DEPS_NEEDED+=(python3-venv)
  python3 -c "import pip" 2>/dev/null || DEPS_NEEDED+=(python3-pip)
fi

if [ ${#DEPS_NEEDED[@]} -gt 0 ]; then
  if apt update -qq 2>/dev/null && apt install -y "${DEPS_NEEDED[@]}" 2>/dev/null; then
    echo -e "${GREEN}Installed: ${DEPS_NEEDED[*]}${NC}"
  else
    echo -e "${RED}apt failed (mirror/repo issues). Required: ${DEPS_NEEDED[*]}${NC}"
    echo -e "${YELLOW}SSH to server, fix apt sources (switch to archive.ubuntu.com if mirrors.digitalocean.com fails), then re-run.${NC}"
    exit 1
  fi
else
  echo -e "${GREEN}All dependencies already installed.${NC}"
fi
echo ""

# Step 2: Validate application directory
echo -e "${YELLOW}[2/8] Checking application directory...${NC}"
if [ ! -f "$APP_DIR/main.py" ]; then
    echo -e "${RED}Error: main.py not found at $APP_DIR${NC}"
    exit 1
fi
echo "Application files OK."
echo -e "${GREEN}Done!${NC}"
echo ""

# Step 3: Set up Python virtual environment
echo -e "${YELLOW}[3/8] Setting up Python virtual environment...${NC}"
cd "$APP_DIR"
rm -rf venv
$PYTHON_CMD -m venv venv
source venv/bin/activate
echo -e "${GREEN}Done!${NC}"
echo ""

# Step 4: Install Python dependencies
echo -e "${YELLOW}[4/8] Installing Python dependencies...${NC}"
pip install --upgrade pip
pip install -r requirements.txt
echo -e "${GREEN}Done!${NC}"
echo ""

# Step 5: Build dashboard + bump deploy version
echo -e "${YELLOW}[5/8] Building dashboard...${NC}"
mkdir -p "$APP_DIR/data"
VERSION_FILE="$APP_DIR/data/.deploy_version"
CURRENT_VERSION=""
if [ -f "$VERSION_FILE" ]; then
  CURRENT_VERSION="$(sed -n '1p' "$VERSION_FILE" | tr -cd '0-9')"
fi
if [ -z "$CURRENT_VERSION" ]; then
  CURRENT_VERSION=0
fi
DEPLOY_VERSION=$((CURRENT_VERSION + 1))
echo "$DEPLOY_VERSION" > "$VERSION_FILE"
DEPLOY_COMMIT="$(cd "$REPO_ROOT" && git rev-parse --short HEAD 2>/dev/null || echo unknown)"

DASH_DIR="$APP_DIR/dashboard"
if [ -f "$DASH_DIR/package.json" ]; then
  cd "$DASH_DIR"
  # Vite 8 / rolldown native bindings require Node >= 22.19 (CI pin). Node 20 fails optional deps.
  NODE_MAJOR="$(node -v 2>/dev/null | sed 's/^v//' | cut -d. -f1 || echo 0)"
  if [ "${NODE_MAJOR:-0}" -lt 22 ]; then
    echo "Node $(node -v 2>/dev/null || echo missing) too old for Vite dashboard build; installing Node 22..."
    if command -v apt-get >/dev/null 2>&1; then
      curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
      apt-get install -y nodejs
    else
      echo -e "${RED}Cannot upgrade Node automatically; install Node >= 22.19 and re-run.${NC}"
      exit 1
    fi
  fi
  echo "Dashboard build using Node $(node -v) / npm $(npm -v)"
  # Clean install so platform-specific optional bindings (rolldown) are present.
  rm -rf node_modules
  if [ -f package-lock.json ]; then
    npm ci --include=optional
  else
    npm install --include=optional --legacy-peer-deps
  fi
  CI=false \
    REACT_APP_DEPLOY_VERSION="$DEPLOY_VERSION" \
    REACT_APP_DEPLOY_COMMIT="$DEPLOY_COMMIT" \
    VITE_DEPLOY_VERSION="$DEPLOY_VERSION" \
    VITE_DEPLOY_COMMIT="$DEPLOY_COMMIT" \
    npm run build
  cd "$APP_DIR"
  # Compatibility bridge: if an external web server serves /opt/linasbot/dashboard/build,
  # mirror the canonical build there so UI stays in sync.
  if [ "$APP_DIR" != "$REPO_ROOT" ] && [ -d "$APP_DIR/dashboard/build" ]; then
    mkdir -p "$REPO_ROOT/dashboard"
    rm -rf "$REPO_ROOT/dashboard/build"
    cp -r "$APP_DIR/dashboard/build" "$REPO_ROOT/dashboard/build"
  fi
  echo -e "${GREEN}Dashboard built successfully!${NC}"
  echo "Dashboard version: v$DEPLOY_VERSION ($DEPLOY_COMMIT)"
else
  echo -e "${YELLOW}Warning: dashboard/package.json not found, skipping dashboard build.${NC}"
fi
echo ""

# Step 5b: Nginx config (proxy /api to backend for login, etc.)
echo -e "${YELLOW}[5b/8] Nginx config for /api proxy...${NC}"
if [ -f "$REPO_ROOT/deploy/nginx-linasaibot.conf" ]; then
  apt install -y nginx 2>/dev/null || true
  if command -v nginx >/dev/null 2>&1; then
    install -o root -g root -m 0644 \
      "$REPO_ROOT/deploy/nginx-privacy-log.conf" \
      /etc/nginx/conf.d/linasbot-privacy-log.conf
    cp "$REPO_ROOT/deploy/nginx-linasaibot.conf" /etc/nginx/sites-available/linasaibot
    ln -sf /etc/nginx/sites-available/linasaibot /etc/nginx/sites-enabled/linasaibot 2>/dev/null || true
    # Canonical enabled name is linasaibot. Disable any other enabled vhost that
    # also claims linasaibot.com so nginx never serves two competing server blocks.
    for enabled_vhost in /etc/nginx/sites-enabled/*; do
      [ -e "$enabled_vhost" ] || continue
      base_name="$(basename "$enabled_vhost")"
      if [ "$base_name" = "linasaibot" ]; then
        continue
      fi
      if grep -qE 'server_name[^;]*(^|[[:space:]])(www\.)?linasaibot\.com([[:space:];]|$)' \
        "$enabled_vhost" 2>/dev/null; then
        echo -e "${YELLOW}Disabling duplicate linasaibot.com vhost: ${enabled_vhost}${NC}"
        rm -f "$enabled_vhost"
      fi
    done
    TARGET_VHOST_COUNT="$(
      { grep -lE 'server_name[^;]*(^|[[:space:]])(www\.)?linasaibot\.com([[:space:];]|$)' \
        /etc/nginx/sites-enabled/* 2>/dev/null || true; } | wc -l | tr -d '[:space:]'
    )"
    if [ "${TARGET_VHOST_COUNT:-0}" != "1" ]; then
      echo -e "${RED}Expected exactly one enabled linasaibot.com vhost; found ${TARGET_VHOST_COUNT:-0}.${NC}"
      grep -lE 'server_name[^;]*(^|[[:space:]])(www\.)?linasaibot\.com([[:space:];]|$)' \
        /etc/nginx/sites-enabled/* 2>/dev/null || true
      exit 1
    fi
    if nginx -t; then
      systemctl reload nginx 2>/dev/null || service nginx reload 2>/dev/null || true
      echo -e "${GREEN}Nginx config installed. /api -> localhost:8003${NC}"
    else
      echo -e "${RED}Nginx config validation failed; refusing to continue deployment.${NC}"
      exit 1
    fi
  else
    echo -e "${YELLOW}Nginx not installed. Copy deploy/nginx-linasaibot.conf to /etc/nginx/sites-available/ and add /api proxy.${NC}"
  fi
else
  echo -e "${YELLOW}deploy/nginx-linasaibot.conf not found, skipping.${NC}"
fi
echo ""

# Step 6: Verify config and credentials
echo -e "${YELLOW}[6/8] Checking configuration...${NC}"
if [ ! -f "$APP_DIR/.env" ]; then
    if [ "$APP_DIR" != "$REPO_ROOT" ] && [ -f "$REPO_ROOT/.env" ]; then
        cp "$REPO_ROOT/.env" "$APP_DIR/.env"
        echo ".env copied from repo root to canonical app directory"
    elif [ -f "$APP_DIR/.env.example" ]; then
        cp "$APP_DIR/.env.example" "$APP_DIR/.env"
        echo -e "${YELLOW}Created .env from .env.example in $APP_DIR${NC}"
    else
        echo -e "${RED}Error: .env and .env.example not found in $APP_DIR${NC}"
        exit 1
    fi
else
    echo ".env file found"
fi

# Preserve durable CM ops flags (e.g. CM_DISABLE_LINAS_LEGACY_BRIDGE) across dual .env paths.
# Deploy rewrites the systemd unit EnvironmentFile path; this keeps the kill-switch durable.
if [ -f "$REPO_ROOT/scripts/prod_cm_preserve_durable_flags.sh" ]; then
    echo "Preserving durable CM ops flags..."
    bash "$REPO_ROOT/scripts/prod_cm_preserve_durable_flags.sh" "$APP_DIR"
else
    echo -e "${YELLOW}Warning: prod_cm_preserve_durable_flags.sh missing; bridge-disable may not survive dual-.env deploys${NC}"
fi

# Binding Sol/Terra model policy env (must match code; startup fails on conflicting overrides).
if [ -f "$REPO_ROOT/scripts/prod_upsert_model_routing_env.py" ]; then
    echo "Applying Sol/Terra model-routing policy env (no service restart yet)..."
    export CM_PRESERVE_APP_DIR="$APP_DIR"
    export LINASBOT_DATA_ROOT="${LINASBOT_DATA_ROOT:-/opt/linasbot_data}"
    export PYTHONPATH="${APP_DIR}${PYTHONPATH:+:$PYTHONPATH}"
    MODEL_PY="$APP_DIR/venv/bin/python"
    if [ ! -x "$MODEL_PY" ]; then
        MODEL_PY="python3"
    fi
    "$MODEL_PY" "$REPO_ROOT/scripts/prod_upsert_model_routing_env.py"
else
    echo -e "${YELLOW}Warning: prod_upsert_model_routing_env.py missing; model env may conflict at startup${NC}"
fi

if [ ! -f "$APP_DIR/data/firebase_data.json" ] && [ -f "$REPO_ROOT/data/firebase_data.json" ]; then
    mkdir -p "$APP_DIR/data"
    cp "$REPO_ROOT/data/firebase_data.json" "$APP_DIR/data/firebase_data.json"
    echo "firebase_data.json copied from repo root"
fi
if [ ! -f "$APP_DIR/data/firebase_data.json" ]; then
    echo -e "${YELLOW}Warning: Firebase credentials not found at $APP_DIR/data/firebase_data.json${NC}"
fi
echo -e "${GREEN}Done!${NC}"
echo ""

# Step 7: Create systemd services (API + optional durable workers)
echo -e "${YELLOW}[7/9] Creating systemd services...${NC}"
cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=Linas Laser AI Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/venv/bin/python main.py
Restart=always
RestartSec=10
StandardOutput=append:/var/log/${SERVICE_NAME}.log
StandardError=append:/var/log/${SERVICE_NAME}.error.log
EnvironmentFile=-${APP_DIR}/.env
Environment=PYTHONUNBUFFERED=1
Environment=PATH=${APP_DIR}/venv/bin:/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=multi-user.target
EOF

# Worker template — queues: high_priority, interactive, background, expensive
WORKER_UNIT_SRC="$REPO_ROOT/deploy/systemd/linasbot-worker@.service"
if [ -f "$WORKER_UNIT_SRC" ]; then
  sed "s|__APP_DIR__|${APP_DIR}|g" "$WORKER_UNIT_SRC" > /etc/systemd/system/linasbot-worker@.service
  echo "Installed linasbot-worker@.service template"
else
  echo -e "${YELLOW}Worker unit template missing; skipping worker units${NC}"
fi

# Re-preserve durable CM flags AFTER systemd EnvironmentFile path rewrite.
if [ -f "$REPO_ROOT/scripts/prod_cm_preserve_durable_flags.sh" ]; then
  bash "$REPO_ROOT/scripts/prod_cm_preserve_durable_flags.sh" "$APP_DIR"
fi

systemctl daemon-reload
echo -e "${GREEN}Done!${NC}"
echo ""

# Step 8: Start the API service
echo -e "${YELLOW}[8/9] Starting API service...${NC}"
systemctl enable ${SERVICE_NAME}
# Stop first, wait for port 8003 to be released (avoid "address already in use" race)
systemctl stop ${SERVICE_NAME} 2>/dev/null || true
echo "Waiting for port 8003 to be released..."
for i in $(seq 1 30); do
  if ! ss -tlnp 2>/dev/null | grep -q ':8003 '; then
    echo "Port 8003 is free."
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo -e "${YELLOW}Port 8003 still in use after 30s, forcing kill...${NC}"
    fuser -k 8003/tcp 2>/dev/null || true
    sleep 2
  else
    sleep 1
  fi
done
systemctl start ${SERVICE_NAME}
sleep 3

if systemctl is-active --quiet ${SERVICE_NAME}; then
    echo -e "${GREEN}API service started successfully!${NC}"
else
    echo -e "${RED}Service failed to start. Showing error log:${NC}"
    echo "=== /var/log/${SERVICE_NAME}.error.log ==="
    tail -80 /var/log/${SERVICE_NAME}.error.log 2>/dev/null || echo "(log file empty or missing)"
    echo ""
    echo "=== journalctl ==="
    journalctl -u ${SERVICE_NAME} -n 15 --no-pager
    echo ""
    echo -e "${YELLOW}Running python main.py to capture traceback:${NC}"
    cd ${APP_DIR} && ${APP_DIR}/venv/bin/python main.py 2>&1 || true
    exit 1
fi
echo ""

# Step 9: Durable workers (only when REDIS_URL + LINAS_REQUIRE_REDIS are set)
echo -e "${YELLOW}[9/9] Queue workers + readiness...${NC}"
WORKER_QUEUES=(high_priority interactive background expensive)
DURABLE_QUEUES_ON=0
if grep -Eq '^[[:space:]]*(REDIS_URL|LINAS_REDIS_URL)=' "$APP_DIR/.env" 2>/dev/null \
  && grep -Eq '^[[:space:]]*(LINAS_REQUIRE_REDIS|LINAS_ENABLE_DURABLE_QUEUES)=(1|true|yes|on)' "$APP_DIR/.env" 2>/dev/null; then
  DURABLE_QUEUES_ON=1
fi

if [ "$DURABLE_QUEUES_ON" = "1" ] && [ -f /etc/systemd/system/linasbot-worker@.service ]; then
  for q in "${WORKER_QUEUES[@]}"; do
    systemctl enable "linasbot-worker@${q}.service"
    systemctl restart "linasbot-worker@${q}.service" || systemctl start "linasbot-worker@${q}.service"
  done
  sleep 2
  WORKER_FAIL=0
  for q in "${WORKER_QUEUES[@]}"; do
    if systemctl is-active --quiet "linasbot-worker@${q}.service"; then
      echo -e "${GREEN}Worker active: linasbot-worker@${q}${NC}"
    else
      echo -e "${RED}Worker inactive: linasbot-worker@${q}${NC}"
      journalctl -u "linasbot-worker@${q}.service" -n 20 --no-pager || true
      WORKER_FAIL=1
    fi
  done
  if [ "$WORKER_FAIL" = "1" ]; then
    echo -e "${RED}Critical workers unavailable — failing deploy${NC}"
    exit 1
  fi
  # Queue readiness (no secrets printed)
  if ! curl -fsS "http://127.0.0.1:8003/api/queue/ready" | grep -q '"ok"[[:space:]]*:[[:space:]]*true'; then
    echo -e "${RED}/api/queue/ready failed — failing deploy${NC}"
    curl -sS "http://127.0.0.1:8003/api/queue/ready" || true
    exit 1
  fi
  echo -e "${GREEN}Queue readiness OK${NC}"
else
  echo -e "${YELLOW}Durable queues not activated (set REDIS_URL + LINAS_REQUIRE_REDIS=true to enable workers).${NC}"
  echo -e "${YELLOW}API-only deploy continues; in-process queue remains non-production.${NC}"
fi

# API readiness (boolean checks only) — poll until gunicorn binds (cold start race).
READY_OK=0
for i in $(seq 1 45); do
  if curl -fsS "http://127.0.0.1:8003/api/ready" 2>/dev/null | grep -q '"ok"[[:space:]]*:[[:space:]]*true'; then
    READY_OK=1
    break
  fi
  sleep 1
done
if [ "$READY_OK" != "1" ]; then
  echo -e "${RED}/api/ready failed after wait — failing deploy${NC}"
  curl -sS "http://127.0.0.1:8003/api/ready" || true
  journalctl -u ${SERVICE_NAME} -n 40 --no-pager || true
  exit 1
fi
echo -e "${GREEN}/api/ready OK${NC}"
echo ""

# Final summary
echo -e "${BLUE}==========================================${NC}"
echo -e "${GREEN}  Deployment Complete!${NC}"
echo -e "${BLUE}==========================================${NC}"
echo ""
echo -e "Application directory: ${YELLOW}$APP_DIR${NC}"
echo -e "Dashboard version: ${YELLOW}v$DEPLOY_VERSION${NC}"
echo -e "Service name: ${YELLOW}$SERVICE_NAME${NC}"
echo -e "Log file: ${YELLOW}/var/log/${SERVICE_NAME}.log${NC}"
echo -e "Error log: ${YELLOW}/var/log/${SERVICE_NAME}.error.log${NC}"
echo -e "Workers: ${YELLOW}linasbot-worker@{high_priority,interactive,background,expensive}${NC}"
echo ""
echo -e "${BLUE}Useful commands:${NC}"
echo "  Check status:    systemctl status $SERVICE_NAME"
echo "  Worker status:   systemctl status 'linasbot-worker@*'"
echo "  View logs:       tail -f /var/log/${SERVICE_NAME}.log"
echo "  Restart:         systemctl restart $SERVICE_NAME"
echo "  Stop:            systemctl stop $SERVICE_NAME"
echo ""
echo -e "${BLUE}Bot is running on:${NC} http://$(curl -s ifconfig.me):8003"
echo ""
echo -e "${YELLOW}Smart Messaging is in PREVIEW MODE${NC}"
echo "Messages will queue for approval in the dashboard."
echo ""

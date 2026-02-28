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

# Step 1: System dependencies
echo -e "${YELLOW}[1/8] Installing system dependencies...${NC}"
apt update -qq
apt install -y python3 python3-venv python3-pip ffmpeg curl nodejs npm
echo -e "${GREEN}Done!${NC}"
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
  npm install --legacy-peer-deps 2>/dev/null || npm install
  CI=false REACT_APP_DEPLOY_VERSION="$DEPLOY_VERSION" REACT_APP_DEPLOY_COMMIT="$DEPLOY_COMMIT" npm run build
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

# Step 7: Create systemd service
echo -e "${YELLOW}[7/8] Creating systemd service...${NC}"
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

systemctl daemon-reload
echo -e "${GREEN}Done!${NC}"
echo ""

# Step 8: Start the service
echo -e "${YELLOW}[8/8] Starting the service...${NC}"
systemctl enable ${SERVICE_NAME}
systemctl restart ${SERVICE_NAME}
sleep 3

if systemctl is-active --quiet ${SERVICE_NAME}; then
    echo -e "${GREEN}Service started successfully!${NC}"
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
echo ""
echo -e "${BLUE}Useful commands:${NC}"
echo "  Check status:    systemctl status $SERVICE_NAME"
echo "  View logs:       tail -f /var/log/${SERVICE_NAME}.log"
echo "  Restart:         systemctl restart $SERVICE_NAME"
echo "  Stop:            systemctl stop $SERVICE_NAME"
echo ""
echo -e "${BLUE}Bot is running on:${NC} http://$(curl -s ifconfig.me):8003"
echo ""
echo -e "${YELLOW}Smart Messaging is in PREVIEW MODE${NC}"
echo "Messages will queue for approval in the dashboard."
echo ""

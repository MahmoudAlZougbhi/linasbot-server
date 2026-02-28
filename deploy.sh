#!/usr/bin/env bash
# ===========================================
# Lina's Laser AI Bot - Deployment Script
# ===========================================
# Run with: bash deploy.sh (or: bash /opt/linasbot/deploy.sh)
# ===========================================

set -e

APP_DIR="/opt/linasbot"
SERVICE_NAME="linasbot"
PYTHON_CMD="python3"
command -v python3.11 &>/dev/null && PYTHON_CMD="python3.11"
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

# Must run as root
if [ "$(id -u)" -ne 0 ]; then
    echo -e "${RED}Please run as root (use sudo)${NC}"
    exit 1
fi

# Ensure we're in APP_DIR (cwd can change with sudo)
cd "$APP_DIR" || { echo -e "${RED}Error: $APP_DIR not found${NC}"; exit 1; }

echo -e "${BLUE}==========================================${NC}"
echo -e "${BLUE}  Lina's Laser AI Bot - Deployment${NC}"
echo -e "${BLUE}==========================================${NC}"
echo ""

# Step 1: System dependencies
echo -e "${YELLOW}[1/7] Installing system dependencies...${NC}"
apt update -qq
apt install -y python3 python3-venv python3-pip ffmpeg curl nodejs npm
echo -e "${GREEN}Done!${NC}"
echo ""

# Step 2: Skip copy - git pull already updated files
echo -e "${YELLOW}[2/7] Checking application directory...${NC}"
if [ ! -f "$APP_DIR/main.py" ]; then
    echo -e "${RED}Error: main.py not found. Run 'git pull' in $APP_DIR first.${NC}"
    exit 1
fi
echo "Application files OK (git pull updates code)."
echo -e "${GREEN}Done!${NC}"
echo ""

# Step 3: Set up Python virtual environment
echo -e "${YELLOW}[3/7] Setting up Python virtual environment...${NC}"
cd "$APP_DIR"
rm -rf venv
$PYTHON_CMD -m venv venv
source venv/bin/activate
echo -e "${GREEN}Done!${NC}"
echo ""

# Step 4: Install Python dependencies
echo -e "${YELLOW}[4/7] Installing Python dependencies...${NC}"
pip install --upgrade pip
pip install -r requirements.txt
echo -e "${GREEN}Done!${NC}"
echo ""

# Step 4b: Build dashboard (React)
echo -e "${YELLOW}[4b/7] Building dashboard...${NC}"
DASH_DIR=""
for d in "$APP_DIR/dashboard" "$APP_DIR/linaslaserbot-2.7.22/dashboard"; do
  if [ -f "$d/package.json" ]; then
    DASH_DIR="$d"
    break
  fi
done
if [ -n "$DASH_DIR" ]; then
  cd "$DASH_DIR"
  npm install --legacy-peer-deps 2>/dev/null || npm install
  if npm run build; then
    # If built in linaslaserbot subdir, ensure root dashboard/build exists for main.py
    if [ "$DASH_DIR" = "$APP_DIR/linaslaserbot-2.7.22/dashboard" ] && [ -d "$DASH_DIR/build" ]; then
      mkdir -p "$APP_DIR/dashboard"
      cp -r "$DASH_DIR/build" "$APP_DIR/dashboard/"
    fi
    echo -e "${GREEN}Dashboard built successfully!${NC}"
  else
    echo -e "${YELLOW}⚠️ Dashboard build failed - continuing without new build${NC}"
  fi
  cd "$APP_DIR"
else
  echo "Dashboard package.json not found, skipping build."
fi
echo ""

# Step 5: Verify .env file exists
echo -e "${YELLOW}[5/7] Checking configuration...${NC}"
if [ ! -f "$APP_DIR/.env" ]; then
    echo -e "${RED}Warning: .env file not found!${NC}"
    echo "Creating from .env.example..."
    if [ -f "$APP_DIR/.env.example" ]; then
        cp "$APP_DIR/.env.example" "$APP_DIR/.env"
        echo -e "${YELLOW}Please edit $APP_DIR/.env with your actual credentials${NC}"
    else
        echo -e "${RED}Error: .env.example not found either!${NC}"
        exit 1
    fi
else
    echo ".env file found"
fi

# Check for Firebase credentials
if [ ! -f "$APP_DIR/data/firebase_data.json" ]; then
    echo -e "${YELLOW}Warning: Firebase credentials not found at data/firebase_data.json${NC}"
    echo "Make sure to upload your Firebase service account JSON file"
fi
echo -e "${GREEN}Done!${NC}"
echo ""

# Step 6: Create systemd service
echo -e "${YELLOW}[6/7] Creating systemd service...${NC}"
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

# Load .env (optional: - means don't fail if missing)
EnvironmentFile=-${APP_DIR}/.env
Environment=PYTHONUNBUFFERED=1
Environment=PATH=${APP_DIR}/venv/bin:/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
echo -e "${GREEN}Done!${NC}"
echo ""

# Step 7: Start the service
echo -e "${YELLOW}[7/7] Starting the service...${NC}"
systemctl enable ${SERVICE_NAME}
systemctl restart ${SERVICE_NAME}
sleep 3

# Check status
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

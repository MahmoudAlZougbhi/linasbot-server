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
apt install -y python3 python3-venv python3-pip ffmpeg curl
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
    echo -e "${RED}Service failed to start. Check logs:${NC}"
    journalctl -u ${SERVICE_NAME} -n 30 --no-pager
    echo ""
    echo -e "${YELLOW}Manual debug: cd ${APP_DIR} && source venv/bin/activate && python main.py${NC}"
    echo -e "${YELLOW}See DEPLOY_TROUBLESHOOT.md for full diagnostic steps.${NC}"
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

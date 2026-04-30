#!/bin/bash
# ============================================================
# SmartTrader-AI — Ubuntu Server Setup Script
# Run this once on your server to install everything
# ============================================================

set -e  # Exit on any error

echo ""
echo "============================================================"
echo "  SmartTrader-AI — Server Setup"
echo "============================================================"
echo ""

# ── 1. Update system ─────────────────────────────────────────
echo "[1/6] Updating system..."
sudo apt-get update -qq
sudo apt-get install -y python3 python3-pip python3-venv git -qq

# ── 2. Create app directory ──────────────────────────────────
echo "[2/6] Setting up app directory..."
APP_DIR="/opt/smarttrader"
sudo mkdir -p $APP_DIR
sudo chown $USER:$USER $APP_DIR

# ── 3. Clone repo ────────────────────────────────────────────
echo "[3/6] Cloning repository..."
if [ -d "$APP_DIR/.git" ]; then
    echo "  Repo already exists — pulling latest..."
    cd $APP_DIR && git pull
else
    git clone https://github.com/burhanyanbolu-design/smarttrader-ai.git $APP_DIR
    cd $APP_DIR
fi

# ── 4. Create virtual environment ────────────────────────────
echo "[4/6] Creating Python virtual environment..."
cd $APP_DIR
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "  Dependencies installed."

# ── 5. Create .env file ──────────────────────────────────────
echo "[5/6] Setting up environment..."
if [ ! -f "$APP_DIR/.env" ]; then
    cp $APP_DIR/.env.example $APP_DIR/.env
    echo ""
    echo "  ⚠️  IMPORTANT: Edit your .env file with your API keys:"
    echo "  nano $APP_DIR/.env"
    echo ""
else
    echo "  .env already exists — skipping."
fi

# Create data and logs directories
mkdir -p $APP_DIR/data
mkdir -p $APP_DIR/logs

# ── 6. Install systemd service ───────────────────────────────
echo "[6/6] Installing systemd service..."
sudo cp $APP_DIR/deploy/smarttrader.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable smarttrader

echo ""
echo "============================================================"
echo "  Setup complete!"
echo "============================================================"
echo ""
echo "Next steps:"
echo "  1. Add your API keys:  nano $APP_DIR/.env"
echo "  2. Start the service:  sudo systemctl start smarttrader"
echo "  3. Check status:       sudo systemctl status smarttrader"
echo "  4. View live logs:     sudo journalctl -u smarttrader -f"
echo ""

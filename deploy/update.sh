#!/bin/bash
# Pull latest code and restart service
echo "Pulling latest code..."
cd /opt/smarttrader
git pull
source venv/bin/activate
pip install -r requirements.txt -q
sudo systemctl restart smarttrader
echo "Done! Service restarted."
sudo systemctl status smarttrader

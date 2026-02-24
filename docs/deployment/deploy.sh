#!/bin/bash
# Stock Report - VPS Deployment Script
# Run on VPS: bash /opt/stockreport/docs/deployment/deploy.sh

set -e
PROJECT_DIR=/opt/stockreport
cd "$PROJECT_DIR"

echo "=== Stock Report Deploy ==="

# 1. Pull latest from dev
git fetch origin
git checkout dev
git pull origin dev

# 2. Python venv
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate

# 3. Dependencies
pip install -q -r requirements.txt
playwright install chromium 2>/dev/null || true

# 4. .env (create from example if missing)
if [ ! -f ".env" ]; then
    cp .env.example .env 2>/dev/null || echo "# Add .env manually" > .env
fi

# 5. Restart systemd service
systemctl restart stockreport 2>/dev/null || echo "Run: systemctl start stockreport"

echo "=== Done ==="

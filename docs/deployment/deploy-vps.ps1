# Stock Report - Deploy to VPS via PuTTY plink
# Run from project root: .\docs\deployment\deploy-vps.ps1

$VPS_IP = "212.85.24.158"
$VPS_USER = "root"
$VPS_PASSWORD = "EcoData2025VPS@Secure-Pass123"
$PLINK = "C:\Program Files\PuTTY\plink.exe"
$HOSTKEY = "SHA256:WCIu/MntsW6iVVem37UoYsMM8APL+/MQYe6vtbTmt2g"
$PROJECT_DIR = "/opt/stockreport"

function Run-VPS { param([string]$cmd) & $PLINK -hostkey $HOSTKEY -pw $VPS_PASSWORD "${VPS_USER}@${VPS_IP}" $cmd }

Write-Host "=== Stock Report VPS Deploy ===" -ForegroundColor Cyan

# 1. Create dir, clone or pull
Write-Host "[1/7] Clone/Pull code..." -ForegroundColor Gray
Run-VPS "mkdir -p $PROJECT_DIR"
Run-VPS "cd $PROJECT_DIR && (test -d .git && (git fetch origin && git checkout dev && git pull origin dev) || git clone -b dev https://github.com/vietlod/stockreport.git .)"

# 2. Python venv + deps
Write-Host "[2/7] Python deps..." -ForegroundColor Gray
Run-VPS "cd $PROJECT_DIR && python3 -m venv .venv 2>/dev/null; .venv/bin/pip install -q -r requirements.txt; .venv/bin/playwright install chromium 2>/dev/null"

# 3. .env
Write-Host "[3/7] .env..." -ForegroundColor Gray
Run-VPS "cd $PROJECT_DIR && (test -f .env) || (cp docs/deployment/env.example .env 2>/dev/null || touch .env)"
Run-VPS "cd $PROJECT_DIR && grep -q OAUTH_REDIRECT_URI .env 2>/dev/null || echo 'OAUTH_REDIRECT_URI=https://stockreport.khoviet.com/oauth2callback' >> .env"

# 4. Systemd
Write-Host "[4/7] Systemd service..." -ForegroundColor Gray
Run-VPS "cp $PROJECT_DIR/docs/deployment/stockreport.service /etc/systemd/system/ && systemctl daemon-reload && systemctl enable stockreport && systemctl restart stockreport"

# 5. Nginx HTTP (for certbot)
Write-Host "[5/7] Nginx HTTP..." -ForegroundColor Gray
Run-VPS "cp $PROJECT_DIR/docs/deployment/nginx_stockreport_http.conf /etc/nginx/sites-available/stockreport.khoviet.com && ln -sf /etc/nginx/sites-available/stockreport.khoviet.com /etc/nginx/sites-enabled/ 2>/dev/null; nginx -t && systemctl reload nginx"

# 6. SSL Certbot
Write-Host "[6/7] SSL certbot..." -ForegroundColor Gray
Run-VPS "certbot --nginx -d stockreport.khoviet.com --non-interactive --agree-tos --email admin@khoviet.com"

# 7. Nginx full SSL config
Write-Host "[7/7] Nginx SSL..." -ForegroundColor Gray
Run-VPS "cp $PROJECT_DIR/docs/deployment/nginx_stockreport.conf /etc/nginx/sites-available/stockreport.khoviet.com && nginx -t && systemctl reload nginx"

Write-Host "`n=== Deploy complete ===" -ForegroundColor Green
Write-Host "URL: https://stockreport.khoviet.com" -ForegroundColor Yellow

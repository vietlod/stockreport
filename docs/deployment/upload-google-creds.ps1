# Upload Google OAuth credentials + token to VPS
# Run from project root: .\docs\deployment\upload-google-creds.ps1
# Prerequisite: _google_token.json đã tạo (chạy OAuth flow local trước)
# ── Credentials từ biến môi trường (KHÔNG hardcode) ──
$VPS_IP = $env:VPS_IP
$VPS_USER = $env:VPS_USER ?? "root"
$VPS_PASSWORD = $env:VPS_PASSWORD
$PSCP = "C:\Program Files\PuTTY\pscp.exe"
$PLINK = "C:\Program Files\PuTTY\plink.exe"
$HOSTKEY = $env:VPS_HOSTKEY ?? "ssh-ed25519 255 SHA256:wv5FF9UZRKTipXip0cFxvz9Xl2FLIZBfLiDgTaVuop8"
$PROJECT_DIR = "/opt/stockreport"

# Validate
if (-not $VPS_IP -or -not $VPS_PASSWORD) {
    Write-Host "ERROR: Set env vars VPS_IP, VPS_PASSWORD first" -ForegroundColor Red
    exit 1
}

$credFile = "google_oauth_credentials.json"
$tokenFile = "_google_token.json"

if (-not (Test-Path $credFile)) {
    Write-Host "ERROR: $credFile not found in current directory" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $tokenFile)) {
    Write-Host "ERROR: $tokenFile not found. Run OAuth flow first:" -ForegroundColor Red
    Write-Host "  python -c `"from google_sync import _get_credentials; _get_credentials()``"" -ForegroundColor Yellow
    Write-Host "  (Complete consent in browser, then re-run this script)" -ForegroundColor Yellow
    exit 1
}

Write-Host "Uploading $credFile and $tokenFile to VPS..." -ForegroundColor Cyan
& $PSCP -hostkey $HOSTKEY -pw $VPS_PASSWORD "$credFile","$tokenFile" "${VPS_USER}@${VPS_IP}:${PROJECT_DIR}/"

if ($LASTEXITCODE -eq 0) {
    Write-Host "Upload OK. Restarting stockreport service..." -ForegroundColor Gray
    & $PLINK -hostkey $HOSTKEY -pw $VPS_PASSWORD "${VPS_USER}@${VPS_IP}" "systemctl restart stockreport"
    Write-Host "Done." -ForegroundColor Green
} else {
    Write-Host "Upload failed." -ForegroundColor Red
    exit 1
}

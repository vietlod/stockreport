# Upload Google OAuth credentials + token to VPS
# Run from project root: .\docs\deployment\upload-google-creds.ps1
# Prerequisite: _google_token.json đã tạo (chạy OAuth flow local trước)

$VPS_IP = "212.85.24.158"
$VPS_USER = "root"
$VPS_PASSWORD = "EcoData2025VPS@Secure-Pass123"
$PSCP = "C:\Program Files\PuTTY\pscp.exe"
$HOSTKEY = "SHA256:WCIu/MntsW6iVVem37UoYsMM8APL+/MQYe6vtbTmt2g"
$PROJECT_DIR = "/opt/stockreport"

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
    $PLINK = "C:\Program Files\PuTTY\plink.exe"
    & $PLINK -hostkey $HOSTKEY -pw $VPS_PASSWORD "${VPS_USER}@${VPS_IP}" "systemctl restart stockreport"
    Write-Host "Done." -ForegroundColor Green
} else {
    Write-Host "Upload failed." -ForegroundColor Red
    exit 1
}

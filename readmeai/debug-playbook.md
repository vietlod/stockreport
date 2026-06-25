# Debug Playbook — Troubleshooting & Diagnostics

This document outlines typical diagnostic workflows and solutions for known failure states in the Stock Report application.

---

## 1. Playwright Browser Crashes ("Page crashed" / Target Closed)
- **Symptom:** Logs show `playwright.errors.Error: Page crashed` or browser freezes during CafeF scrapers.
- **Cause:** Chromium headless accumulates massive memory footprints when loading hundreds of financial pages.
- **Resolution:**
  - Check `.env` `BROWSER_RESTART_INTERVAL` (default is 50). Ensure the browser restarts periodically.
  - Verify playwright chromium dependencies are installed on the VPS host:
    ```bash
    /opt/stockreport/.venv/bin/playwright install --with-deps chromium
    ```

---

## 2. Google OAuth Sync Failures
- **Symptom:** Bấm **Sync Drive** redirect về báo lỗi `redirect_uri_mismatch` hoặc quay về trả lỗi `no_code`.
- **Diagnostics:**
  1. Open `https://stockreport.tnsai.vn/api/oauth2/debug` to check current client ID and redirect URI parameters.
  2. Verify they match what is declared in `/opt/stockreport/google_oauth_credentials.json` and the Google Cloud Console.
  3. Clear current token cache to trigger fresh consent:
    ```bash
    rm -f /opt/stockreport/_google_token.json
    systemctl restart stockreport
    ```

---

## 3. Hải Quan Download SSL Errors
- **Symptom:** Hải Quan statistics fail with `SSLError: [SSL: CERTIFICATE_VERIFY_FAILED]`.
- **Cause:** The customs website (`files.customs.gov.vn`) frequently runs expired or self-signed certificates.
- **Resolution:** The scraper defaults to `verify=False` with `urllib3.disable_warnings()`. Ensure these configurations are active in `haiquan_scraper.py` and are not overridden.

---

## 4. Process Status & Port Conflicts
- **Symptom:** Service `stockreport` fails to start.
- **Diagnostics:**
  1. Check systemd unit logs:
     ```bash
     journalctl -u stockreport -n 100 --no-pager
     ```
  2. Verify port `8002` is not occupied:
     ```bash
     netstat -tulpn | grep 8002
     ```
  3. If port is bound by a ghost process, kill it:
     ```bash
     kill -9 $(lsof -t -i:8002)
     ```

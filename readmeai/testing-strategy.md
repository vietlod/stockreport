# Testing Strategy — Verification & Quality Assurance

This document details testing strategies, script targets, and verification procedures for Stock Report backend APIs and scraper engines.

---

## 1. Automated Scripts

The repository contains standalone python test scripts designed for verification:

### A. API Endpoints Check
- **Script:** `_test_api.py`
- **Purpose:** Asserts basic backend routing responds successfully (HTTP 200) for stock tickers listing and stats.
- **Execution:**
  ```bash
  .venv/bin/python _test_api.py
  ```

### B. Parser Verification
- **Script:** `_test_parse.py` (CafeF) & `_test_haiquan_parse.py` (Hải Quan)
- **Purpose:** Verifies HTML/Excel selectors correctly extract ticker fields, date tags, and statistics numbers without breaking layout patterns.
- **Execution:**
  ```bash
  .venv/bin/python _test_parse.py
  .venv/bin/python _test_haiquan_parse.py
  ```

### C. Google Drive Integration Test
- **API Endpoint:** `/api/gdrive/test`
- **Purpose:** Attempts to upload a dummy file to verify OAuth scopes and write permission in the target Drive folder.
- **Validation:** Open `https://stockreport.tnsai.vn/api/gdrive/test` in browser (requires admin login) to check output results.

---

## 2. Manual Verification Checklist (Deployment verification)

Before signing off a release, execute these verification steps:
1. **SSL Verification:** Check that `https://stockreport.tnsai.vn` loads securely with a valid lock icon.
2. **WebSocket connection:** Open the browser console and check that connection is established to `wss://stockreport.tnsai.vn/ws/progress` with no connection rejects (400 Bad Request).
3. **Google Auth Sync flow:** Trigger a dry run of "Sync Drive" and ensure it completes or returns a valid token check.
4. **Scraper dry-run:** Test a single ticker download (e.g. `STOCK_CODE=ACB python cafef_scraper.py` or through the UI) to ensure Playwright launches and downloads a PDF successfully.

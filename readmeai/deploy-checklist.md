# Deploy Checklist — VPS Production Release Steps

This document outlines the step-by-step verification checklist for deploying new updates of the Stock Report application to the production VPS.

---

## 1. Pre-Deployment Checks
- [ ] Staged code has been tested locally and contains no syntax errors.
- [ ] No database schema additions or breaking API structural shifts are introduced without a fallback.
- [ ] Domain callback origins are authorized in the Google developer console.

---

## 2. Deployment Sequence

### Step 1: Pull Code & Check Deps
- [ ] Log into the VPS via SSH.
- [ ] Navigate to the project root: `cd /opt/stockreport`.
- [ ] Fetch and pull latest dev commits: `git fetch origin && git checkout dev && git pull origin dev`.
- [ ] Refresh Python virtual environment dependencies: `.venv/bin/pip install -r requirements.txt`.
- [ ] Verify playwright chromium binaries are installed: `.venv/bin/playwright install chromium`.

### Step 2: Nginx Config & Certbot (If Domain changes)
- [ ] Copy the HTTP Nginx config: `cp docs/deployment/nginx_stockreport_http.conf /etc/nginx/sites-available/stockreport.tnsai.vn`.
- [ ] Enable the site: `ln -sf /etc/nginx/sites-available/stockreport.tnsai.vn /etc/nginx/sites-enabled/`.
- [ ] Verify syntax and reload Nginx: `nginx -t && systemctl reload nginx`.
- [ ] Run Certbot to generate/renew the SSL certificate:
  ```bash
  certbot --nginx -d stockreport.tnsai.vn --non-interactive --agree-tos --email admin@tnsai.vn
  ```
- [ ] Copy the final SSL Nginx config: `cp docs/deployment/nginx_stockreport.conf /etc/nginx/sites-available/stockreport.tnsai.vn`.
- [ ] Verify syntax and reload Nginx again: `nginx -t && systemctl reload nginx`.
- [ ] Remove old Nginx config files: `rm -f /etc/nginx/sites-available/stockreport.tnsai.tech /etc/nginx/sites-enabled/stockreport.tnsai.tech`.

### Step 3: Restart Services & Check Logs
- [ ] Restart the backend process: `systemctl restart stockreport`.
- [ ] Verify process is running: `systemctl status stockreport`.
- [ ] Check startup logs for errors: `journalctl -u stockreport -n 50 --no-pager`.

---

## 3. Post-Deployment Verification
- [ ] Load the frontend UI in a private browser window: `https://stockreport.tnsai.vn`.
- [ ] Check favicon is displayed and Open Graph image tags are active.
- [ ] Test the Google login flow.
- [ ] Trigger `/api/gdrive/test` to verify Drive sync integration permissions.

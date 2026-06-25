# Build Runbook — Local Development & Execution Setup

This document provides step-by-step instructions to set up the local environment, install dependencies, and run the Stock Report scraper.

---

## 1. System Requirements
- Python 3.12+
- Node.js (Only if building frontend assets; not required for vanilla web UI)
- Google Chrome / Chromium dependencies (required for Playwright)

---

## 2. Local Environment Setup

### Step 1: Clone Repository & Create venv
```bash
git clone https://github.com/vietlod/stockreport.git
cd stockreport
python3 -m venv .venv
```

### Step 2: Install Python Dependencies
```bash
source .venv/bin/activate  # On Windows: .\.venv\Scripts\activate
pip install -r requirements.txt
```

### Step 3: Install Playwright Chromium Browser
Install the Chromium browser engine and system dependencies:
```bash
playwright install chromium
# On Linux host (Ubuntu):
# playwright install-deps chromium
```

---

## 3. Configuration & Startup

### Step 1: Initialize `.env`
Create a `.env` file in the root directory by copying the example template:
```bash
cp docs/deployment/env.example .env
```
Open `.env` and configure key variables (`JWT_SECRET`, folder IDs, redirection URI).

### Step 2: Run the Web Server
Launch the FastAPI development server:
```bash
python server.py
# Server will start on http://localhost:8000
```

### Step 3: Command Line Scraper Operations
To run the scrapers directly from the command line (CLI mode):
```bash
# Scrape all tickers (up to MAX_PAGES)
python cafef_scraper.py

# Scrape a specific ticker (e.g. FPT)
STOCK_CODE=FPT python cafef_scraper.py

# Run in headful mode (visual debugging)
HEADLESS=false python cafef_scraper.py
```

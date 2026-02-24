"""
Google Drive & Sheets Integration
=================================
Upload PDFs to Google Drive, sync metadata to Google Sheets.

Supports:
  - Service Account (service_account.json): no browser, share Drive folder with client_email
  - OAuth2 (web/installed): one-time browser consent, token saved locally

Usage:
    from google_sync import GoogleDriveSync, GoogleSheetSync
    
    drive = GoogleDriveSync()
    drive.upload_all()
    
    sheet = GoogleSheetSync()  
    sheet.sync()
"""

import os
import json
import sqlite3
import logging
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("google_sync")

# ── Config ──────────────────────────────────────────────────────────────────
CREDENTIALS_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_KEY", "./google_oauth_credentials.json")
DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
SHEET_FOLDER_ID = os.getenv("GOOGLE_SHEET_FOLDER_ID", "")
PDF_DIR = Path(os.getenv("PDF_DIR", "./pdf"))
TOKEN_FILE = Path(__file__).parent / "_google_token.json"

# Google API scopes
SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/spreadsheets",
]


def _is_service_account_file(path: str) -> bool:
    """Check if credentials file is Service Account format."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("type") == "service_account"
    except (json.JSONDecodeError, OSError):
        return False


def _get_credentials():
    """Get credentials: Service Account (no consent) or OAuth2 (browser consent).
    
    - Service Account: uses GOOGLE_SERVICE_ACCOUNT_KEY → service_account.json
    - OAuth2: uses client secrets (web/installed) → token saved to _google_token.json
    """
    creds_path = Path(CREDENTIALS_FILE)
    if not creds_path.exists():
        raise FileNotFoundError(
            f"Google credentials file not found: {CREDENTIALS_FILE}\n"
            f"Set GOOGLE_SERVICE_ACCOUNT_KEY in .env (Service Account) or use OAuth client secrets."
        )

    # Service Account: no browser, no token file
    if _is_service_account_file(str(creds_path)):
        from google.oauth2 import service_account
        log.info("🔑 Using Service Account credentials")
        return service_account.Credentials.from_service_account_file(
            str(creds_path), scopes=SCOPES
        )

    # OAuth2 flow (web/installed app)
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            log.info("🔄 Refreshing Google OAuth token...")
            creds.refresh(Request())
        else:
            log.info("🔑 Opening browser for Google OAuth consent...")
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, SCOPES,
                redirect_uri="http://localhost:8080"
            )
            creds = flow.run_local_server(port=8080, open_browser=True)

        TOKEN_FILE.write_text(creds.to_json())
        log.info(f"💾 Token saved to {TOKEN_FILE}")

    return creds


# ═══════════════════════════════════════════════════════════════════════════
# Google Drive Sync
# ═══════════════════════════════════════════════════════════════════════════

class GoogleDriveSync:
    """Upload PDFs to Google Drive, mirroring ICB_CODE subdirectory structure."""

    def __init__(self):
        self.creds = _get_credentials()
        self._folder_cache = {}  # {icb_code: folder_id}

    def _service(self):
        from googleapiclient.discovery import build
        return build("drive", "v3", credentials=self.creds)

    def _get_or_create_folder(self, service, name: str, parent_id: str) -> str:
        """Get or create a subfolder under parent_id."""
        if name in self._folder_cache:
            return self._folder_cache[name]

        # Search existing
        query = (
            f"name='{name}' and '{parent_id}' in parents "
            f"and mimeType='application/vnd.google-apps.folder' and trashed=false"
        )
        results = service.files().list(q=query, fields="files(id)").execute()
        files = results.get("files", [])

        if files:
            folder_id = files[0]["id"]
        else:
            # Create new folder
            meta = {
                "name": name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id],
            }
            folder = service.files().create(body=meta, fields="id").execute()
            folder_id = folder["id"]
            log.info(f"  📁 Created Drive folder: {name}")

        self._folder_cache[name] = folder_id
        return folder_id

    def _file_exists(self, service, name: str, parent_id: str) -> bool:
        """Check if file already exists in Drive folder."""
        query = f"name='{name}' and '{parent_id}' in parents and trashed=false"
        results = service.files().list(q=query, fields="files(id)").execute()
        return len(results.get("files", [])) > 0

    def upload_single(self, pdf_path: Path) -> bool:
        """Upload một file PDF lên Drive ngay sau khi tải xong.
        
        Returns: True nếu upload thành công hoặc file đã tồn tại, False nếu lỗi.
        """
        if not DRIVE_FOLDER_ID:
            return False
        try:
            from googleapiclient.http import MediaFileUpload
            service = self._service()
            if pdf_path.parent != PDF_DIR:
                icb_folder = pdf_path.parent.name
                parent_id = self._get_or_create_folder(
                    service, icb_folder, DRIVE_FOLDER_ID
                )
            else:
                parent_id = DRIVE_FOLDER_ID
            filename = pdf_path.name
            if self._file_exists(service, filename, parent_id):
                return True
            media = MediaFileUpload(
                str(pdf_path), mimetype="application/pdf", resumable=True
            )
            service.files().create(
                body={"name": filename, "parents": [parent_id]},
                media_body=media, fields="id"
            ).execute()
            log.info(f"  ☁ [{filename}] → Drive")
            return True
        except Exception as e:
            log.warning(f"  ⚠ Drive upload failed for {pdf_path.name}: {e}")
            return False

    def upload_all(self, progress_callback=None) -> dict:
        """Upload all PDFs from PDF_DIR to Google Drive.
        
        Returns: {"uploaded": int, "skipped": int, "errors": int}
        """
        if not DRIVE_FOLDER_ID:
            raise ValueError("GOOGLE_DRIVE_FOLDER_ID not configured in .env")

        from googleapiclient.http import MediaFileUpload

        service = self._service()
        stats = {"uploaded": 0, "skipped": 0, "errors": 0, "total": 0}

        # Collect all PDFs
        pdf_files = sorted(PDF_DIR.rglob("*.pdf"))
        stats["total"] = len(pdf_files)
        log.info(f"📤 Uploading {len(pdf_files)} PDFs to Google Drive...")

        for i, pdf_path in enumerate(pdf_files):
            try:
                # Determine target folder (ICB subdirectory)
                if pdf_path.parent != PDF_DIR:
                    icb_folder = pdf_path.parent.name
                    parent_id = self._get_or_create_folder(
                        service, icb_folder, DRIVE_FOLDER_ID
                    )
                else:
                    parent_id = DRIVE_FOLDER_ID

                filename = pdf_path.name

                # Skip if already exists
                if self._file_exists(service, filename, parent_id):
                    stats["skipped"] += 1
                    continue

                # Upload
                media = MediaFileUpload(
                    str(pdf_path),
                    mimetype="application/pdf",
                    resumable=True,
                )
                file_meta = {
                    "name": filename,
                    "parents": [parent_id],
                }
                service.files().create(
                    body=file_meta, media_body=media, fields="id"
                ).execute()

                stats["uploaded"] += 1
                log.info(f"  ↑ [{i+1}/{len(pdf_files)}] {filename}")

                if progress_callback:
                    progress_callback(i + 1, len(pdf_files), filename)

            except Exception as e:
                stats["errors"] += 1
                log.error(f"  ✖ Error uploading {pdf_path.name}: {e}")

        log.info(
            f"✅ Drive sync done: {stats['uploaded']} uploaded, "
            f"{stats['skipped']} skipped, {stats['errors']} errors"
        )
        return stats


# ═══════════════════════════════════════════════════════════════════════════
# Google Sheets Sync
# ═══════════════════════════════════════════════════════════════════════════

class GoogleSheetSync:
    """Sync download metadata to Google Sheets.
    
    Sheet: "CAFEF"
    Columns: TICKER | TIME | TYPE | EXC | IND | INDEX
    Sorted by: TICKER, then TIME
    """

    SHEET_NAME = "CAFEF"
    HEADERS = ["TICKER", "TIME", "TYPE", "EXC", "IND", "INDEX"]

    def __init__(self):
        self.creds = _get_credentials()

    def _service(self):
        from googleapiclient.discovery import build
        return build("sheets", "v4", credentials=self.creds)

    def _find_or_create_sheet(self, service) -> str:
        """Find existing 'CAFEF' sheet or create one in the target folder."""
        from googleapiclient.discovery import build
        
        drive_service = build("drive", "v3", credentials=self.creds)

        if SHEET_FOLDER_ID:
            # Search in folder
            query = (
                f"name='{self.SHEET_NAME}' and '{SHEET_FOLDER_ID}' in parents "
                f"and mimeType='application/vnd.google-apps.spreadsheet' and trashed=false"
            )
            results = drive_service.files().list(q=query, fields="files(id)").execute()
            files = results.get("files", [])

            if files:
                return files[0]["id"]

        # Create new spreadsheet
        body = {
            "properties": {"title": self.SHEET_NAME},
        }
        if SHEET_FOLDER_ID:
            # Create in specific folder via Drive API
            body_drive = {
                "name": self.SHEET_NAME,
                "mimeType": "application/vnd.google-apps.spreadsheet",
                "parents": [SHEET_FOLDER_ID],
            }
            file = drive_service.files().create(body=body_drive, fields="id").execute()
            sheet_id = file["id"]
        else:
            sheet = service.spreadsheets().create(body=body).execute()
            sheet_id = sheet["spreadsheetId"]

        # Set headers
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range="Sheet1!A1:F1",
            valueInputOption="RAW",
            body={"values": [self.HEADERS]},
        ).execute()

        log.info(f"📊 Created Sheet: {self.SHEET_NAME} (ID: {sheet_id})")
        return sheet_id

    def sync(self) -> dict:
        """Sync all download records to Google Sheet.
        
        Returns: {"rows": int, "sheet_id": str}
        """
        from stock_data import registry as stock_registry
        stock_registry.load()

        service = self._service()
        sheet_id = self._find_or_create_sheet(service)

        # Read download history from SQLite
        db_path = PDF_DIR / "_download_history.db"
        if not db_path.exists():
            return {"rows": 0, "sheet_id": sheet_id, "error": "No download history"}

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT DISTINCT stock_code, quarter_year, report_type, exchange, icb_code "
            "FROM downloads WHERE stock_code != '' "
            "ORDER BY stock_code, quarter_year"
        ).fetchall()
        conn.close()

        # Build sheet data
        data = []
        for r in rows:
            ticker = r["stock_code"]
            indexes = stock_registry.get_indexes(ticker)
            icb_name = stock_registry.get_icb_name(ticker)

            data.append([
                ticker,                                    # TICKER
                r["quarter_year"] or "",                   # TIME
                r["report_type"] or "",                    # TYPE
                r["exchange"] or stock_registry.get_exchange(ticker),  # EXC
                f"[{r['icb_code']}] {icb_name}" if r["icb_code"] else icb_name,  # IND
                ", ".join(indexes) if indexes else "",     # INDEX
            ])

        # Sort by TICKER, TIME
        data.sort(key=lambda x: (x[0], x[1]))

        # Clear existing data and write new
        # First clear
        service.spreadsheets().values().clear(
            spreadsheetId=sheet_id,
            range="Sheet1!A2:F",
        ).execute()

        # Write headers + data
        all_values = [self.HEADERS] + data
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range="Sheet1!A1",
            valueInputOption="RAW",
            body={"values": all_values},
        ).execute()

        log.info(f"✅ Sheet sync done: {len(data)} rows → {self.SHEET_NAME}")
        return {"rows": len(data), "sheet_id": sheet_id}

"""
Google Drive & Sheets Integration
=================================
Upload PDFs to Google Drive, sync metadata to Google Sheets.

OAuth2 only: google_oauth_credentials.json → lần đầu mở browser consent → token lưu _google_token.json

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
OAUTH_CREDENTIALS_FILE = os.getenv("GOOGLE_OAUTH_CREDENTIALS", "./google_oauth_credentials.json")
DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
SHEET_FOLDER_ID = os.getenv("GOOGLE_SHEET_FOLDER_ID", "")
PDF_DIR = Path(os.getenv("PDF_DIR", "./pdf"))
TOKEN_FILE = Path(__file__).parent / "_google_token.json"

# Google API scopes
SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]


def _is_service_account_file(path: str) -> bool:
    """Check if file is Service Account format (reject — we use OAuth only)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("type") == "service_account"
    except (json.JSONDecodeError, OSError):
        return False


def _get_credentials():
    """OAuth2 only. Lần đầu: mở browser consent → token lưu _google_token.json."""
    oauth_path = Path(OAUTH_CREDENTIALS_FILE)
    if not oauth_path.exists():
        raise FileNotFoundError(
            f"Không tìm thấy {OAUTH_CREDENTIALS_FILE}. "
            f"Tạo OAuth client từ Google Cloud Console, tải credentials (web type)."
        )
    if _is_service_account_file(str(oauth_path)):
        raise ValueError(
            f"File {OAUTH_CREDENTIALS_FILE} là Service Account. "
            f"Cần OAuth client credentials (web/installed type)."
        )

    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

    creds = None
    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        except Exception:
            log.warning("🔑 Token file hỏng, sẽ tạo mới")
            TOKEN_FILE.unlink(missing_ok=True)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            log.info("🔄 Refreshing Google OAuth token...")
            creds.refresh(Request())
        else:
            log.info("🔑 Opening browser for Google OAuth consent...")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(oauth_path), SCOPES,
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
        results = service.files().list(
            q=query, fields="files(id)",
            supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute()
        files = results.get("files", [])

        if files:
            folder_id = files[0]["id"]
        else:
            # Create new folder (supportsAllDrives for Shared Drive parent)
            meta = {
                "name": name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id],
            }
            folder = service.files().create(
                body=meta, fields="id",
                supportsAllDrives=True,
            ).execute()
            folder_id = folder["id"]
            log.info(f"  📁 Created Drive folder: {name}")

        self._folder_cache[name] = folder_id
        return folder_id

    def _file_exists(self, service, name: str, parent_id: str) -> bool:
        """Check if file already exists in Drive folder."""
        query = f"name='{name}' and '{parent_id}' in parents and trashed=false"
        results = service.files().list(
            q=query, fields="files(id)",
            supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute()
        return len(results.get("files", [])) > 0

    def _list_existing_files(self, service, parent_id: str) -> dict:
        """Batch list ALL files trong folder → {name: {id, size}}.
        
        1 API call thay vì N calls cho N files.
        """
        result = {}
        page_token = None
        query = f"'{parent_id}' in parents and trashed=false and mimeType!='application/vnd.google-apps.folder'"
        while True:
            resp = service.files().list(
                q=query,
                fields="nextPageToken, files(id, name, size)",
                pageSize=1000,
                pageToken=page_token,
                supportsAllDrives=True, includeItemsFromAllDrives=True,
            ).execute()
            for f in resp.get("files", []):
                result[f["name"]] = {
                    "id": f["id"],
                    "size": int(f.get("size", 0)),
                }
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return result

    def _list_existing_files_recursive(self, service, root_folder_id: str) -> dict:
        """List files trong root + tất cả subfolders.
        
        Returns: {relative_path: {id, size}} — ví dụ: {'ICB123/report.pdf': {...}}
        """
        result = {}
        # Files trực tiếp trong root
        for name, info in self._list_existing_files(service, root_folder_id).items():
            result[name] = info

        # Subfolders
        page_token = None
        query = f"'{root_folder_id}' in parents and trashed=false and mimeType='application/vnd.google-apps.folder'"
        while True:
            resp = service.files().list(
                q=query,
                fields="nextPageToken, files(id, name)",
                pageSize=100,
                pageToken=page_token,
                supportsAllDrives=True, includeItemsFromAllDrives=True,
            ).execute()
            for folder in resp.get("files", []):
                folder_name = folder["name"]
                self._folder_cache[folder_name] = folder["id"]
                sub_files = self._list_existing_files(service, folder["id"])
                for fname, finfo in sub_files.items():
                    result[f"{folder_name}/{fname}"] = finfo
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        return result

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
            local_size = pdf_path.stat().st_size
            use_resumable = local_size > 5 * 1024 * 1024
            media = MediaFileUpload(
                str(pdf_path), mimetype="application/pdf",
                resumable=use_resumable,
            )
            result = service.files().create(
                body={"name": filename, "parents": [parent_id]},
                media_body=media, fields="id,size",
                supportsAllDrives=True,
            ).execute()
            remote_size = int(result.get("size", 0))
            if remote_size != local_size:
                log.warning(f"  ⚠ Size mismatch after upload: {filename} "
                            f"(local={local_size}B, remote={remote_size}B)")
            log.info(f"  ☁ [{filename}] → Drive ({local_size}B)")
            return True
        except Exception as e:
            log.warning(f"  ⚠ Drive upload failed for {pdf_path.name}: {e}")
            return False

    def upload_all(self, progress_callback=None) -> dict:
        """Upload PDFs từ PDF_DIR lên Google Drive.

        Incremental: batch-list files trên Drive 1 lần, so sánh tên + size
        → chỉ upload files mới hoặc bị corrupt (size khác).

        progress_callback(current, total, filename, stats):
            stats bao gồm: uploaded, skipped, errors, total,
                           current_folder, action, error_msg, elapsed_s

        Returns: {"uploaded": int, "skipped": int, "errors": int, "total": int}
        """
        if not DRIVE_FOLDER_ID:
            raise ValueError("GOOGLE_DRIVE_FOLDER_ID not configured in .env")

        from googleapiclient.http import MediaFileUpload
        import time as _time

        service = self._service()
        stats = {"uploaded": 0, "skipped": 0, "errors": 0, "total": 0}

        # Collect all local PDFs
        pdf_files = sorted(PDF_DIR.rglob("*.pdf"))
        stats["total"] = len(pdf_files)
        log.info(f"📤 Scanning {len(pdf_files)} local PDFs...")

        if not pdf_files:
            log.info("📤 No PDF files found to upload")
            return stats

        # ── Batch list existing remote files (1 + subfolder count API calls) ──
        log.info("📋 Listing existing files on Drive (batch)...")
        existing_remote = self._list_existing_files_recursive(service, DRIVE_FOLDER_ID)
        log.info(f"   Found {len(existing_remote)} files already on Drive")

        start_time = _time.time()

        for i, pdf_path in enumerate(pdf_files):
            action = "skip"
            error_msg = ""
            current_folder = ""
            filename = pdf_path.name

            try:
                # Determine relative key and target folder
                if pdf_path.parent != PDF_DIR:
                    icb_folder = pdf_path.parent.name
                    relative_key = f"{icb_folder}/{pdf_path.name}"
                    current_folder = icb_folder
                else:
                    relative_key = pdf_path.name

                local_size = pdf_path.stat().st_size

                # Skip if exists on Drive with matching size
                remote_info = existing_remote.get(relative_key)
                if remote_info and remote_info["size"] == local_size:
                    stats["skipped"] += 1
                    action = "skip"
                else:
                    # Need upload — get or create parent folder
                    if pdf_path.parent != PDF_DIR:
                        parent_id = self._get_or_create_folder(
                            service, icb_folder, DRIVE_FOLDER_ID
                        )
                    else:
                        parent_id = DRIVE_FOLDER_ID

                    # Delete corrupt remote file if size mismatch
                    if remote_info and remote_info["size"] != local_size:
                        try:
                            service.files().delete(
                                fileId=remote_info["id"],
                                supportsAllDrives=True,
                            ).execute()
                            log.info(f"  🗑 Deleted corrupt remote: {relative_key} "
                                     f"(remote={remote_info['size']}B, local={local_size}B)")
                        except Exception:
                            pass  # file may already be gone

                    # Upload — non-resumable cho files nhỏ (< 5MB), resumable cho lớn
                    use_resumable = local_size > 5 * 1024 * 1024
                    media = MediaFileUpload(
                        str(pdf_path),
                        mimetype="application/pdf",
                        resumable=use_resumable,
                    )
                    file_meta = {
                        "name": filename,
                        "parents": [parent_id],
                    }
                    result = service.files().create(
                        body=file_meta, media_body=media, fields="id,size",
                        supportsAllDrives=True,
                    ).execute()

                    stats["uploaded"] += 1
                    action = "upload"
                    log.info(f"  ↑ [{i+1}/{len(pdf_files)}] {filename} "
                             f"({local_size}B → {result.get('id', '?')})")

            except Exception as e:
                stats["errors"] += 1
                action = "error"
                error_msg = str(e)
                log.error(f"  ✖ Error uploading {filename}: {e}")

            # Progress callback — gọi cho MỌI file (upload, skip, error)
            if progress_callback:
                elapsed = _time.time() - start_time
                stats_ext = {
                    **stats,
                    "current_folder": current_folder,
                    "action": action,
                    "error_msg": error_msg,
                    "elapsed_s": round(elapsed, 1),
                }
                progress_callback(i + 1, len(pdf_files), filename, stats_ext)

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
        """Sync download records lên Google Sheet.

        Incremental: tính hash của data → so sánh với hash lưu trên Sheet (G1).
        Nếu hash giống → skip (không có thay đổi).

        Returns: {"rows": int, "sheet_id": str, "skipped": bool}
        """
        from stock_data import registry as stock_registry
        stock_registry.load()

        service = self._service()
        sheet_id = self._find_or_create_sheet(service)

        # Read download history from SQLite
        db_path = PDF_DIR / "_download_history.db"
        if not db_path.exists():
            return {"rows": 0, "sheet_id": sheet_id, "error": "No download history", "skipped": False}

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

        # ── Hash-based change detection ──────────────────────────────
        import hashlib
        data_str = json.dumps(data, ensure_ascii=False, sort_keys=True)
        new_hash = hashlib.md5(data_str.encode("utf-8")).hexdigest()

        # Read stored hash from G1
        try:
            stored = service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range="Sheet1!G1",
            ).execute()
            stored_hash = (stored.get("values", [[]])[0] or [""])[0]
        except Exception:
            stored_hash = ""

        if stored_hash == new_hash:
            log.info(f"⏭ Sheet sync skipped: data unchanged (hash={new_hash[:8]}...)")
            return {"rows": len(data), "sheet_id": sheet_id, "skipped": True}

        # ── Data changed → clear and rewrite ─────────────────────────
        service.spreadsheets().values().clear(
            spreadsheetId=sheet_id,
            range="Sheet1!A2:G",
        ).execute()

        # Write headers (A1:F1) + hash (G1) + data
        header_row = self.HEADERS + [new_hash]
        all_values = [header_row] + data
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range="Sheet1!A1",
            valueInputOption="RAW",
            body={"values": all_values},
        ).execute()

        log.info(f"✅ Sheet sync done: {len(data)} rows → {self.SHEET_NAME} (hash={new_hash[:8]}...)")
        return {"rows": len(data), "sheet_id": sheet_id, "skipped": False}


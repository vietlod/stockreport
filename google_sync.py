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
OAUTH_REDIRECT_URI = os.getenv("OAUTH_REDIRECT_URI", "https://stockreport.khoviet.com/oauth2callback")
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
    """OAuth2. Lấy token từ file hoặc raise nếu cần consent (web flow qua /oauth2callback)."""
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
    from google.auth.transport.requests import Request

    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
            if creds.valid:
                return creds
            if creds.expired and creds.refresh_token:
                log.info("🔄 Refreshing Google OAuth token...")
                creds.refresh(Request())
                TOKEN_FILE.write_text(creds.to_json())
                return creds
        except Exception:
            log.warning("🔑 Token file hỏng, sẽ tạo mới")
            TOKEN_FILE.unlink(missing_ok=True)

    raise ValueError(
        "Chưa có Google OAuth token. Bấm Sync Drive để bắt đầu consent flow."
    )


def get_oauth_authorization_url() -> str:
    """Trả URL để redirect user đến Google consent."""
    from google_auth_oauthlib.flow import Flow

    oauth_path = Path(OAUTH_CREDENTIALS_FILE)
    if not oauth_path.exists():
        raise FileNotFoundError(f"Không tìm thấy {OAUTH_CREDENTIALS_FILE}")
    if _is_service_account_file(str(oauth_path)):
        raise ValueError(f"{OAUTH_CREDENTIALS_FILE} phải là OAuth client (web type)")

    flow = Flow.from_client_secrets_file(
        str(oauth_path), SCOPES,
        redirect_uri=OAUTH_REDIRECT_URI,
    )
    url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        # Không dùng include_granted_scopes — OAuth client dùng chung với app khác (pdf2vid/YouTube)
        # gây lỗi "Scope has changed" khi token trả về nhiều scopes hơn yêu cầu
    )
    return url


def save_oauth_token_from_callback(code: str) -> None:
    """Đổi authorization code lấy token, lưu vào _google_token.json."""
    from google_auth_oauthlib.flow import Flow

    oauth_path = Path(OAUTH_CREDENTIALS_FILE)
    flow = Flow.from_client_secrets_file(
        str(oauth_path), SCOPES,
        redirect_uri=OAUTH_REDIRECT_URI,
    )
    flow.fetch_token(code=code)
    TOKEN_FILE.write_text(flow.credentials.to_json())
    log.info(f"💾 Token saved to {TOKEN_FILE}")


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

    def _find_file_id(self, service, name: str, parent_id: str):
        """Tìm file trên Drive, trả file ID hoặc None."""
        query = f"name='{name}' and '{parent_id}' in parents and trashed=false"
        results = service.files().list(
            q=query, fields="files(id)",
            supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute()
        files = results.get("files", [])
        return files[0]["id"] if files else None

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

    def upload_single(self, pdf_path: Path):
        """Upload một file PDF lên Drive ngay sau khi tải xong.
        
        Returns: Drive file ID (str) nếu thành công/đã tồn tại, None nếu lỗi.
        """
        if not DRIVE_FOLDER_ID:
            return None
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
            existing_id = self._find_file_id(service, filename, parent_id)
            if existing_id:
                return existing_id
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
            log.info(f"  ☁ [{filename}] → Drive ({local_size}B, id={result['id']})")
            return result["id"]
        except Exception as e:
            log.warning(f"  ⚠ Drive upload failed for {pdf_path.name}: {e}")
            return None

    def upload_all(self, progress_callback=None, phase_callback=None) -> dict:
        """Upload PDFs từ PDF_DIR lên Google Drive.

        Incremental: batch-list files trên Drive 1 lần, so sánh tên + size
        → chỉ upload files mới hoặc bị corrupt (size khác).

        progress_callback(current, total, filename, stats):
            stats bao gồm: uploaded, skipped, errors, total,
                           current_folder, action, error_msg, elapsed_s

        phase_callback(phase, detail):
            phase: "scanning" | "listing" | "uploading"
            detail: dict with context info

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
        if phase_callback:
            phase_callback("scanning", {"total_local": len(pdf_files)})

        if not pdf_files:
            log.info("📤 No PDF files found to upload")
            return stats

        # ── Batch list existing remote files (1 + subfolder count API calls) ──
        log.info("📋 Listing existing files on Drive (batch)...")
        if phase_callback:
            phase_callback("listing", {"total_local": len(pdf_files)})
        existing_remote = self._list_existing_files_recursive(service, DRIVE_FOLDER_ID)
        log.info(f"   Found {len(existing_remote)} files already on Drive")
        if phase_callback:
            phase_callback("uploading", {"total_local": len(pdf_files), "total_remote": len(existing_remote)})

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

        # ── Re-scan Drive to get file IDs (for Sheet hyperlinks) ─────
        try:
            final_remote = self._list_existing_files_recursive(service, DRIVE_FOLDER_ID)
        except Exception:
            final_remote = existing_remote  # fallback to pre-upload snapshot

        # ── Mark synced files + populate drive_file_id in SQLite ──────
        all_filenames = [p.name for p in pdf_files]
        if all_filenames:
            try:
                db_path = PDF_DIR / "_download_history.db"
                if db_path.exists():
                    import sqlite3 as _sqlite3
                    conn = _sqlite3.connect(str(db_path))
                    # Build filename → drive_file_id map
                    file_id_map = {}
                    for pdf_path in pdf_files:
                        if pdf_path.parent != PDF_DIR:
                            relative_key = f"{pdf_path.parent.name}/{pdf_path.name}"
                        else:
                            relative_key = pdf_path.name
                        remote_info = final_remote.get(relative_key)
                        if remote_info:
                            file_id_map[pdf_path.name] = remote_info["id"]

                    # Batch update: drive_synced=1 + drive_file_id
                    for fn in all_filenames:
                        drive_id = file_id_map.get(fn, "")
                        conn.execute(
                            "UPDATE downloads SET drive_synced = 1, drive_file_id = ? WHERE filename = ?",
                            (drive_id, fn)
                        )
                    conn.commit()
                    conn.close()
                    log.info(f"📋 Marked {len(all_filenames)} files as drive_synced "
                             f"({len(file_id_map)} with drive_file_id) in DB")
            except Exception as e:
                log.warning(f"⚠ Failed to mark drive_synced: {e}")

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
    SHEET_TAB = "DATA"  # Tab name cố định, không phụ thuộc locale Google Account
    HEADERS = ["TICKER", "TIME", "TYPE", "EXC", "IND", "INDEX", "DATE"]

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
            # Search in folder (supportsAllDrives cho Shared Drive)
            query = (
                f"name='{self.SHEET_NAME}' and '{SHEET_FOLDER_ID}' in parents "
                f"and mimeType='application/vnd.google-apps.spreadsheet' and trashed=false"
            )
            results = drive_service.files().list(
                q=query, fields="files(id)",
                supportsAllDrives=True, includeItemsFromAllDrives=True,
            ).execute()
            files = results.get("files", [])

            if files:
                sheet_id = files[0]["id"]
                # Đảm bảo tab DATA tồn tại (cho sheet cũ tạo trước khi fix)
                self._ensure_data_tab(service, sheet_id)
                return sheet_id

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
            file = drive_service.files().create(
                body=body_drive, fields="id",
                supportsAllDrives=True,
            ).execute()
            sheet_id = file["id"]
        else:
            sheet = service.spreadsheets().create(body=body).execute()
            sheet_id = sheet["spreadsheetId"]

        # Rename tab mặc định (locale-dependent) → tên cố định "DATA"
        self._ensure_data_tab(service, sheet_id)

        # Set headers
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"{self.SHEET_TAB}!A1:G1",
            valueInputOption="RAW",
            body={"values": [self.HEADERS]},
        ).execute()

        log.info(f"📊 Created Sheet: {self.SHEET_NAME} (ID: {sheet_id}), tab: {self.SHEET_TAB}")
        return sheet_id

    def _ensure_data_tab(self, service, sheet_id: str):
        """Đảm bảo tab đầu tiên có tên 'DATA' (không phụ thuộc locale)."""
        try:
            spreadsheet = service.spreadsheets().get(
                spreadsheetId=sheet_id,
                fields="sheets.properties",
            ).execute()
            sheets = spreadsheet.get("sheets", [])
            if not sheets:
                return
            first_tab = sheets[0]["properties"]
            if first_tab["title"] != self.SHEET_TAB:
                log.info(f"  🔄 Renaming tab '{first_tab['title']}' → '{self.SHEET_TAB}'")
                service.spreadsheets().batchUpdate(
                    spreadsheetId=sheet_id,
                    body={"requests": [{
                        "updateSheetProperties": {
                            "properties": {
                                "sheetId": first_tab["sheetId"],
                                "title": self.SHEET_TAB,
                            },
                            "fields": "title",
                        }
                    }]},
                ).execute()
        except Exception as e:
            log.warning(f"  ⚠ Error ensuring DATA tab: {e}")

    def sync(self, progress_callback=None) -> dict:
        """Sync download records lên Google Sheet.

        Incremental: tính hash của data → so sánh với hash lưu trên Sheet (G1).
        Nếu hash giống → skip (không có thay đổi).

        progress_callback(phase, detail):
            phase: "reading_db" | "computing_hash" | "writing_sheet" | "completed"
            detail: dict with rows count, etc.

        Returns: {"rows": int, "sheet_id": str, "skipped": bool}
        """
        if progress_callback:
            progress_callback("reading_db", {})

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
            "SELECT DISTINCT stock_code, quarter_year, report_type, exchange, icb_code, "
            "drive_file_id, downloaded_at "
            "FROM downloads WHERE stock_code != '' "
            "ORDER BY stock_code, quarter_year"
        ).fetchall()
        conn.close()

        if not rows:
            log.warning("⚠ Sheet sync: no download records found in DB")
            return {"rows": 0, "sheet_id": sheet_id, "skipped": False, "error": "No records"}

        # Build sheet data
        data = []
        for r in rows:
            ticker = r["stock_code"]
            indexes = stock_registry.get_indexes(ticker)
            icb_name = stock_registry.get_icb_name(ticker)
            drive_file_id = r["drive_file_id"] or ""
            downloaded_at = r["downloaded_at"] or ""

            # TICKER: hyperlink đến Drive file nếu đã sync
            if drive_file_id:
                ticker_cell = f'=HYPERLINK("https://drive.google.com/file/d/{drive_file_id}/view", "{ticker}")'
            else:
                ticker_cell = ticker

            data.append([
                ticker_cell,                                # TICKER
                r["quarter_year"] or "",                     # TIME
                r["report_type"] or "",                      # TYPE
                r["exchange"] or stock_registry.get_exchange(ticker),  # EXC
                f"[{r['icb_code']}] {icb_name}" if r["icb_code"] else icb_name,  # IND
                ", ".join(indexes) if indexes else "",       # INDEX
                downloaded_at[:10] if downloaded_at else "", # DATE
            ])

        # Sort by TICKER, TIME
        data.sort(key=lambda x: (x[0], x[1]))

        # ── Hash-based change detection ──────────────────────────────
        if progress_callback:
            progress_callback("computing_hash", {"rows": len(data)})

        import hashlib
        data_str = json.dumps(data, ensure_ascii=False, sort_keys=True)
        new_hash = hashlib.md5(data_str.encode("utf-8")).hexdigest()

        # Read stored hash from H1
        try:
            stored = service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range=f"{self.SHEET_TAB}!H1",
            ).execute()
            stored_hash = (stored.get("values", [[]])[0] or [""])[0]
        except Exception:
            stored_hash = ""

        if stored_hash == new_hash:
            log.info(f"⏭ Sheet sync skipped: data unchanged (hash={new_hash[:8]}...)")
            return {"rows": len(data), "sheet_id": sheet_id, "skipped": True}

        # ── Data changed → clear and rewrite ─────────────────────────
        if progress_callback:
            progress_callback("writing_sheet", {"rows": len(data)})

        service.spreadsheets().values().clear(
            spreadsheetId=sheet_id,
            range=f"{self.SHEET_TAB}!A2:H",
        ).execute()

        # Write headers (A1:F1) + hash (G1) + data
        header_row = self.HEADERS + [new_hash]
        all_values = [header_row] + data
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"{self.SHEET_TAB}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": all_values},
        ).execute()

        log.info(f"✅ Sheet sync done: {len(data)} rows → {self.SHEET_NAME} (hash={new_hash[:8]}...)")
        return {"rows": len(data), "sheet_id": sheet_id, "skipped": False}


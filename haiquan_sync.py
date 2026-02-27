"""
Hải Quan — Google Drive Sync
=============================
Upload PDFs từ pdf/haiquan/ lên Google Drive folder riêng.

Module TÁCH BIỆT hoàn toàn với google_sync.py (CafeF).
Reuse credentials (OAuth token) nhưng dùng folder ID riêng.
"""

import logging
import os
import time
from pathlib import Path

log = logging.getLogger("haiquan_sync")

HQ_PDF_DIR = Path(os.getenv("HQ_PDF_DIR", "./pdf/haiquan"))
HQ_DRIVE_FOLDER_ID = os.getenv("HQ_GOOGLE_DRIVE_FOLDER_ID", "")


class HaiQuanDriveSync:
    """Upload Hải Quan PDFs lên Google Drive — flat structure, folder riêng."""

    def __init__(self):
        # Reuse credentials from google_sync
        from google_sync import _get_credentials
        self.creds = _get_credentials()

    def _service(self):
        from googleapiclient.discovery import build
        return build("drive", "v3", credentials=self.creds)

    def _find_file_id(self, service, name: str, parent_id: str):
        """Tìm file trên Drive, trả file ID hoặc None."""
        query = f"name='{name}' and '{parent_id}' in parents and trashed=false"
        results = service.files().list(
            q=query, fields="files(id)",
            supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute()
        files = results.get("files", [])
        return files[0]["id"] if files else None

    def upload_single(self, pdf_path: Path) -> str | None:
        """Upload một file PDF lên Drive ngay sau khi tải xong (real-time sync).

        Returns: Drive file ID (str) nếu thành công/đã tồn tại, None nếu lỗi.
        """
        if not HQ_DRIVE_FOLDER_ID:
            return None
        try:
            from googleapiclient.http import MediaFileUpload
            service = self._service()
            filename = pdf_path.name

            # Check if already exists
            existing_id = self._find_file_id(service, filename, HQ_DRIVE_FOLDER_ID)
            if existing_id:
                return existing_id

            local_size = pdf_path.stat().st_size
            use_resumable = local_size > 5 * 1024 * 1024
            media = MediaFileUpload(
                str(pdf_path), mimetype="application/pdf",
                resumable=use_resumable,
            )
            result = service.files().create(
                body={"name": filename, "parents": [HQ_DRIVE_FOLDER_ID]},
                media_body=media, fields="id,size",
                supportsAllDrives=True,
            ).execute()

            remote_size = int(result.get("size", 0))
            if remote_size != local_size:
                log.warning(f"  ⚠ Size mismatch: {filename} "
                            f"(local={local_size}B, remote={remote_size}B)")
            log.info(f"  ☁ [{filename}] → HQ Drive ({local_size}B, id={result['id']})")
            return result["id"]
        except Exception as e:
            log.warning(f"  ⚠ HQ Drive upload failed for {pdf_path.name}: {e}")
            return None

    def upload_all(self, progress_callback=None, phase_callback=None) -> dict:
        """Upload PDFs từ HQ_PDF_DIR lên Google Drive.

        Incremental: list files trên Drive 1 lần, so sánh tên + size
        → chỉ upload files mới hoặc bị corrupt.

        Returns: {"uploaded": int, "skipped": int, "errors": int, "total": int}
        """
        if not HQ_DRIVE_FOLDER_ID:
            raise ValueError("HQ_GOOGLE_DRIVE_FOLDER_ID not configured in .env")

        from googleapiclient.http import MediaFileUpload

        service = self._service()
        stats = {"uploaded": 0, "skipped": 0, "errors": 0, "total": 0}

        # Collect local PDFs (flat — no subdirs)
        pdf_files = sorted(HQ_PDF_DIR.glob("*.pdf"))
        stats["total"] = len(pdf_files)
        log.info(f"📤 Found {len(pdf_files)} local HQ PDFs")

        if phase_callback:
            phase_callback("scanning", {"total_local": len(pdf_files)})

        if not pdf_files:
            log.info("📤 No HQ PDF files to upload")
            return stats

        # List existing remote files
        log.info("📋 Listing existing HQ files on Drive...")
        if phase_callback:
            phase_callback("listing", {"total_local": len(pdf_files)})

        existing_remote = self._list_existing_files(service, HQ_DRIVE_FOLDER_ID)
        log.info(f"   Found {len(existing_remote)} files on Drive")

        if phase_callback:
            phase_callback("uploading", {
                "total_local": len(pdf_files),
                "total_remote": len(existing_remote),
            })

        start_time = time.time()

        for i, pdf_path in enumerate(pdf_files):
            action = "skip"
            error_msg = ""
            filename = pdf_path.name

            try:
                local_size = pdf_path.stat().st_size

                # Skip if exists on Drive with matching size
                remote_info = existing_remote.get(filename)
                if remote_info and remote_info["size"] == local_size:
                    stats["skipped"] += 1
                    action = "skip"
                else:
                    # Delete corrupt remote if size mismatch
                    if remote_info and remote_info["size"] != local_size:
                        try:
                            service.files().delete(
                                fileId=remote_info["id"],
                                supportsAllDrives=True,
                            ).execute()
                        except Exception:
                            pass

                    # Upload
                    use_resumable = local_size > 5 * 1024 * 1024
                    media = MediaFileUpload(
                        str(pdf_path),
                        mimetype="application/pdf",
                        resumable=use_resumable,
                    )
                    result = service.files().create(
                        body={
                            "name": filename,
                            "parents": [HQ_DRIVE_FOLDER_ID],
                        },
                        media_body=media,
                        fields="id,size",
                        supportsAllDrives=True,
                    ).execute()

                    stats["uploaded"] += 1
                    action = "upload"
                    log.info(
                        f"  ↑ [{i+1}/{len(pdf_files)}] {filename} "
                        f"({local_size}B → {result.get('id', '?')})"
                    )

            except Exception as e:
                stats["errors"] += 1
                action = "error"
                error_msg = str(e)
                log.error(f"  ✖ Error uploading {filename}: {e}")

            if progress_callback:
                elapsed = time.time() - start_time
                progress_callback(i + 1, len(pdf_files), filename, {
                    **stats,
                    "action": action,
                    "error_msg": error_msg,
                    "elapsed_s": elapsed,
                })

        log.info(
            f"✅ HQ Drive sync done: {stats['uploaded']} uploaded, "
            f"{stats['skipped']} skipped, {stats['errors']} errors"
        )

        # ── Re-scan Drive to get file IDs (for Sheet hyperlinks) ─────
        try:
            final_remote = self._list_existing_files(service, HQ_DRIVE_FOLDER_ID)
        except Exception:
            final_remote = existing_remote  # fallback

        # ── Mark synced + populate drive_file_id in SQLite ────────────
        all_filenames = [p.name for p in pdf_files]
        if all_filenames:
            try:
                import sqlite3
                db_path = HQ_PDF_DIR / "_haiquan_history.db"
                if db_path.exists():
                    conn = sqlite3.connect(str(db_path))
                    for fn in all_filenames:
                        remote_info = final_remote.get(fn)
                        drive_id = remote_info["id"] if remote_info else ""
                        conn.execute(
                            "UPDATE haiquan_downloads SET drive_synced = 1, drive_file_id = ? "
                            "WHERE filename = ?",
                            (drive_id, fn)
                        )
                    conn.commit()
                    conn.close()
                    id_count = sum(1 for fn in all_filenames if fn in final_remote)
                    log.info(f"📋 Marked {len(all_filenames)} HQ files as synced "
                             f"({id_count} with drive_file_id)")
            except Exception as e:
                log.warning(f"⚠ Failed to mark HQ drive_synced: {e}")

        return stats

    def _list_existing_files(self, service, folder_id: str) -> dict:
        """List all files in a single Drive folder (flat).

        Returns: {filename: {"id": ..., "size": int}}
        """
        files = {}
        page_token = None

        while True:
            resp = service.files().list(
                q=f"'{folder_id}' in parents and trashed = false",
                fields="nextPageToken, files(id, name, size)",
                pageSize=1000,
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
                pageToken=page_token,
            ).execute()

            for f in resp.get("files", []):
                files[f["name"]] = {
                    "id": f["id"],
                    "size": int(f.get("size", 0)),
                }

            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        return files


# ═══════════════════════════════════════════════════════════════════════════
# Google Sheets Sync — Hải Quan
# ═══════════════════════════════════════════════════════════════════════════

class HaiQuanSheetSync:
    """Sync Hải Quan metadata lên Google Sheets.

    Sheet: "HAI QUAN"
    Tab: "DATA"
    Columns: FILENAME | YEAR | PERIOD | TYPE | CODE | SIZE | DATE
    Sorted by: FILENAME
    """

    SHEET_NAME = "HAI QUAN"
    SHEET_TAB = "DATA"
    HEADERS = ["FILENAME", "YEAR", "PERIOD", "TYPE", "CODE", "SIZE", "DATE"]

    def __init__(self):
        from google_sync import _get_credentials
        self.creds = _get_credentials()

    def _sheets_service(self):
        from googleapiclient.discovery import build
        return build("sheets", "v4", credentials=self.creds)

    def _drive_service(self):
        from googleapiclient.discovery import build
        return build("drive", "v3", credentials=self.creds)

    def _find_or_create_sheet(self, sheets_svc, drive_svc) -> str:
        """Find existing 'HAI QUAN' spreadsheet or create one."""
        from google_sync import SHEET_FOLDER_ID

        if SHEET_FOLDER_ID:
            query = (
                f"name='{self.SHEET_NAME}' and '{SHEET_FOLDER_ID}' in parents "
                f"and mimeType='application/vnd.google-apps.spreadsheet' and trashed=false"
            )
            results = drive_svc.files().list(
                q=query, fields="files(id)",
                supportsAllDrives=True, includeItemsFromAllDrives=True,
            ).execute()
            files = results.get("files", [])

            if files:
                sheet_id = files[0]["id"]
                self._ensure_data_tab(sheets_svc, sheet_id)
                return sheet_id

        # Create new spreadsheet
        if SHEET_FOLDER_ID:
            body = {
                "name": self.SHEET_NAME,
                "mimeType": "application/vnd.google-apps.spreadsheet",
                "parents": [SHEET_FOLDER_ID],
            }
            file = drive_svc.files().create(
                body=body, fields="id", supportsAllDrives=True,
            ).execute()
            sheet_id = file["id"]
        else:
            body = {"properties": {"title": self.SHEET_NAME}}
            sheet = sheets_svc.spreadsheets().create(body=body).execute()
            sheet_id = sheet["spreadsheetId"]

        self._ensure_data_tab(sheets_svc, sheet_id)

        # Set headers
        sheets_svc.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"{self.SHEET_TAB}!A1:G1",
            valueInputOption="RAW",
            body={"values": [self.HEADERS]},
        ).execute()

        log.info(f"📊 Created HQ Sheet: {self.SHEET_NAME} (ID: {sheet_id})")
        return sheet_id

    def _ensure_data_tab(self, service, sheet_id: str):
        """Đảm bảo tab đầu tiên có tên 'DATA'."""
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
        """Sync Hải Quan download records lên Google Sheet.

        Incremental: hash-based change detection.

        Returns: {"rows": int, "sheet_id": str, "skipped": bool}
        """
        import sqlite3
        import json
        import hashlib

        if progress_callback:
            progress_callback("reading_db", {})

        sheets_svc = self._sheets_service()
        drive_svc = self._drive_service()
        sheet_id = self._find_or_create_sheet(sheets_svc, drive_svc)

        # Read download history
        db_path = HQ_PDF_DIR / "_haiquan_history.db"
        if not db_path.exists():
            return {"rows": 0, "sheet_id": sheet_id, "error": "No HQ history DB", "skipped": False}

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT DISTINCT filename, year, period, report_type, report_code, "
            "file_size, drive_file_id, downloaded_at "
            "FROM haiquan_downloads WHERE filename != '' "
            "ORDER BY filename"
        ).fetchall()
        conn.close()

        if not rows:
            log.warning("⚠ HQ Sheet sync: no records found")
            return {"rows": 0, "sheet_id": sheet_id, "skipped": False, "error": "No records"}

        # Build sheet data
        data = []
        for r in rows:
            filename = r["filename"]
            drive_file_id = r["drive_file_id"] or ""
            downloaded_at = r["downloaded_at"] or ""

            # FILENAME: hyperlink → Drive file nếu đã sync
            if drive_file_id:
                filename_cell = (
                    f'=HYPERLINK("https://drive.google.com/file/d/{drive_file_id}/view", '
                    f'"{filename}")'
                )
            else:
                filename_cell = filename

            # Size human-readable
            file_size = r["file_size"] or 0
            if file_size < 1024:
                size_str = f"{file_size} B"
            elif file_size < 1024 * 1024:
                size_str = f"{file_size / 1024:.1f} KB"
            else:
                size_str = f"{file_size / 1024 / 1024:.1f} MB"

            data.append([
                filename_cell,                                 # FILENAME
                str(r["year"] or ""),                           # YEAR
                r["period"] or "",                              # PERIOD
                r["report_type"] or "",                         # TYPE
                r["report_code"] or "",                         # CODE
                size_str,                                      # SIZE
                downloaded_at[:10] if downloaded_at else "",    # DATE
            ])

        data.sort(key=lambda x: x[0])

        # ── Hash-based change detection ─────────────────────────────
        if progress_callback:
            progress_callback("computing_hash", {"rows": len(data)})

        data_str = json.dumps(data, ensure_ascii=False, sort_keys=True)
        new_hash = hashlib.md5(data_str.encode("utf-8")).hexdigest()

        try:
            stored = sheets_svc.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range=f"{self.SHEET_TAB}!H1",
            ).execute()
            stored_hash = (stored.get("values", [[]])[0] or [""])[0]
        except Exception:
            stored_hash = ""

        if stored_hash == new_hash:
            log.info(f"⏭ HQ Sheet sync skipped: unchanged (hash={new_hash[:8]}...)")
            return {"rows": len(data), "sheet_id": sheet_id, "skipped": True}

        # ── Write ────────────────────────────────────────────────────
        if progress_callback:
            progress_callback("writing_sheet", {"rows": len(data)})

        sheets_svc.spreadsheets().values().clear(
            spreadsheetId=sheet_id,
            range=f"{self.SHEET_TAB}!A2:H",
        ).execute()

        header_row = self.HEADERS + [new_hash]
        all_values = [header_row] + data
        sheets_svc.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"{self.SHEET_TAB}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": all_values},
        ).execute()

        log.info(f"✅ HQ Sheet sync done: {len(data)} rows → {self.SHEET_NAME}")
        return {"rows": len(data), "sheet_id": sheet_id, "skipped": False}


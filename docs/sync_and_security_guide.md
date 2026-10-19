# Hướng Dẫn Đồng Bộ & Bảo Mật Triển Khai (Local - Repo - VPS)

Tài liệu này chuẩn hóa mô hình đồng bộ mã nguồn và quy chuẩn bảo mật cho dự án **Stock Report** giữa 3 môi trường: **Local Machine**, **GitHub Repository**, và **Remote VPS**.

---

## 1. Nguyên Tắc & Phân Cấp Môi Trường

```
                      ┌─────────────────────────┐
                      │    GitHub Repository    │
                      │  (vietlod/stockreport)  │
                      └────────────┬────────────┘
                                   │
                    Push / Pull    │    Pull (Fast-forward)
                  (Code & Docs)    │   (Code & Docs)
                                   ▼
┌─────────────────────────┐                 ┌─────────────────────────┐
│     Local Dev (PC)      │                 │       Remote VPS        │
│    (d:\stockreport)     │◄────────────────┤    (31.97.110.12)       │
└─────────────────────────┘  pscp (Configs) └─────────────────────────┘
                                                ★ Source of Truth ★
                                              (Runtime & Credentials)
```

1. **VPS (`/opt/stockreport`) là "Source of Truth" (Nguồn Chân Lý Triển Khai)**:
   - Là nơi lưu giữ cấu hình thực tế đang chạy (`.env`), các token cấp phép Google (`service_account.json`, `google_oauth_credentials.json`), và dịch vụ nền `stockreport.service` (Port 8002).
   - Mọi thay đổi về cấu hình hoặc dữ liệu vận hành phải lấy từ VPS làm căn cứ chuẩn.

2. **GitHub Repository (`dev` branch)**:
   - Lưu trữ lịch sử mã nguồn, tài liệu thiết kế và kịch bản tự động hóa.
   - **Tuyệt đối không lưu trữ bất kỳ file cấu hình chứa secret hay private key nào.**

3. **Local Dev Machine (`d:\stockreport`)**:
   - Môi trường lập trình, kiểm thử và viết kịch bản.
   - Đồng bộ code từ GitHub Repo và đồng bộ các file cấu hình bí mật từ VPS về thông qua kết nối bảo mật (`pscp`).

---

## 2. Ma Trận Tệp Tin & Chính Sách Bảo Mật

| Tệp tin / Tài nguyên | Mục đích | Lưu trữ ở đâu | Trạng thái Git |
| :--- | :--- | :--- | :--- |
| `.env` | Biến môi trường, JWT Secret, Drive Folder ID, Port | VPS + Local | **Bị chặn bởi `.gitignore`** |
| `service_account.json` | Khóa xác thực Google Cloud Service Account (sync Drive/Sheets) | VPS + Local | **Bị chặn bởi `.gitignore`** |
| `google_oauth_credentials.json` | Google OAuth 2.0 Web Client credentials | VPS + Local | **Bị chặn bởi `.gitignore`** |
| `_google_token.json` | User OAuth token sinh ra khi login Google Drive | VPS + Local | **Bị chặn bởi `.gitignore`** |
| `*.db`, `*.sqlite`, `pdf/` | Database và các tệp PDF báo cáo tải về | VPS / Local | **Bị chặn bởi `.gitignore`** |
| `deploy-vps.ps1` | Script triển khai tự động lên VPS | Repo + Local + VPS | Đã chuẩn hóa: **Dùng biến môi trường** |
| `upload-google-creds.ps1` | Script tải credentials từ Local lên VPS | Repo + Local + VPS | Đã chuẩn hóa: **Dùng biến môi trường** |

---

## 3. Quy Chuẩn Bảo Mật Thông Tin Triển Khai

### A. Quản lý GitHub Personal Access Token (PAT)
- Token mẫu: `$GITHUB_TOKEN`
- Không hardcode token vào file mã nguồn được Git theo dõi.
- Remote URL trên cả Local và VPS được cấu hình thông qua Git remote hoặc credential helper:
  ```bash
  git remote set-url origin https://<TOKEN>@github.com/vietlod/stockreport.git
  ```

### B. Quản lý SSH & Mật khẩu VPS
- Thông số VPS:
  - **Host**: `31.97.110.12`
  - **User**: `root`
  - **Hostkey**: `ssh-ed25519 255 SHA256:wv5FF9UZRKTipXip0cFxvz9Xl2FLIZBfLiDgTaVuop8`
  - **Working Directory**: `/opt/stockreport`
- **Nguyên tắc**: Không đưa trực tiếp mật khẩu vào lịch sử lệnh hoặc file code. Luôn nạp thông qua biến môi trường phiên:
  ```powershell
  $env:VPS_IP = "31.97.110.12"
  $env:VPS_USER = "root"
  $env:VPS_PASSWORD = "..."
  $env:GITHUB_TOKEN = "..."
  ```

---

## 4. Quy Trình Vận Hành & Đồng Bộ Chuẩn

### Bước 1: Phát triển & Kiểm thử tại Local
```powershell
# Kích hoạt venv
.\.venv\Scripts\Activate.ps1

# Chạy server thử nghiệm local
python server.py
```

### Bước 2: Commit & Push lên GitHub Repo
```powershell
git status
git add <các file mã nguồn đã thay đổi>
git commit -m "feat/fix: mô tả nội dung"
git push origin dev
```

### Bước 3: Triển khai tự động lên VPS
Chỉ cần chạy script triển khai chuẩn hóa từ thư mục gốc dự án:
```powershell
$env:VPS_IP = "31.97.110.12"
$env:VPS_USER = "root"
$env:VPS_PASSWORD = "..."
$env:GITHUB_TOKEN = "..."

.\docs\deployment\deploy-vps.ps1
```
Script sẽ tự động:
1. Kết nối VPS an toàn qua `plink`.
2. `git fetch` và `git pull origin dev` mã nguồn mới nhất.
3. Cài đặt các gói phụ thuộc Python (`requirements.txt`).
4. Khởi động lại dịch vụ `systemctl restart stockreport`.

### Bước 4: Kiểm tra trạng thái dịch vụ trên VPS
```powershell
$PLINK = "C:\Program Files\PuTTY\plink.exe"
$HOSTKEY = "ssh-ed25519 255 SHA256:wv5FF9UZRKTipXip0cFxvz9Xl2FLIZBfLiDgTaVuop8"

# Kiểm tra status dịch vụ
& $PLINK -ssh -batch -hostkey $HOSTKEY -pw $env:VPS_PASSWORD root@31.97.110.12 "systemctl status stockreport --no-pager"

# Xem logs thời gian thực
& $PLINK -ssh -batch -hostkey $HOSTKEY -pw $env:VPS_PASSWORD root@31.97.110.12 "journalctl -u stockreport -n 30 --no-pager"
```

### Bước 5: Kéo cấu hình mới từ VPS về Local (khi VPS cập nhật)
Nếu có sự thay đổi biến môi trường trực tiếp trên VPS:
```powershell
$PSCP = "C:\Program Files\PuTTY\pscp.exe"
& $PSCP -batch -hostkey $HOSTKEY -pw $env:VPS_PASSWORD root@31.97.110.12:/opt/stockreport/.env d:\stockreport\.env
```

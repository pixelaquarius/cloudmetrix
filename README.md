# CloudMetrix Engine - Hướng Dẫn Cài Đặt & Khởi Chạy

CloudMetrix Engine là một hệ thống tự động hoá (Tiktok to Facebook Reels) kết hợp giao diện web Dashboard và các background workers để xử lý video.

## 1. Yêu Cầu Hệ Thống
- Python 3.9+
- FFmpeg (dùng để xử lý / transform video bypass bản quyền)
- Node.js (tuỳ chọn nếu một số module của Playwright yêu cầu)

## 2. Cài Đặt Môi Trường (Local / Server)

### Bước 1: Clone source code và tạo môi trường ảo
```bash
git clone https://github.com/pixelaquarius/cloudmetrix.git cloudmetrix
cd cloudmetrix
python3 -m venv venv
source venv/bin/activate
```

### Bước 2: Cài đặt thư viện Python
```bash
pip install -r requirements.txt
```

### Bước 3: Cài đặt Playwright Browser
Vì hệ thống dùng trình duyệt Playwright ẩn danh (headless/network interception) để auto-download và auto-upload, cần phải tải các file thực thi của trình duyệt:
```bash
playwright install
playwright install-deps
```

### Bước 4: Cài đặt FFmpeg
Hệ thống sử dụng FFmpeg để xử lý video (`video_transformer.py`).
- **Ubuntu/Debian (Server):** `sudo apt update && sudo apt install ffmpeg`
- **MacOS:** `brew install ffmpeg`
- **Windows:** Tải file `.exe` và đưa vào biến môi trường PATH.

---

## 3. Khởi Chạy Hệ Thống

Hệ thống hoạt động gồm 2 thành phần chính chạy song song: **Web Dashboard** và **Background Worker**.

### Cách 1: Chạy trực tiếp qua Terminal (Dành cho Local/Dev)

**Terminal 1: Khởi chạy Web Server (Flask Dashboard)**
```bash
source venv/bin/activate
python app.py
```
> Truy cập giao diện tại: `http://localhost:5001` (hoặc `http://<IP_SERVER>:5001`)

**Terminal 2: Khởi chạy Background Worker (Huey)**
```bash
source venv/bin/activate
huey_consumer workers.huey_app.huey
```
> Worker này sẽ đọc hàng đợi từ `data/huey_queue.db` và thực hiện các tác vụ ngầm kéo/tải video mà không làm nghẽn web server.

*(Tùy chọn) API Server Remote:*
Nếu bạn chỉ muốn mở kết nối API qua ngrok (FastAPI), chạy `python api_server.py`.

### Cách 2: Deploy trên Server Linux (Sử dụng Supervisor + Gunicorn)
Để hệ thống chạy nền (background) 24/7 và tự khởi động lại khi crash, bạn nên sử dụng `supervisor` và `gunicorn`.

**1. Cài đặt Supervisor**
```bash
sudo apt install supervisor
```

**2. Cấu hình chạy Web App (Gunicorn)**
Tạo file cấu hình tại `/etc/supervisor/conf.d/cloudmetrix_web.conf`:
```ini
[program:cloudmetrix_web]
directory=/path/to/cloudmetrix
# Lưu ý: Do dùng SocketIO nên phải sử dụng worker-class là eventlet
command=/path/to/cloudmetrix/venv/bin/gunicorn --worker-class eventlet -w 1 -b 0.0.0.0:5001 app:app
autostart=true
autorestart=true
stderr_logfile=/var/log/cloudmetrix_web.err.log
stdout_logfile=/var/log/cloudmetrix_web.out.log
```

**3. Cấu hình chạy Huey Worker**
Tạo file cấu hình cho Huey tại `/etc/supervisor/conf.d/cloudmetrix_worker.conf`:
```ini
[program:cloudmetrix_worker]
directory=/path/to/cloudmetrix
command=/path/to/cloudmetrix/venv/bin/huey_consumer workers.huey_app.huey
autostart=true
autorestart=true
stderr_logfile=/var/log/cloudmetrix_worker.err.log
stdout_logfile=/var/log/cloudmetrix_worker.out.log
```

**4. Khởi động các tiến trình**
```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start all
```

---

## 4. Cấu Trúc Các File Quan Trọng

- `app.py`: Web App chính với Flask và SocketIO để cập nhật log thời gian thực.
- `api_server.py`: API Server độc lập (FastAPI) để trigger job từ xa, tích hợp sẵn pyngrok.
- `workers/huey_app.py` & `workers/tasks.py`: Cấu hình hàng đợi bằng thư viện Huey (lưu local file SQLite).
- `database/models.py`: Chứa schema và kết nối SQLite bất đồng bộ (aiosqlite).
- `video_transformer.py`: Xử lý cắt ghép, thêm text chớp nháy bằng thư viện FFmpeg để lách bản quyền nền tảng.
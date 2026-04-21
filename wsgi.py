from app import app, DATA_FILE
import scheduler

# Khởi tạo tiến trình nền chạy cùng Web Server
post_manager = scheduler.AutoPostManager(DATA_FILE)
post_manager.start_automation()

if __name__ == "__main__":
    # Để host='0.0.0.0' để mọi thiết bị LAN hoặc mảng internet (Nếu mở NAT) đều dùng được
    app.run(host='0.0.0.0', port=5001)

import os
import sys
import subprocess
import venv
import shutil
from pathlib import Path

# --- ANSI COLORS ---
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_step(msg):
    print(f"\n{Colors.CYAN}{Colors.BOLD}>>> {msg}{Colors.RESET}")

def print_success(msg):
    print(f"{Colors.GREEN}✔ {msg}{Colors.RESET}")

def print_warning(msg):
    print(f"{Colors.YELLOW}⚠ {msg}{Colors.RESET}")

def print_error(msg):
    print(f"{Colors.RED}✖ {msg}{Colors.RESET}")

# --- 1. OS DETECTION & PRE-FLIGHT CHECKS ---
def get_os_type():
    if sys.platform.startswith('win'):
        return 'windows'
    elif sys.platform.startswith('darwin'):
        return 'macos'
    elif sys.platform.startswith('linux'):
        return 'linux'
    else:
        return 'unknown'

def check_ffmpeg():
    print_step("Kiểm tra FFmpeg...")
    if shutil.which("ffmpeg") is None:
        print_warning("Không tìm thấy FFmpeg trong PATH!")
        print_warning("Hệ thống vẫn có thể hoạt động nhưng các tính năng xử lý video (Bypass Copyright, Branding) sẽ thất bại.")
        print_warning("Vui lòng cài đặt FFmpeg và thêm vào biến môi trường PATH.")
    else:
        print_success("FFmpeg đã được cài đặt và sẵn sàng.")

# --- 2. TỰ ĐỘNG QUẢN LÝ VIRTUAL ENVIRONMENT (VENV) ---
def setup_venv():
    print_step("Kiểm tra Virtual Environment...")
    venv_dir = os.path.join(os.getcwd(), 'venv')
    
    if not os.path.exists(venv_dir):
        print(f"{Colors.BLUE}Đang tạo Virtual Environment tại: {venv_dir}{Colors.RESET}")
        venv.create(venv_dir, with_pip=True)
        print_success("Tạo Virtual Environment thành công.")
    else:
        print_success("Virtual Environment đã tồn tại.")
        
    os_type = get_os_type()
    if os_type == 'windows':
        venv_python = os.path.join(venv_dir, 'Scripts', 'python.exe')
        venv_bin = os.path.join(venv_dir, 'Scripts')
    else:
        venv_python = os.path.join(venv_dir, 'bin', 'python')
        venv_bin = os.path.join(venv_dir, 'bin')
        
    if not os.path.exists(venv_python):
        print_error("Không tìm thấy Python executable trong venv. Vui lòng xóa thư mục venv và chạy lại.")
        sys.exit(1)
        
    return venv_python, venv_bin

# --- 3. AUTO-INSTALL DEPENDENCIES ---
def install_dependencies(venv_python):
    print_step("Cài đặt thư viện và phụ thuộc...")
    req_file = os.path.join(os.getcwd(), 'requirements.txt')
    
    if not os.path.exists(req_file):
        print_warning(f"Không tìm thấy {req_file}. Bỏ qua cài đặt pip.")
    else:
        print(f"{Colors.BLUE}Đang chạy pip install... (Vui lòng chờ){Colors.RESET}")
        subprocess.check_call([venv_python, '-m', 'pip', 'install', '-r', req_file])
        print_success("Cài đặt thư viện Python hoàn tất.")

    print(f"{Colors.BLUE}Đang cài đặt Playwright Chromium...{Colors.RESET}")
    # Chạy playwright install thông qua module python
    subprocess.check_call([venv_python, '-m', 'playwright', 'install', 'chromium'])
    print_success("Cài đặt Playwright Chromium hoàn tất.")

# --- 4. ENV SETUP ---
def setup_env():
    print_step("Kiểm tra cấu hình môi trường (.env)...")
    env_file = os.path.join(os.getcwd(), '.env')
    
    if not os.path.exists(env_file):
        print_warning("Không tìm thấy tệp .env!")
        print(f"{Colors.BLUE}Đang tạo mẫu tệp .env...{Colors.RESET}")
        
        env_template = """# CloudMetrix Engine Environment Variables
GEMINI_API_KEY=your_gemini_api_key_here
FFMPEG_PATH=ffmpeg
FFPROBE_PATH=ffprobe
"""
        with open(env_file, 'w', encoding='utf-8') as f:
            f.write(env_template)
            
        print_error("Tệp .env đã được tạo. CHƯƠNG TRÌNH ĐANG DỪNG LẠI.")
        print_error("VUI LÒNG MỞ TỆP .env VÀ ĐIỀN GEMINI_API_KEY TRƯỚC KHI CHẠY LẠI SCRIPT NÀY!")
        sys.exit(0)
    else:
        print_success("Tệp .env đã tồn tại.")

# --- 5. PROCESS SPAWNER ---
def spawn_terminals(venv_python, venv_bin):
    print_step("Khởi chạy hệ thống CloudMetrix Engine...")
    
    os_type = get_os_type()
    cwd = os.getcwd()
    
    # Xác định đường dẫn huey_consumer (executable)
    huey_exe = "huey_consumer.exe" if os_type == 'windows' else "huey_consumer"
    huey_cmd_path = os.path.join(venv_bin, huey_exe)
    
    if not os.path.exists(huey_cmd_path):
        # Fallback chạy qua module python nếu không tìm thấy executable
        huey_command = f'"{venv_python}" -m huey.bin.huey_consumer workers.huey_app.huey'
    else:
        huey_command = f'"{huey_cmd_path}" workers.huey_app.huey'
        
    app_command = f'"{venv_python}" app.py'

    if os_type == 'windows':
        print(f"{Colors.BLUE}Đang mở các cửa sổ CMD trên Windows...{Colors.RESET}")
        subprocess.Popen(f'start "CloudMetrix Server" cmd /k "cd /d "{cwd}" & {app_command}"', shell=True)
        subprocess.Popen(f'start "CloudMetrix Background Worker (Huey)" cmd /k "cd /d "{cwd}" & {huey_command}"', shell=True)
        
    elif os_type == 'macos':
        print(f"{Colors.BLUE}Đang mở các cửa sổ Terminal trên macOS...{Colors.RESET}")
        apple_script_app = f'tell app "Terminal" to do script "cd \'{cwd}\' && {app_command}"'
        apple_script_huey = f'tell app "Terminal" to do script "cd \'{cwd}\' && {huey_command}"'
        
        subprocess.Popen(['osascript', '-e', apple_script_app])
        subprocess.Popen(['osascript', '-e', apple_script_huey])
        
    elif os_type == 'linux':
        print(f"{Colors.BLUE}Đang cố gắng mở Gnome-Terminal trên Linux...{Colors.RESET}")
        try:
            subprocess.Popen(['gnome-terminal', '--title=CloudMetrix Server', '--', 'bash', '-c', f'cd "{cwd}" && {app_command}; exec bash'])
            subprocess.Popen(['gnome-terminal', '--title=CloudMetrix Worker', '--', 'bash', '-c', f'cd "{cwd}" && {huey_command}; exec bash'])
        except FileNotFoundError:
            print_warning("Không tìm thấy gnome-terminal. Chạy dưới dạng background process...")
            subprocess.Popen(app_command, shell=True, cwd=cwd)
            subprocess.Popen(huey_command, shell=True, cwd=cwd)
            print_success("Đã chạy ngầm server và worker. Kiểm tra log trên console này nếu có lỗi.")
            
    print_success("🚀 HỆ THỐNG ĐÃ ĐƯỢC KHỞI CHẠY THÀNH CÔNG!")
    print(f"{Colors.GREEN}{Colors.BOLD}Truy cập giao diện: http://localhost:5001{Colors.RESET}")

# --- MAIN EXECUTOR ---
def main():
    # Bật support ANSI trên Windows CMD
    if os.name == 'nt':
        os.system('color')
        
    print(f"{Colors.HEADER}{Colors.BOLD}==================================================")
    print("      CLOUDMETRIX ENGINE - UNIVERSAL BOOTSTRAPPER")
    print(f"=================================================={Colors.RESET}")
    
    check_ffmpeg()
    venv_python, venv_bin = setup_venv()
    install_dependencies(venv_python)
    setup_env()
    spawn_terminals(venv_python, venv_bin)

if __name__ == "__main__":
    main()

import os
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium_stealth import stealth

# Global State for Live Posting Tracking
POST_STATE = {
    "status": "idle",
    "filename": "",
    "progress": 0,
    "logs": []
}

def log_post(msg, progress=None):
    time_str = datetime.now().strftime('%H:%M:%S')
    POST_STATE["logs"].append(f"[{time_str}] {msg}")
    if progress is not None:
        POST_STATE["progress"] = progress
    if len(POST_STATE["logs"]) > 20:
        POST_STATE["logs"].pop(0)
    print(msg)

KEYWORDS_NEXT = ["Next", "Tiếp", "Tiếp tục", "Continue"]
KEYWORDS_PUBLISH = ["Publish", "Đăng", "Đăng ngay", "Chia sẻ", "Share", "Xuất bản"]
KEYWORDS_ADD_VIDEO = ["Thêm video", "Add video", "Video"]
KEYWORDS_UPLOAD_PC = ["Tải lên từ máy tính", "Upload from computer", "Tải lên"]

def find_button_by_text(driver, keywords):
    """
    Mới V4: Quét toàn bộ thẻ span, div, button chứa văn bản khớp mục tiêu.
    Đặc biệt xử lý các thẻ React ảo lồng nhau của Facebook.
    """
    for kw in keywords:
        try:
            # Quét tìm thẻ Mẹ là button chứa cái dòng chữ kia
            xpath = f"//*[contains(normalize-space(.), '{kw}') and (@role='button' or self::button)]"
            els = driver.find_elements(By.XPATH, xpath)
            # Lấy thẻ gốc sát nhất, tránh chọn nhầm body
            if els:
                return els[-1] 
        except:
            pass
            
    elements = driver.find_elements(By.XPATH, "//*[self::span or self::div or self::button]")
    for el in elements:
        try:
            text = el.text.strip()
            if text in keywords and el.is_displayed():
                return el
        except:
            continue
    return None

import playwright_uploader

def upload_to_facebook_page(video_path, caption, profile_name="Default"):
    """
    V5: Using Playwright for maximum reliability with Meta Business Suite.
    """
    # Sync states
    playwright_uploader.POST_STATE = POST_STATE
    
    try:
        success = playwright_uploader.upload_to_facebook_page_playwright(video_path, caption, profile_name, external_state=POST_STATE)
    finally:
        # After playwright finishes, make sure our local status matches (it should be idle anyway)
        POST_STATE["status"] = "idle"
        
    return success

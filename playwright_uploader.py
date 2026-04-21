import os
import time
import re
from datetime import datetime
from playwright.sync_api import sync_playwright

# Global State for Live Posting Tracking (Shared with uploader.py)
POST_STATE = {
    "status": "idle",
    "filename": "",
    "logs": []
}

def log_post(msg, state_object=None, progress=None):
    time_str = datetime.now().strftime('%H:%M:%S')
    target_state = state_object if state_object is not None else POST_STATE
    target_state["logs"].append(f"[{time_str}] {msg}")
    if progress is not None:
        target_state["progress"] = progress
    if len(target_state["logs"]) > 20:
        target_state["logs"].pop(0)
    print(msg)

def get_user_data_dir(profile_name):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    # Standardize sanitization: allow alphanumeric, underscore, and hyphen
    safe_profile = "".join([c for c in profile_name if c.isalnum() or c in ('_', '-')]).strip()
    if not safe_profile: safe_profile = "Automation_1"
    
    profiles_dir = os.path.join(base_dir, 'data', 'profiles')
    os.makedirs(profiles_dir, exist_ok=True)
    return os.path.join(profiles_dir, safe_profile)

def upload_to_facebook_page_playwright(video_path, caption, profile_name="Automation_1", external_state=None):
    # Use external state if provided for real-time telemetry
    state = external_state if external_state is not None else POST_STATE
    
    # SIGNAL START TO UI
    state['status'] = 'running'
    state['filename'] = os.path.basename(video_path)
    state['progress'] = 5

    user_data_dir = get_user_data_dir(profile_name)
    
    # --- PRE-FLIGHT VALIDATION ---
    if not os.path.exists(video_path):
        log_post(f"❌ ABORT: Media file not found: {video_path}", state)
        return False
        
    valid_exts = ['.mp4', '.mov', '.avi', '.mkv', '.jpg', '.jpeg', '.png']
    ext = os.path.splitext(video_path)[1].lower()
    if ext not in valid_exts:
        log_post(f"❌ ABORT: Unsupported file type '{ext}'. Meta requires video or images.", state)
        return False

    log_post(f"Rocketing Playwright Engine: {state['filename']}", state, progress=10)
    
    HEADLESS = False  # Set to False to allow user to see and login if needed
    
    with sync_playwright() as p:
        # Launch persistent context to use existing cookies/session
        browser = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=HEADLESS, 
            args=["--disable-blink-features=AutomationControlled"]
        )
        
        page = browser.new_page()
        
        try:
            log_post("Navigating to Meta Business Suite Composer...", state, progress=15)
            page.goto("https://business.facebook.com/latest/composer", wait_until="load", timeout=90000)
            
            # 1. Check for Login and stabilize session
            page.wait_for_timeout(7000)
            
            # Robust login check: if redirected or composer elements missing
            is_login_page = "login" in page.url.lower() or page.locator("text=Bắt đầu với, text=Log In").count() > 0
            
            if is_login_page:
                log_post("⚠️ AUTHENTICATION REQUIRED!", state)
                log_post("Please LOGIN in the browser window. Waiting up to 5 minutes...", state)
                # Wait for any element that definitely indicates composer is loaded
                try:
                    page.wait_for_selector("text=Tạo bài viết, input[type='file'], [aria-label*='video' i]", timeout=300000)
                    log_post("✅ Login detected. Letting session settle...", state)
                    page.wait_for_timeout(5000) # Give Meta time to save cookies
                except:
                    log_post("❌ Login timeout or failed.", state)
                    return False
 
            log_post("Searching for Video Upload trigger...", state, progress=25)
            
            # Use File Chooser Interceptor - most reliable for Meta
            try:
                log_post("Setting up File Chooser Interceptor...", state)
                with page.expect_file_chooser(timeout=45000) as fc_info:
                    # Look for the 'Thêm video' button using multiple patterns
                    btn_patterns = ["text=/Thêm video/i", "text=/Add Video/i", "text=/Video/i", "[aria-label*='video' i]", "[aria-label*='media' i]"]
                    btn_video = None
                    for pattern in btn_patterns:
                        try:
                            loc = page.locator(pattern).first
                            if loc.is_visible():
                                btn_video = loc
                                break
                        except:
                            continue
                    
                    if not btn_video:
                        # Fallback to get_by_role for 2026 standards
                        btn_video = page.get_by_role("button", name=re.compile("video|add", re.I)).first
                    
                    btn_video.wait_for(state="visible", timeout=15000)
                    log_post(f"Found injection node. Clicking... ({btn_video.evaluate('el => el.innerText || el.ariaLabel')})", state)
                    btn_video.click()
                    page.wait_for_timeout(3000)
                    
                    # Detect and handle dropdown menu (Tải lên từ máy tính / Upload from computer)
                    dropdown_patterns = ["Tải lên từ máy tính", "Upload from computer", "Upload from", "Tải lên"]
                    for dp in dropdown_patterns:
                        btn_upload = page.get_by_text(dp, exact=False).first
                        if btn_upload.is_visible():
                            log_post(f"Dropdown detected: Clicking '{dp}'", state)
                            btn_upload.click()
                            break
                
                file_chooser = fc_info.value
                file_chooser.set_files(os.path.abspath(video_path))
                log_post("✅ File chooser intercepted and payload delivered!", state, progress=50)
            except Exception as e:
                log_post(f"File chooser strategy failed ({str(e)}). Attempting direct input injection...", state)
                try:
                    # Attempt to find the specific file input that isn't hidden by display:none if possible
                    inputs = page.locator("input[type='file']")
                    found = False
                    for i in range(inputs.count()):
                        try:
                            inputs.nth(i).set_input_files(os.path.abspath(video_path))
                            log_post(f"✅ Input injection succeeded on index {i}!", state)
                            found = True
                            break
                        except:
                            continue
                    if not found: raise Exception("No valid file input found")
                except:
                    log_post("❌ All upload strategies failed. Saving error screenshot.", state)
                    page.screenshot(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "upload_error.png"))
                    raise e

            log_post("✅ Media payload delivered successfully.", state)
            page.wait_for_timeout(5000) # Wait for Meta to recognize the file

            # 2. Enter Caption
            log_post("Injecting post caption...", state)
            textbox = page.locator("div[role='textbox'], [contenteditable='true']").first
            textbox.wait_for(state="visible", timeout=30000)
            textbox.click()
            textbox.fill(caption)
            log_post("✅ Caption injected.", state, progress=65)

            # 3. Step through Next/Publish with robust action detection
            log_post("Executing sequence bypass (Next -> Next -> Publish)...", state, progress=70)
            
            for i in range(40): # Extended cycles (approx 3-4 mins) for heavy video processing
                page.wait_for_timeout(5000)
                log_post(f"Bypass cycle {i+1}/40... checking UI state", state)
                
                # A. Handle Popups/Banners (The "Reels" prompt etc.)
                try:
                    close_btns = page.locator("[aria-label*='Close' i], [aria-label*='Đóng' i], [aria-label*='Tắt' i]").all()
                    for cb in close_btns:
                        if cb.is_visible() and cb.is_enabled():
                            log_post("🧹 Banner/Popup detected. Dismissing...", state)
                            cb.click(force=True)
                            page.wait_for_timeout(1000)
                except: pass

                # B. Check for Meta errors
                error_msg = page.locator("text=không thể tải, text=Error, text=lỗi, text=something went wrong, text=trục trặc").first
                if error_msg.count() > 0 and error_msg.is_visible():
                    log_post(f"⚠️ Meta reported an error: {error_msg.inner_text()}", state)

                # C. Robust Button Detection (Universal Action Pattern)
                # This regex covers Publish, Next, Share, Done in multiple languages and UI versions
                action_pattern = re.compile("Đăng|Publish|Tiếp|Next|Chia sẻ|Share|Xong|Done|Hoàn tất", re.I)
                
                # Find all potential buttons
                buttons = page.locator("div[role='button'], button").all()
                found_action = None
                
                for btn in buttons:
                    try:
                        b_text = (btn.inner_text() or btn.get_attribute("aria-label") or "").strip()
                        # Must be visible AND active to be a valid target
                        if action_pattern.search(b_text) and btn.is_visible():
                            # CHECK IF DISABLED (Meta uses 'disabled' attribute or classes)
                            is_disabled = (btn.get_attribute("disabled") is not None or 
                                           "disabled" in (btn.get_attribute("class") or "").lower() or
                                           btn.get_attribute("aria-disabled") == "true")
                            
                            if is_disabled:
                                # log_post(f"Button '{b_text.upper()}' found but currently disabled.", state)
                                continue # Wait for it to become active
                                
                            # Prioritize 'Publish' or 'Đăng' over 'Next'
                            if re.search("Đăng|Publish|Share|Chia sẻ", b_text, re.I):
                                found_action = btn
                                break # Found the final action
                            else:
                                found_action = btn # Found 'Next', keep looking for 'Publish'
                    except: continue

                if found_action:
                    btn_label = (found_action.inner_text() or "Action Button").strip().upper()
                    log_post(f"🚀 ACTION: Clicking '{btn_label}'", state)
                    found_action.scroll_into_view_if_needed()
                    found_action.click(force=True)
                    
                    # If this was the final action, wait and check for completion
                    if re.search("Đăng|Publish|Share|Chia sẻ|Xong|Done", btn_label, re.I):
                        log_post("Waiting for confirmation screen...", state)
                        page.wait_for_timeout(10000)
                        # Check if we are still on composer or moved to dashboard/success
                        if "composer" not in page.url.lower() or page.locator("text=đã đăng, text=published, text=success").count() > 0:
                            log_post("🎉 TASK COMPLETED SUCCESSFULLY!", state, progress=100)
                            return True
                    page.wait_for_timeout(2000)
                    # Small incremental progress during bypass cycles
                    new_progress = min(98, 70 + (i * 2))
                    log_post(f"Processing... {new_progress}%", state, progress=new_progress)
                    continue # Advance to next cycle
                
                log_post("Processing video or waiting for button activation...", state)

            log_post("❌ Sequence stalled. Meta might be processing slowly or UI is blocked.", state)
            # Take one final screenshot for debug
            page.screenshot(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "error_sequence_stalled.png"))
            return False

        except Exception as e:
            log_post(f"❌ Playwright Error: {str(e)}", state)
            # Optional: save screenshot for debugging
            try:
                page.screenshot(path=os.path.join(base_dir, "data", "error_playwright.png"))
            except:
                pass
            return False
        finally:
            browser.close()

def verify_facebook_login(profile_name="Automation_1"):
    user_data_dir = get_user_data_dir(profile_name)
    HEADLESS = True  
    
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=HEADLESS, 
                args=["--disable-blink-features=AutomationControlled"]
            )
            
            page = browser.new_page()
            # Set a shorter timeout for verification
            page.set_default_timeout(30000)
            
            page.goto("https://business.facebook.com/latest/composer", wait_until="networkidle")
            page.wait_for_timeout(3000) # Small buffer for React hydration

            # If redirected to login, or common login elements are visible
            if "login" in page.url.lower():
                return "Auth Required"
            
            # Check for composer-specific elements
            composer_selectors = ["text=Tạo bài viết", "text=Create post", "input[type='file']", "[role='main']"]
            logged_in = False
            for selector in composer_selectors:
                if page.locator(selector).first.is_visible():
                    logged_in = True
                    break
            
            if logged_in:
                return "Verified"
            else:
                return "Auth Required"
                
        except Exception as e:
            print(f"Verification Error: {str(e)}")
            return "Error"
        finally:
            if 'browser' in locals():
                browser.close()

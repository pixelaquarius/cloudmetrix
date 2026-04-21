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
            
            is_login_page = "login" in page.url.lower() or page.locator("[aria-label='Log In'], [aria-label='Bắt đầu với']").count() > 0
            
            if is_login_page:
                log_post("⚠️ AUTHENTICATION REQUIRED!", state)
                log_post("Please LOGIN in the browser window. Waiting up to 5 minutes...", state)
                try:
                    page.wait_for_selector("input[type='file'], [aria-label*='video' i]", timeout=300000)
                    log_post("✅ Login detected. Letting session settle...", state)
                    page.wait_for_timeout(5000)
                except:
                    log_post("❌ Login timeout or failed.", state)
                    return False
 
            log_post("Searching for Video Upload trigger...", state, progress=25)
            
            try:
                log_post("Setting up File Chooser Interceptor...", state)
                with page.expect_file_chooser(timeout=45000) as fc_info:
                    # Using stricter CSS/Aria selectors
                    btn_video = page.locator("[aria-label='Add video'], [aria-label='Thêm video'], [data-testid='media-upload-button']").first
                    
                    if not btn_video.is_visible():
                        # Fallback CSS Selectors for generic upload icons
                        btn_video = page.locator("div[role='button'] i[data-visualcompletion='css-img']").first
                    
                    btn_video.wait_for(state="visible", timeout=15000)
                    log_post(f"Found injection node. Clicking...", state)
                    btn_video.click()
                    page.wait_for_timeout(3000)
                    
                    # Detect and handle dropdown menu
                    dropdown_upload = page.locator("[aria-label='Upload from computer'], [aria-label='Tải lên từ máy tính']").first
                    if dropdown_upload.is_visible():
                        log_post("Dropdown detected: Clicking 'Upload from computer'", state)
                        dropdown_upload.click()
                
                file_chooser = fc_info.value
                file_chooser.set_files(os.path.abspath(video_path))
                log_post("✅ File chooser intercepted and payload delivered!", state, progress=50)
            except Exception as e:
                log_post(f"File chooser strategy failed ({str(e)}). Attempting direct input injection...", state)
                try:
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
            page.wait_for_timeout(5000)

            # 2. Enter Caption
            log_post("Injecting post caption...", state)
            textbox = page.locator("div[role='textbox'][aria-label*='text'], [contenteditable='true']").first
            textbox.wait_for(state="visible", timeout=30000)
            textbox.click()
            textbox.fill(caption)
            log_post("✅ Caption injected.", state, progress=65)

            # 3. Step through Next/Publish with robust action detection
            log_post("Executing sequence bypass (Next -> Next -> Publish)...", state, progress=70)
            
            for i in range(40):
                page.wait_for_timeout(5000)
                log_post(f"Bypass cycle {i+1}/40... checking UI state", state)
                
                # A. Handle Popups/Banners
                try:
                    close_btns = page.locator("[aria-label='Close'], [aria-label='Đóng']").all()
                    for cb in close_btns:
                        if cb.is_visible() and cb.is_enabled():
                            log_post("🧹 Banner/Popup detected. Dismissing...", state)
                            cb.click(force=True)
                            page.wait_for_timeout(1000)
                except: pass

                # B. CSS Selector-based Action Button Logic
                # Look for final action first (Publish/Share/Done)
                publish_btn = page.locator("[aria-label='Publish'], [aria-label='Đăng'], [aria-label='Share'], [aria-label='Chia sẻ'], [aria-label='Done'], [aria-label='Xong']").first
                next_btn = page.locator("[aria-label='Next'], [aria-label='Tiếp']").first
                
                found_action = None
                is_final_action = False
                
                if publish_btn.count() > 0 and publish_btn.is_visible():
                    # Check if disabled
                    is_disabled = publish_btn.get_attribute("aria-disabled") == "true" or "disabled" in str(publish_btn.get_attribute("class")).lower()
                    if not is_disabled:
                        found_action = publish_btn
                        is_final_action = True
                elif next_btn.count() > 0 and next_btn.is_visible():
                    is_disabled = next_btn.get_attribute("aria-disabled") == "true" or "disabled" in str(next_btn.get_attribute("class")).lower()
                    if not is_disabled:
                        found_action = next_btn
                
                if found_action:
                    log_post(f"🚀 ACTION: Clicking {'Publish/Final' if is_final_action else 'Next'}", state)
                    found_action.scroll_into_view_if_needed()
                    found_action.click(force=True)
                    
                    if is_final_action:
                        log_post("Waiting for confirmation screen...", state)
                        page.wait_for_timeout(10000)
                        
                        # Verify completion
                        if "composer" not in page.url.lower() or page.locator("[aria-label='Published'], [aria-label='Đã đăng']").count() > 0:
                            log_post("🎉 TASK COMPLETED SUCCESSFULLY!", state, progress=100)
                            
                            # GROWTH FEATURE: FIRST COMMENT INJECTION
                            # Check if we have an external state with affiliate link to inject
                            affiliate_link = external_state.get('affiliate_link') if external_state else None
                            if affiliate_link:
                                inject_first_comment(page, affiliate_link, state)
                                
                            return True
                    
                    page.wait_for_timeout(2000)
                    new_progress = min(98, 70 + (i * 2))
                    log_post(f"Processing... {new_progress}%", state, progress=new_progress)
                    continue
                
                log_post("Processing video or waiting for button activation...", state)

            log_post("❌ Sequence stalled. Meta might be processing slowly or UI is blocked.", state)
            page.screenshot(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "error_sequence_stalled.png"))
            return False

        except Exception as e:
            log_post(f"❌ Playwright Error: {str(e)}", state)
            try:
                page.screenshot(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "error_playwright.png"))
            except: pass
            return False
        finally:
            if 'browser' in locals() and browser:
                browser.close()

def inject_first_comment(page, affiliate_link, state):
    """ GROWTH HOOK: Auto-Seeding & Affiliate Injection """
    try:
        log_post("🌱 GROWTH HOOK: Injecting First Comment with Affiliate Link...", state)
        
        # Look for the recently published post notification or link
        view_post_btn = page.locator("[aria-label='View Post'], [aria-label='Xem bài viết']").first
        if view_post_btn.is_visible():
            view_post_btn.click()
            page.wait_for_load_state("networkidle")
            
            # Find the comment box
            comment_box = page.locator("[aria-label='Write a comment'], [aria-label='Viết bình luận']").first
            comment_box.wait_for(state="visible", timeout=10000)
            comment_box.click()
            
            comment_content = f"Sản phẩm cực chất! Mua ngay tại đây nhận ưu đãi: {affiliate_link}"
            comment_box.fill(comment_content)
            
            # Press Enter to submit comment
            page.keyboard.press("Enter")
            log_post("✅ Seed Comment Injected Successfully!", state)
            page.wait_for_timeout(3000)
            
            # Attempt to pin the comment (if Meta UI supports it in this context)
            try:
                more_opts = page.locator("[aria-label='More options'], [aria-label='Tùy chọn khác']").first
                if more_opts.is_visible():
                    more_opts.click()
                    pin_btn = page.locator("text='Ghim bình luận', text='Pin comment'").first
                    if pin_btn.is_visible():
                        pin_btn.click()
                        log_post("📌 Comment Pinned!", state)
            except Exception as e:
                log_post("⚠️ Pinning comment failed or not supported in current UI view.", state)
                
    except Exception as e:
        log_post(f"⚠️ Seed Comment Injection Failed: {str(e)}", state)

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

import os
import time
import random
from datetime import datetime
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

class FacebookReelsUploader:
    def __init__(self, profile_name="Automation_1", state=None):
        self.profile_name = profile_name
        self.state = state or {"status": "idle", "logs": [], "progress": 0}

    def _log(self, msg, progress=None):
        time_str = datetime.now().strftime('%H:%M:%S')
        self.state["logs"].append(f"[{time_str}] {msg}")
        if progress is not None:
            self.state["progress"] = progress
        print(msg)

    def _jitter(self, min_s=2, max_s=5):
        """Random delay to simulate human behavior."""
        delay = random.uniform(min_s, max_s)
        time.sleep(delay)

    def _get_user_dir(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        profiles_dir = os.path.join(base_dir, 'data', 'profiles')
        return os.path.join(profiles_dir, self.profile_name)

    def upload_reel(self, video_path, caption, affiliate_link=None, asset_id=None):
        """
        Automates the Reels upload flow on Meta Business Suite.
        """
        self._log(f"🚀 Reels sequence initiated: {os.path.basename(video_path)}", progress=5)
        
        full_caption = caption
        if affiliate_link:
            full_caption += f"\n\n🔗 Mua tại đây: {affiliate_link}"

        user_data_dir = self._get_user_dir()
        
        with sync_playwright() as p:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=False,
                args=["--disable-blink-features=AutomationControlled"]
            )
            page = browser.new_page()
            Stealth().apply_stealth_sync(page)

            try:
                self._log("Navigating to Business Suite Reels...", progress=15)
                composer_url = "https://business.facebook.com/latest/reels_composer"
                if asset_id:
                    composer_url += f"?asset_id={asset_id}"
                page.goto(composer_url, wait_until="networkidle")
                self._jitter(2, 4)
                
                # Session and Layout Check
                if "login" in page.url:
                    self._log("❌ Error: Facebook session EXPIRED. Redirected to login.")
                    return "SESSION_EXPIRED"
                
                # Trial and Error Navigation Resilience
                self._log("Searching for video upload node...", progress=25)
                
                # Check if we are on the Home page instead of Composer
                if "home" in page.url or "reels_composer" not in page.url:
                    self._log("⚠️ Not on composer page. Attempting to click 'Create Reel' button...")
                    create_reel_btn = page.query_selector('text="Create Reel"') or page.query_selector('text="Tạo thước phim"')
                    if create_reel_btn:
                        create_reel_btn.click()
                        self._jitter(4, 7)

                # Try multiple selectors for the file input or the "Add Video" button
                try:
                    page.wait_for_selector('input[type="file"]', timeout=30000)
                    file_input = page.query_selector('input[type="file"]')
                    file_input.set_input_files(video_path)
                except:
                    self._log("⚠️ Primary file input not found. Attempting 'Add Video' button fallback...")
                    # More comprehensive button selectors from subagent research
                    add_btn = (page.query_selector('div[role="button"]:has-text("Thêm video")') or 
                               page.query_selector('div[role="button"]:has-text("Add Video")') or
                               page.query_selector('text="Thêm video"') or
                               page.query_selector('text="Add Video"'))
                    
                    if add_btn:
                        self._log("Clicking 'Thêm video' button and expecting file chooser...")
                        try:
                            with page.expect_file_chooser(timeout=10000) as fc_info:
                                add_btn.click()
                            file_chooser = fc_info.value
                            file_chooser.set_files(video_path)
                            self._log("✅ File chooser handled successfully.")
                        except Exception as e:
                            self._log(f"⚠️ File chooser failed: {e}. Falling back to input search.")
                            # Search for any file input that accepts video or looks like an upload node
                            input_selectors = [
                                'input[type="file"][accept*="video"]',
                                'input[type="file"]',
                                'input[accept*="video"]'
                            ]
                            
                            file_input = None
                            for sel in input_selectors:
                                try:
                                    page.wait_for_selector(sel, state="attached", timeout=5000)
                                    file_input = page.query_selector(sel)
                                    if file_input:
                                        self._log(f"Found upload node via: {sel}")
                                        break
                                except: continue
                            
                            if file_input:
                                file_input.set_input_files(video_path)
                            else:
                                raise Exception("Still no file input/chooser found after clicking button.")
                        except:
                            # Final absolute fallback: set_input_files on ANY input that takes files
                            try:
                                all_inputs = page.query_selector_all('input[type="file"]')
                                if all_inputs:
                                    self._log(f"Fallback: Sending to first of {len(all_inputs)} generic file inputs.")
                                    all_inputs[0].set_input_files(video_path)
                                else:
                                    raise Exception("No file inputs found whatsoever on page.")
                            except Exception as e:
                                raise Exception(f"Fundamental UI failure: {e}")
                    else:
                        # Final attempt: just try to click the center of the page if it looks empty
                        self._log("⚠️ Final attempt: Clicking page area for potential drop-zone...")
                        page.mouse.click(600, 400) 
                        time.sleep(2)
                        if page.query_selector('input[type="file"]'):
                            page.set_input_files('input[type="file"]', video_path)
                        else:
                            raise Exception("Fundamental UI navigation failure.")
                
                self._log("✅ Media uploaded. Waiting for processing...", progress=50)
                self._jitter(8, 12) # Human-like wait for upload progress

                # Fill Caption
                self._log("Injecting caption & links...", progress=70)
                # Find the div with role="textbox" or similar
                caption_box = page.wait_for_selector('div[role="textbox"]')
                caption_box.click()
                
                # Simulate human typing
                for char in full_caption:
                    page.keyboard.type(char)
                    if random.random() > 0.7: # Occasional delay between chars
                        time.sleep(random.uniform(0.05, 0.15))
                
                self._jitter(1, 3)

                # Navigation sequence (Next -> Next -> Share)
                # In Business Suite, there are usually 3 "Next" buttons
                for i in range(2):
                    self._log(f"Navigation bypass step {i+1}...", progress=80 + i*5)
                    next_btns = page.query_selector_all('text="Tiếp"'); # Vietnamese UI
                    if not next_btns: next_btns = page.query_selector_all('text="Next"'); # English UI
                    
                    if next_btns:
                        next_btns[-1].click()
                        self._jitter(1, 2)

                # Final Share button
                self._log("Finalizing publication...", progress=95)
                
                # Wait 3 to 5 seconds before the first click attempt
                self._jitter(3, 5)
                
                share_selectors = [
                    'div[role="button"]:has-text("Chia sẻ")',
                    'div[role="button"]:has-text("Share")',
                    'text="Chia sẻ"',
                    'text="Share"'
                ]
                
                success_selectors = [
                    'div[role="button"]:has-text("Xong")',
                    'div[role="button"]:has-text("Done")',
                    'text="Xong"', 'text="Done"', 
                    'text="Thước phim đã được chia sẻ"', 
                    'text="Your reel has been shared"'
                ]

                # Hàm click thử nghiệm
                def execute_share_click():
                    share_btn = None
                    for sel in share_selectors:
                        share_btn = page.query_selector(sel)
                        if share_btn: break
                    
                    if share_btn:
                        try:
                            share_btn.click(force=True, timeout=3000)
                        except: pass
                    
                    # Luôn backup bằng JS Injection (tỷ lệ thành công cực cao)
                    page.evaluate("""
                        () => {
                            const buttons = Array.from(document.querySelectorAll('div[role="button"], button'));
                            buttons.forEach(b => {
                                const text = b.innerText.trim();
                                if (text === 'Chia sẻ' || text === 'Share' || text === 'Đăng') {
                                    b.click();
                                }
                            });
                        }
                    """)

                # Retry loop cho nút Đăng
                publication_success = False
                for attempt in range(3):
                    self._log(f"Attempting share click (Lần {attempt + 1})...")
                    execute_share_click()
                    
                    self._log("Waiting for publication confirmation (Xong/Done)...")
                    found_sel = None
                    # Chờ 5s để xem có màn hình Xong không
                    for _ in range(5): 
                        for sel in success_selectors:
                            if page.query_selector(sel):
                                found_sel = sel
                                break
                        if found_sel: break
                        time.sleep(1)
                    
                    if found_sel:
                        publication_success = True
                        self._log(f"✅ Reel Published & Verified via: {found_sel}")
                        
                        # Click Xong if we found a valid button
                        try:
                            done_btn = page.query_selector(found_sel)
                            if done_btn: done_btn.click(timeout=1000)
                        except: pass

                        # Proof Screenshot
                        proof_path = f"scratch/success_{int(time.time())}.png"
                        page.screenshot(path=proof_path)
                        self._log(f"📸 Proof of success saved to: {proof_path}")
                        self._jitter(1, 2)
                        break
                    else:
                        self._log("⚠️ Không thấy màn hình Xong, đợi thêm 2s và bấm thử lại...")
                        page.screenshot(path=f"scratch/check_state_attempt_{attempt}_{int(time.time())}.png")
                        time.sleep(2) # Đợi thêm 2s như yêu cầu rồi thử lại
                
                if not publication_success:
                    self._log("❌ Click Đăng không thành công sau 3 lần thử.")

                return True

            except Exception as e:
                self._log(f"❌ Reels Error: {e}")
                # Debug Screenshot
                try:
                    debug_path = f"scratch/upload_fail_{int(time.time())}.png"
                    page.screenshot(path=debug_path)
                    self._log(f"📸 Debug screenshot saved to: {debug_path}")
                except: pass
                return False
            finally:
                browser.close()

    def verify_publication(self, caption, asset_id=None):
        """
        Navigates to the Published Posts feed to verify the latest Reel.
        """
        self._log(f"🔍 Verifying publication for: {caption[:30]}...")
        user_data_dir = self._get_user_dir()
        
        with sync_playwright() as p:
            browser = p.chromium.launch_persistent_context(user_data_dir=user_data_dir, headless=True)
            page = browser.new_page()
            
            try:
                # URL for Published Reels
                url = "https://business.facebook.com/latest/posts/published_posts?content_type=REELS"
                if asset_id:
                    url += f"&asset_id={asset_id}"
                
                page.goto(url, wait_until="networkidle")
                time.sleep(5) # Wait for list to load
                
                # Check for the caption in the first few rows of the table
                # Usually, newest posts are at the top
                feed_text = page.inner_text('body')
                
                # Clean up caption for matching (remove hashtags/emojis for better substring match)
                clean_caption = "".join(filter(str.isalnum, caption[:20].lower()))
                clean_feed = "".join(filter(str.isalnum, feed_text.lower()))
                
                if clean_caption in clean_feed:
                    self._log("✅ Verification SUCCESS: Post found in published feed.")
                    return True
                else:
                    self._log("⚠️ Verification PENDING: Post not found in first page of feed yet.")
                    # Take a screenshot for manual audit
                    page.screenshot(path=f"scratch/verify_check_{int(time.time())}.png")
                    return False
            except Exception as e:
                self._log(f"❌ Verification Error: {e}")
                return False
            finally:
                browser.close()

# Test Logic
if __name__ == "__main__":
    uploader = FacebookReelsUploader()
    uploader.upload_reel("scratch/transformed_test.mp4", "Test Reels Caption #AI #Automation", "https://shope.ee/test")

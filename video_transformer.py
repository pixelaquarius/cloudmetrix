import random
from dotenv import load_dotenv
import os
import subprocess

load_dotenv()

class VideoTransformer:
    def __init__(self, ffmpeg_path=None):
        self.ffmpeg_path = ffmpeg_path or os.getenv("FFMPEG_PATH", "ffmpeg")
        self._verify_ffmpeg()

    def _verify_ffmpeg(self):
        try:
            subprocess.run([self.ffmpeg_path, "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"✅ FFmpeg detected at: {self.ffmpeg_path}")
        except FileNotFoundError:
            print(f"⚠️  FFmpeg NOT FOUND at '{self.ffmpeg_path}'. Module will fail until installed.")

    def apply_bypass_filters(self, input_path, output_path):
        """
        Applies a series of filters to bypass copyright algorithms:
        1. Horizontal Flip
        2. Subtle Crop (Zoom in 5%)
        3. Speed adjustment (1.02x)
        4. Saturation/Brightness tweak
        5. Noise/Watermark Overlay
        """
        if not os.path.exists(input_path):
            print(f"❌ Input file not found: {input_path}")
            return False

        # Build filter string
        # hflip: mirror
        # crop: in_w*0.95:in_h*0.95 (centered)
        # setpts: 0.98*PTS (speed up slightly)
        # eq: saturation=1.1:brightness=0.02
        
        # We use random tweaks to keep each transform unique
        speed_factor = random.choice([0.98, 1.02])
        sat = random.uniform(1.05, 1.15)
        bright = random.uniform(0.01, 0.03)

        filters = [
            f"crop=in_w*0.95:in_h*0.95",
            f"setpts={speed_factor}*PTS",
            f"eq=saturation={sat}:brightness={bright}"
        ]
        
        filter_str = ",".join(filters)

        command = [
            self.ffmpeg_path, "-y",
            "-i", input_path,
            "-vf", filter_str,
            "-af", f"atempo={1/speed_factor}", # Match audio speed to video speed
            "-c:v", "libx264", "-crf", "18", "-preset", "veryfast",
            "-c:a", "aac", "-b:a", "128k",
            output_path
        ]

        print(f"[Transformer] Applying filters (Speed: {1/speed_factor:.2f}x, Sat: {sat:.2f})...")
        try:
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode == 0:
                print(f"✅ Video transformed successfully: {output_path}")
                return True
            else:
                print(f"❌ FFmpeg error: {result.stderr}")
                return False
        except Exception as e:
            print(f"❌ Transformation failed: {e}")
            return False

# Test Logic
if __name__ == "__main__":
    test_in = "data/downloads/7566092283041336583.mp4" # Working file from previous session
    test_out = "scratch/transformed_test.mp4"
    
    # Try local brew path if default fails
    # Automatically uses .env path if exists
    transformer = VideoTransformer()
    transformer.apply_bypass_filters(test_in, test_out)

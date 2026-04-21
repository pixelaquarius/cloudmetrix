import random
from dotenv import load_dotenv
import os
import asyncio
import json

load_dotenv()

class VideoTransformer:
    def __init__(self, ffmpeg_path=None, ffprobe_path=None):
        self.ffmpeg_path = ffmpeg_path or os.getenv("FFMPEG_PATH", "ffmpeg")
        self.ffprobe_path = ffprobe_path or os.getenv("FFPROBE_PATH", "ffprobe")
        # Ensure Paths for Windows
        if os.name == 'nt':
            if not self.ffmpeg_path.endswith('.exe') and not os.path.isabs(self.ffmpeg_path):
                self.ffmpeg_path += '.exe'
            if not self.ffprobe_path.endswith('.exe') and not os.path.isabs(self.ffprobe_path):
                self.ffprobe_path += '.exe'

    async def _get_duration(self, input_path):
        cmd = [
            self.ffprobe_path, "-v", "error", "-show_entries",
            "format=duration", "-of",
            "default=noprint_wrappers=1:nokey=1", input_path
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        try:
            return float(stdout.decode().strip())
        except:
            return 15.0 # Fallback

    async def apply_bypass_filters(self, input_path, output_path):
        """
        Applies a series of filters to bypass copyright algorithms:
        1. Horizontal Flip
        2. Subtle Crop (Zoom in 5%)
        3. Speed adjustment (1.02x)
        4. Saturation/Brightness tweak
        5. FOMO Branding (drawtext) flashing in last 3 seconds
        """
        if not os.path.exists(input_path):
            print(f"❌ Input file not found: {input_path}")
            return False

        duration = await self._get_duration(input_path)
        start_flash_time = max(0, duration - 3.0)

        # Build filter string
        speed_factor = random.choice([0.98, 1.02])
        sat = random.uniform(1.05, 1.15)
        bright = random.uniform(0.01, 0.03)

        # On Windows, need to properly escape the font file or use a generic one if possible
        # We will use a basic drawtext without specific fontfile to rely on defaults, or a standard path.
        font_path = "C\\\\:/Windows/Fonts/arial.ttf" if os.name == 'nt' else "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        
        # Flashing text: "Mua ngay ở Bio - Mã Giảm: FREESHIP"
        # enable condition: greater than start_flash_time AND (mod(t, 0.5) < 0.25) for fast blink
        fomo_text = "Mua ngay o Bio - Ma Giam\: FREESHIP"
        drawtext = f"drawtext=fontfile='{font_path}':text='{fomo_text}':fontcolor=white:fontsize=w/20:box=1:boxcolor=red@0.8:x=(w-text_w)/2:y=h-text_h-50:enable='between(t,{start_flash_time},{duration})*lt(mod(t,0.5),0.25)'"

        filters = [
            f"crop=in_w*0.95:in_h*0.95",
            f"setpts={speed_factor}*PTS",
            f"eq=saturation={sat}:brightness={bright}",
            drawtext
        ]
        
        filter_str = ",".join(filters)

        command = [
            self.ffmpeg_path, "-y",
            "-i", input_path,
            "-vf", filter_str,
            "-af", f"atempo={1/speed_factor}",
            "-c:v", "libx264", "-crf", "18", "-preset", "veryfast",
            "-c:a", "aac", "-b:a", "128k",
            output_path
        ]

        print(f"[Transformer] Applying Async filters (Speed: {1/speed_factor:.2f}x)...")
        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                print(f"✅ Video transformed successfully: {output_path}")
                return True
            else:
                print(f"❌ FFmpeg error: {stderr.decode()}")
                return False
        except Exception as e:
            print(f"❌ Transformation failed: {e}")
            return False

if __name__ == "__main__":
    async def run_test():
        test_in = "data/downloads/test.mp4"
        test_out = "scratch/transformed_test.mp4"
        transformer = VideoTransformer()
        await transformer.apply_bypass_filters(test_in, test_out)
        
    # asyncio.run(run_test())

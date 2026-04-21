import os
import json
from dotenv import load_dotenv

load_dotenv()

class LLMService:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        
    async def generate_caption_variations(self, title: str, description: str) -> list:
        """
        Generates 3 CTA-heavy variations of Title/Hashtag based on TikTok metadata using Gemini API.
        If API key is not set or fails, returns default variations.
        """
        default_variations = [
            f"🔥 {title} #trending #fyp",
            f"😱 Bạn sẽ không tin vào điều này! {title} #viral",
            f"👇 Xem ngay link ở Bio! {title} #foryou"
        ]
        
        if not self.api_key:
            print("⚠️ GEMINI_API_KEY not set. Using default caption variations.")
            return default_variations
            
        import google.generativeai as genai
        try:
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel('gemini-2.5-flash')
            
            prompt = f"""
            You are an expert Social Media Marketer. Based on the following TikTok video metadata, generate 3 highly engaging, Call-to-Action (CTA) heavy caption variations (including hashtags) for a Facebook Reel.
            The captions should trigger FOMO and encourage users to click the affiliate link in the pinned comment or bio.
            
            Video Title: {title}
            Video Description: {description}
            
            Return ONLY a valid JSON array of strings containing the 3 variations. No markdown formatting.
            Example: ["Variation 1", "Variation 2", "Variation 3"]
            """
            
            response = model.generate_content(prompt)
            # Clean up the response text in case it has markdown ticks
            cleaned_text = response.text.replace('```json', '').replace('```', '').strip()
            
            variations = json.loads(cleaned_text)
            if isinstance(variations, list) and len(variations) >= 3:
                return variations[:3]
            else:
                return default_variations
        except Exception as e:
            print(f"❌ LLM API Error: {str(e)}")
            return default_variations

llm_service = LLMService()

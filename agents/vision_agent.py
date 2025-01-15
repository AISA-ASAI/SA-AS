"""Vision agent for analyzing images and screen content."""
import os
import time
from datetime import datetime
from pathlib import Path
import pyautogui
import pytesseract
from PIL import Image
import numpy as np
import base64
import imghdr
from .base_agent import BaseAgent
from config.openai_config import create_image_message
from config.paths_config import get_path
from config.settings import debug_print

SUPPORTED_FORMATS = ['png', 'jpeg', 'jpg', 'gif', 'webp']

VISION_SYSTEM_PROMPT = """You are a specialized Vision Agent that analyzes visual content.
Your tasks include:
1. Analyzing shared images from the user
2. Capturing and analyzing screenshots when requested
3. Extracting text from images using OCR and vision analysis
4. Providing detailed descriptions of visual content
5. Organizing and managing analyzed images
Focus on accurate analysis and clear communication of visual content."""

class VisionAgent(BaseAgent):
    """Agent for analyzing images and screen content."""
    
    def __init__(self):
        """Initialize the Vision Agent."""
        super().__init__(
            agent_type="vision",
            system_prompt=VISION_SYSTEM_PROMPT
        )
        self.screenshots_dir = get_path('screenshots')
        self.shared_dir = get_path('shared_images')
        
        # Ensure directories exist
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.shared_dir.mkdir(parents=True, exist_ok=True)
        
        # Ensure tesseract is available (used as backup for OCR)
        if not self._check_tesseract():
            print("⚠️ Warning: Tesseract OCR not found. Using vision model for text extraction.")
    
    def _check_tesseract(self) -> bool:
        """Check if tesseract is installed and accessible."""
        try:
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False
            
    def _encode_image(self, image_path: str) -> str:
        """Encode image to base64 and ensure it's in a supported format."""
        # Verify file exists and is not empty
        if not os.path.exists(image_path):
            raise ValueError(f"Image file not found: {image_path}")
        
        if os.path.getsize(image_path) == 0:
            raise ValueError(f"Image file is empty: {image_path}")
        
        # Check image format
        img_format = imghdr.what(image_path)
        if not img_format:
            raise ValueError(f"Unable to determine image format for: {image_path}")
            
        if img_format == 'jpeg':
            img_format = 'jpg'
        
        # Try to open and verify the image
        try:
            with Image.open(image_path) as img:
                # Verify image can be loaded
                img.verify()
                # Reset file pointer after verify
                img = Image.open(image_path)
                
                if img_format not in SUPPORTED_FORMATS:
                    # Convert to PNG if not in supported format
                    converted_path = str(Path(image_path).with_suffix('.png'))
                    img.save(converted_path, format='PNG')
                    image_path = converted_path
                    print(f"✓ Converted image to PNG format: {converted_path}")
                
                # Ensure reasonable dimensions
                if img.size[0] * img.size[1] > 25000000:  # Max ~25MP
                    ratio = (25000000 / (img.size[0] * img.size[1])) ** 0.5
                    new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                    img.save(image_path)
                    print(f"✓ Resized image to {new_size}")
                
        except Exception as e:
            raise ValueError(f"Invalid or corrupted image file: {str(e)}")
        
        # Read and encode the image
        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
        except Exception as e:
            raise ValueError(f"Error encoding image: {str(e)}")
    
    async def analyze_image(self, image_path: str, query: str = "") -> str:
        """Analyze a shared image."""
        try:
            try:
                # Verify image can be read and encoded
                encoded_image = self._encode_image(image_path)
            except Exception as e:
                return f"Cannot access/encode image file: {str(e)}"
            
            # Create message content
            content = [
                {
                    "type": "text",
                    "text": query if query else "What do you see in this image? Please provide a detailed description."
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{encoded_image}"
                    }
                }
            ]
            
            messages = [
                {"role": "user", "content": content}
            ]
            
            try:
                # Use base agent's process method with vision model config
                response = await super().process(
                    input_text="",  # Empty input text since we're using messages
                    messages=messages,  # Pass the formatted messages
                    model="gpt-4o-mini",  # Using GPT-4o mini for vision tasks
                    max_tokens=300,
                    response_format={"type": "text"}  # Ensure text response
                )
                return response
            except Exception as e:
                return f"Error during image analysis: {str(e)}"
            
        except Exception as e:
            return f"Error processing image: {str(e)}"
    
    async def capture_screen(self, region=None) -> str:
        """Capture and analyze a screenshot."""
        try:
            # Create timestamp for filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}.png"
            filepath = self.screenshots_dir / filename
            
            # Ensure screenshots directory exists
            self.screenshots_dir.mkdir(parents=True, exist_ok=True)
            
            try:
                # Capture screenshot
                if region:
                    screenshot = pyautogui.screenshot(region=region)
                else:
                    screenshot = pyautogui.screenshot()
                
                # Save screenshot
                screenshot.save(filepath)
                print(f"Screenshot saved to: {filepath}")
            except Exception as e:
                return f"Error capturing screenshot: {str(e)}"
            
            # Analyze the screenshot
            prompt = """Please describe what you see in this screenshot, including:
1. Main content and layout
2. Any visible text or UI elements
3. Important details or information
4. Overall organization and structure"""
            
            return await self.analyze_image(str(filepath), prompt)
            
        except Exception as e:
            return f"Error in screenshot process: {str(e)}" 
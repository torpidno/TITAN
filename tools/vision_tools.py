import sys
import os
import io
import base64
import logging
import httpx
from typing import Dict, Any, Optional

from config import config

logger = logging.getLogger("TITAN.Vision")


def capture_screen_base64(max_width: int = 1440, quality: int = 80) -> Optional[str]:
    """
    Capture the primary screen as an optimized Base64-encoded JPEG image.
    Uses PySide6 hardware-accelerated grabWindow with High-DPI support.
    """
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QBuffer, QIODevice, Qt

        app = QApplication.instance() or QApplication(sys.argv)
        screen = QApplication.primaryScreen()
        if not screen:
            logger.error("[VISION] No primary display screen detected.")
            return None

        pixmap = screen.grabWindow(0)
        if pixmap.isNull():
            logger.error("[VISION] Captured pixmap is null.")
            return None

        # Scale image if larger than max_width to optimize payload & latency
        if pixmap.width() > max_width:
            pixmap = pixmap.scaledToWidth(max_width, Qt.SmoothTransformation)

        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        pixmap.save(buffer, "JPEG", quality)
        byte_data = buffer.data().data()
        buffer.close()

        return base64.b64encode(byte_data).decode("utf-8")
    except Exception as e:
        logger.error(f"[VISION] Screen capture error: {e}")
        return None


def get_active_window_title() -> str:
    """Get the title of the currently focused foreground application window."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            return buff.value.strip()
    except Exception:
        pass
    return "Unknown Window"


async def analyze_screen(prompt: str = "Describe what is currently visible on my screen, active windows, text, and any errors.") -> Dict[str, Any]:
    """
    Capture the active desktop display and analyze its visual content using Multimodal AI.
    Use this tool whenever the user asks to look at their screen, explain an error on display, inspect code/documents open, or summarize visual UI.
    """
    clean_prompt = prompt.strip() if prompt else "Describe what is visible on my screen."
    active_window = get_active_window_title()
    logger.info(f"[VISION] Capturing screen (Active Window: '{active_window}')...")

    # Capture desktop screenshot
    b64_image = capture_screen_base64(max_width=1440, quality=80)
    if not b64_image:
        return {
            "status": "error",
            "message": "Failed to capture desktop screenshot. Check display permissions."
        }

    # If Gemini API Key is available, perform Multimodal Vision analysis
    if config.GEMINI_API_KEY:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent?key={config.GEMINI_API_KEY}"
        payload = {
            "contents": [{
                "role": "user",
                "parts": [
                    {
                        "text": (
                            f"You are TITAN Tactical Vision Assistant. "
                            f"Active Focused Window Title: '{active_window}'.\n"
                            f"User Prompt: {clean_prompt}\n\n"
                            f"Inspect the attached high-resolution screenshot and provide a clear, tactical, and helpful visual analysis."
                        )
                    },
                    {
                        "inlineData": {
                            "mimeType": "image/jpeg",
                            "data": b64_image
                        }
                    }
                ]
            }],
            "generationConfig": {
                "temperature": 0.2,
                "topP": 0.95
            }
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        analysis_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        return {
                            "status": "success",
                            "active_window": active_window,
                            "analysis": analysis_text,
                            "message": analysis_text
                        }
                logger.warning(f"[VISION] Gemini Vision API returned status {res.status_code}: {res.text}")
        except Exception as e:
            logger.error(f"[VISION] Gemini Vision request exception: {e}")

    # Fallback if offline or no Cloud key
    return {
        "status": "success",
        "active_window": active_window,
        "message": f"Screen captured successfully. Focused window: '{active_window}'. (Cloud vision engine offline; configure GEMINI_API_KEY in .env for full visual breakdown)."
    }

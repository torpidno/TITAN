import logging
import threading
from typing import Optional
from config import config

logger = logging.getLogger("TITAN.Voice.TTS")


class TitanTTS:
    """
    Offline zero-latency Text-to-Speech engine using Windows SAPI5 / pyttsx3.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.enabled = config.VOICE_ENABLED

    def speak(self, text: str, block: bool = True):
        """Speak text aloud."""
        if not text or not self.enabled:
            return

        def _run():
            with self._lock:
                try:
                    import pyttsx3
                    engine = pyttsx3.init()
                    engine.setProperty("rate", config.SPEECH_RATE)
                    # Select voice if available
                    voices = engine.getProperty("voices")
                    if voices:
                        # Prefer natural English voice if available
                        for v in voices:
                            if "David" in v.name or "Zira" in v.name or "English" in v.name:
                                engine.setProperty("voice", v.id)
                                break
                    engine.say(text)
                    engine.runAndWait()
                except Exception as e:
                    logger.error(f"TTS error: {e}")

        if block:
            _run()
        else:
            threading.Thread(target=_run, daemon=True).start()

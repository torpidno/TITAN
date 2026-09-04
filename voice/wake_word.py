import time
import logging
import threading
from typing import Callable, Optional
import sounddevice as sd
import numpy as np
from voice.stt import TitanSTT
from config import config

logger = logging.getLogger("TITAN.Voice.WakeWord")


class TitanWakeListener:
    """
    Continuous background wake-word listener for 'TITAN'.
    Listens on default microphone and triggers callback when wake phrase is recognized.
    """

    def __init__(self, on_wake_callback: Callable[[str], None]):
        self.on_wake_callback = on_wake_callback
        self.stt = TitanSTT(model_size="tiny.en")
        self.wake_word = config.WAKE_WORD
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self.sample_rate = 16000
        self.chunk_duration = 3.0  # seconds per window

    def start(self):
        """Start background listening thread."""
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        logger.info(f"[WAKE] Wake word listener active. Say '{self.wake_word.upper()}' to trigger.")

    def stop(self):
        """Stop background listening thread."""
        self.running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _listen_loop(self):
        """Continuous audio capture and wake detection."""
        buffer_size = int(self.sample_rate * self.chunk_duration)
        
        while self.running:
            try:
                # Record chunk
                audio_data = sd.rec(
                    buffer_size,
                    samplerate=self.sample_rate,
                    channels=1,
                    dtype="int16"
                )
                sd.wait()

                # Check if audio has energy (not pure silence)
                rms = np.sqrt(np.mean(audio_data.astype(np.float32)**2))
                if rms < 300: # Silence threshold
                    continue

                raw_bytes = audio_data.tobytes()
                transcription = self.stt.transcribe_audio_bytes(raw_bytes, self.sample_rate).lower()

                if self.wake_word in transcription:
                    logger.info(f"[WAKE] Wake word detected: '{transcription}'")
                    # Extract the rest of the command after the wake word if spoken in the same breath
                    command_part = transcription.split(self.wake_word, 1)[-1].strip()
                    self.on_wake_callback(command_part)
                    time.sleep(1.0) # brief cooldown

            except Exception as e:
                logger.error(f"Error in wake listening loop: {e}")
                time.sleep(1.0)

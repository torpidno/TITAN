import io
import wave
import logging
import numpy as np
from typing import Optional

logger = logging.getLogger("TITAN.Voice.STT")


class TitanSTT:
    """
    Local Speech-To-Text engine using faster-whisper.
    """

    def __init__(self, model_size: str = "base.en"):
        self.model_size = model_size
        self._model = None

    def _load_model(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
                logger.info(f"[STT] Loading local Whisper STT model ({self.model_size})...")
                # Use int8 compute type for speed on CPU/NPU
                self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
            except Exception as e:
                logger.error(f"Failed to load WhisperModel: {e}")
                self._model = False
        return self._model

    def transcribe_audio_bytes(self, audio_data: bytes, sample_rate: int = 16000) -> str:
        """Transcribe raw 16kHz PCM audio bytes."""
        model = self._load_model()
        if not model:
            # Fallback to speech_recognition
            return self._fallback_transcribe(audio_data, sample_rate)

        try:
            # Convert PCM bytes to float32 numpy array
            audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
            segments, _ = model.transcribe(audio_np, beam_size=2, language="en")
            text = " ".join([seg.text.strip() for seg in segments]).strip()
            return text
        except Exception as e:
            logger.error(f"Whisper transcription failed: {e}")
            return ""

    def _fallback_transcribe(self, audio_data: bytes, sample_rate: int = 16000) -> str:
        try:
            import speech_recognition as sr
            r = sr.Recognizer()
            audio = sr.AudioData(audio_data, sample_rate, 2)
            return r.recognize_google(audio)
        except Exception as e:
            logger.error(f"Fallback STT failed: {e}")
            return ""

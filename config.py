import os
from pathlib import Path
from dotenv import load_dotenv

# Base Project Paths
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
MEMORY_DIR = DATA_DIR / "memory"
SKILLS_DIR = BASE_DIR / "tools" / "dynamic_skills"
LOGS_DIR = DATA_DIR / "logs"

# Ensure runtime directories exist
for folder in [DATA_DIR, MEMORY_DIR, SKILLS_DIR, LOGS_DIR]:
    folder.mkdir(parents=True, exist_ok=True)

# Load .env file
ENV_FILE = BASE_DIR / ".env"
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)
else:
    load_dotenv()

class Config:
    BASE_DIR: Path = BASE_DIR
    DATA_DIR: Path = DATA_DIR
    MEMORY_DIR: Path = MEMORY_DIR
    SKILLS_DIR: Path = SKILLS_DIR
    LOGS_DIR: Path = LOGS_DIR

    # Google AI Studio API
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    
    # Local NPU / FLM Settings (FastFlowLM)
    LOCAL_MODEL_ENABLED: bool = os.getenv("LOCAL_MODEL_ENABLED", "true").lower() in ("true", "1", "yes")
    LOCAL_MODEL_ENDPOINT: str = os.getenv("LOCAL_MODEL_ENDPOINT", "http://127.0.0.1:52625/v1")
    LOCAL_MODEL_NAME: str = os.getenv("LOCAL_MODEL_NAME", "qwen2.5-it:3b")
    
    # Operational Mode: 'hybrid', 'cloud_only', 'local_only'
    TITAN_MODE: str = os.getenv("TITAN_MODE", "hybrid")
    
    # Sensory & Voice
    WAKE_WORD: str = os.getenv("WAKE_WORD", "titan").lower()
    VOICE_ENABLED: bool = os.getenv("VOICE_ENABLED", "false").lower() in ("true", "1", "yes")
    SPEECH_RATE: int = int(os.getenv("SPEECH_RATE", "175"))
    
    # Memory Database
    DB_PATH: Path = MEMORY_DIR / "titan_memory.db"
    KNOWLEDGE_PATH: Path = MEMORY_DIR / "knowledge_store.json"
    SKILLS_INDEX_PATH: Path = MEMORY_DIR / "skills_index.json"

config = Config()

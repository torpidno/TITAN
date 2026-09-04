import sqlite3
import json
import time
from typing import Any, Dict, List, Optional
from pathlib import Path
from config import config

class TitanMemory:
    """
    Persistent Multi-Tier Memory Subsystem for T.I.T.A.N.
    - Tier 1: Working Memory (active conversation buffer & context scratchpad)
    - Tier 2: Episodic Memory (SQLite database of past interactions, actions & outcomes)
    - Tier 3: Semantic Long-Term Knowledge (persistent facts, preferences, user profiles)
    """

    def __init__(self, db_path: Optional[Path] = None, knowledge_path: Optional[Path] = None):
        self.db_path = db_path or config.DB_PATH
        self.knowledge_path = knowledge_path or config.KNOWLEDGE_PATH
        self.working_memory: List[Dict[str, Any]] = []
        self._init_db()
        self._init_knowledge()

    def _init_db(self):
        """Initialize SQLite database for episodic logs and learned insights."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Episodes / Conversation Logs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    timestamp REAL,
                    role TEXT,
                    content TEXT,
                    tool_calls TEXT,
                    metadata TEXT
                )
            """)
            # Learned Lessons / Insights
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS insights (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    category TEXT,
                    trigger_context TEXT,
                    lesson TEXT,
                    success_rate REAL DEFAULT 1.0,
                    applied_count INTEGER DEFAULT 0
                )
            """)
            # Dynamic Skills Metadata
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS skills (
                    name TEXT PRIMARY KEY,
                    description TEXT,
                    filepath TEXT,
                    created_at REAL,
                    usage_count INTEGER DEFAULT 0
                )
            """)
            conn.commit()

    def _init_knowledge(self):
        """Initialize JSON-backed semantic knowledge base."""
        if not self.knowledge_path.exists():
            default_knowledge = {
                "user_profile": {
                    "name": "Commander",
                    "preferences": {},
                    "frequent_apps": ["notepad", "explorer", "chrome", "powershell"]
                },
                "system_facts": {
                    "os": "Windows",
                    "hardware": "AMD Ryzen AI 7 350 + Radeon 860M",
                    "npu_supported": True
                },
                "custom_rules": [
                    "Always confirm before deleting system files.",
                    "Provide concise tactical status updates."
                ],
                "saved_facts": []
            }
            self.save_knowledge(default_knowledge)

    # --- Working Memory ---
    def add_working_message(
        self,
        role: str,
        content: str,
        tool_calls: Optional[List[Dict]] = None,
        raw_parts: Optional[List[Any]] = None,
        name: Optional[str] = None,
    ):
        """Append to active conversation window."""
        msg = {"role": role, "content": content}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        if raw_parts:
            msg["raw_parts"] = raw_parts
        if name:
            msg["name"] = name
        self.working_memory.append(msg)

    def get_working_messages(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self.working_memory[-limit:]

    def clear_working_memory(self):
        self.working_memory = []

    # --- Episodic Memory ---
    def record_episode(self, session_id: str, role: str, content: str, tool_calls: Optional[List[Dict]] = None, metadata: Optional[Dict] = None):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO episodes (session_id, timestamp, role, content, tool_calls, metadata) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    time.time(),
                    role,
                    content,
                    json.dumps(tool_calls) if tool_calls else None,
                    json.dumps(metadata) if metadata else None
                )
            )
            conn.commit()

    def search_episodes(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search past episodic logs using simple text matching."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM episodes WHERE content LIKE ? ORDER BY timestamp DESC LIMIT ?",
                (f"%{query}%", limit)
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    # --- Semantic Knowledge Store ---
    def load_knowledge(self) -> Dict[str, Any]:
        try:
            with open(self.knowledge_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save_knowledge(self, data: Dict[str, Any]):
        with open(self.knowledge_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def remember_fact(self, fact: str, category: str = "general"):
        """Save a new permanent fact or preference."""
        data = self.load_knowledge()
        if "saved_facts" not in data:
            data["saved_facts"] = []
        data["saved_facts"].append({
            "fact": fact,
            "category": category,
            "timestamp": time.time()
        })
        self.save_knowledge(data)

    def get_all_facts(self) -> List[Dict[str, Any]]:
        data = self.load_knowledge()
        return data.get("saved_facts", [])

    # --- Insights & Learnings ---
    def record_insight(self, category: str, trigger_context: str, lesson: str):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO insights (timestamp, category, trigger_context, lesson) VALUES (?, ?, ?, ?)",
                (time.time(), category, trigger_context, lesson)
            )
            conn.commit()

    def get_recent_insights(self, limit: int = 10) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM insights ORDER BY timestamp DESC LIMIT ?", (limit,))
            return [dict(r) for r in cursor.fetchall()]

    def format_memory_for_prompt(self) -> str:
        """Render relevant facts, user preferences, and top insights into system prompt context."""
        knowledge = self.load_knowledge()
        user_prof = knowledge.get("user_profile", {})
        facts = knowledge.get("saved_facts", [])[-5:] # latest 5 facts
        rules = knowledge.get("custom_rules", [])
        insights = self.get_recent_insights(limit=3)

        lines = ["=== T.I.T.A.N. PERSISTENT KNOWLEDGE BASE ==="]
        lines.append(f"User: {user_prof.get('name', 'Commander')}")
        
        if rules:
            lines.append("Operating Rules:")
            for r in rules:
                lines.append(f" - {r}")
                
        if facts:
            lines.append("Known Facts & Preferences:")
            for f in facts:
                lines.append(f" - [{f.get('category', 'general')}] {f.get('fact')}")

        if insights:
            lines.append("Learned Insights from Past Experience:")
            for ins in insights:
                lines.append(f" - {ins.get('lesson')}")

        lines.append("============================================")
        return "\n".join(lines)

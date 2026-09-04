import asyncio
import json
import unittest
from pathlib import Path
from config import config
from core.memory import TitanMemory
from core.learning import TitanLearner
from tools.registry import ToolRegistry
from tools.system_tools import get_system_stats, execute_powershell

class TestTitanCore(unittest.TestCase):

    def setUp(self):
        self.memory = TitanMemory()
        self.tools = ToolRegistry(memory_instance=self.memory)
        self.learner = TitanLearner(memory=self.memory, tool_registry=self.tools)

    def test_memory_storage_and_recall(self):
        """Test persistent memory storage and retrieval."""
        test_fact = "User prefers dark mode and tactical UI."
        self.memory.remember_fact(test_fact, category="preferences")
        
        facts = self.memory.get_all_facts()
        self.assertTrue(any(f.get("fact") == test_fact for f in facts))
        
        prompt_text = self.memory.format_memory_for_prompt()
        self.assertIn(test_fact, prompt_text)
        print("[OK] Memory Subsystem validated.")

    def test_episodic_database(self):
        """Test SQLite episodic logging."""
        self.memory.record_episode("test-session-1", "user", "Execute diagnostics")
        episodes = self.memory.search_episodes("diagnostics")
        self.assertTrue(len(episodes) > 0)
        self.assertEqual(episodes[0]["session_id"], "test-session-1")
        print("[OK] Episodic SQLite Database validated.")

    def test_system_stats_and_powershell(self):
        """Test Windows system metric extraction and PowerShell execution."""
        stats = get_system_stats()
        self.assertIn("cpu_usage_percent", stats)
        self.assertIn("ram_percent", stats)
        
        ps_res = execute_powershell("Write-Output 'TITAN_ONLINE'")
        self.assertTrue(ps_res["success"])
        self.assertIn("TITAN_ONLINE", ps_res["stdout"])
        print("[OK] Windows OS System Tools validated.")

    def test_skill_synthesis_and_hot_reload(self):
        """Test self-reflection and dynamic skill synthesis."""
        skill_name = "test_ping_localhost"
        res = self.learner.synthesize_skill(
            name=skill_name,
            description="Ping localhost to verify network connectivity.",
            parameters={"type": "object", "properties": {}},
            code_body="return {'status': 'success', 'ping': 'pong'}"
        )
        self.assertEqual(res["status"], "success")
        
        # Verify tool is registered in registry
        self.assertIn(skill_name, self.tools.tools)
        
        # Execute the new skill directly
        skill_output = self.tools.tools[skill_name]()
        self.assertEqual(skill_output.get("ping"), "pong")

        # Cleanup test skill file to avoid polluting user tools
        test_file = config.SKILLS_DIR / f"{skill_name}.py"
        if test_file.exists():
            test_file.unlink()
        self.tools.reload_dynamic_skills()

        print("[OK] Dynamic Skill Synthesis & Hot-Reload validated.")

    def test_git_versioning_and_evolution(self):
        """Test Git version control, status, and code inspection."""
        from core.evolution import GitVersionManager, CodeEvolutionEngine
        git_mgr = GitVersionManager()
        status = git_mgr.get_status()
        self.assertTrue("branch" in status)
        
        history = git_mgr.get_history(limit=3)
        self.assertTrue(len(history) > 0)
        
        engine = CodeEvolutionEngine(memory=self.memory)
        res = engine.inspect_file("config.py")
        self.assertEqual(res["status"], "success")
        self.assertIn("class Config:", res["content"])
        print("[OK] Git Versioning & Code Inspection validated.")

    def test_screen_capture_and_vision_tool(self):
        """Test Screen Capture & Multimodal Vision tool."""
        from tools.vision_tools import capture_screen_base64, get_active_window_title
        b64 = capture_screen_base64(max_width=800, quality=50)
        self.assertIsNotNone(b64)
        self.assertTrue(len(b64) > 100)
        
        window_title = get_active_window_title()
        self.assertIsInstance(window_title, str)
        print("[OK] Screen Perception & Multimodal Vision Subsystem validated.")

if __name__ == "__main__":
    unittest.main()

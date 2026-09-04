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
        print("[OK] Dynamic Skill Synthesis & Hot-Reload validated.")

if __name__ == "__main__":
    unittest.main()

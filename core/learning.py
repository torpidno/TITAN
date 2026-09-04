import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from config import config
from core.memory import TitanMemory

logger = logging.getLogger("TITAN.Learning")

SKILL_TEMPLATE = """# Dynamic Skill: {name}
# Synthesized by T.I.T.A.N. Auto-Learning Engine
import subprocess
import psutil
from typing import Dict, Any

SKILL_METADATA = {{
    "name": "{name}",
    "description": "{description}",
    "parameters": {parameters_json}
}}

def run_skill({param_args}) -> Dict[str, Any]:
    \"\"\"
    {description}
    \"\"\"
{code_body}
"""


class TitanLearner:
    """
    Continuous Learning & Self-Reflection System for T.I.T.A.N.
    - Synthesizes and hot-reloads new Python skills
    - Extracts lessons & insights from user feedback or execution errors
    - Maintains an evolving procedural skill library
    """

    def __init__(self, memory: TitanMemory, tool_registry):
        self.memory = memory
        self.tools = tool_registry

    def synthesize_skill(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        code_body: str,
        param_args: str = "**kwargs",
    ) -> Dict[str, Any]:
        """
        Synthesize a new Python skill, write it to disk, and register it dynamically.
        """
        clean_name = name.lower().replace(" ", "_").replace("-", "_")
        target_path = config.SKILLS_DIR / f"{clean_name}.py"

        # Format indented code body
        indented_code = "\n".join(f"    {line}" if line.strip() else "" for line in code_body.strip().split("\n"))
        
        file_content = SKILL_TEMPLATE.format(
            name=clean_name,
            description=description,
            parameters_json=json.dumps(parameters, indent=8),
            param_args=param_args,
            code_body=indented_code,
        )

        try:
            target_path.write_text(file_content, encoding="utf-8")
            # Hot reload skills in registry
            self.tools.reload_dynamic_skills()
            
            # Record insight
            self.memory.record_insight(
                category="skill_creation",
                trigger_context=f"Created skill: {clean_name}",
                lesson=f"Synthesized skill '{clean_name}': {description}"
            )

            # Auto-commit and push skill to GitHub
            from core.evolution import GitVersionManager
            git_mgr = GitVersionManager()
            checkpoint = git_mgr.create_checkpoint(f"Learned dynamic skill: {clean_name}", auto_push=True)
            
            logger.info(f"[SKILL] Successfully synthesized skill: {clean_name} -> {target_path} (Git: {checkpoint.get('commit_hash', 'local')})")
            return {
                "status": "success",
                "message": f"Skill '{clean_name}' successfully learned, activated, and synced to Git.",
                "filepath": str(target_path),
                "commit_hash": checkpoint.get("commit_hash", "")
            }
        except Exception as e:
            logger.error(f"Failed to synthesize skill: {e}")
            return {"status": "error", "message": f"Failed to synthesize skill: {str(e)}"}

    def reflect_on_error(self, tool_name: str, error_msg: str, context: str):
        """Analyze a failure and record a learning insight to prevent repeating it."""
        lesson = f"When using '{tool_name}' for context '{context}', error encountered: '{error_msg}'. Ensure parameters and prerequisites are validated."
        self.memory.record_insight(
            category="error_recovery",
            trigger_context=f"{tool_name}: {context}",
            lesson=lesson
        )
        logger.info(f"[INSIGHT] Logged insight: {lesson}")

    def list_learned_skills(self) -> List[Dict[str, Any]]:
        """List all synthesized dynamic skills."""
        skills = []
        for file in config.SKILLS_DIR.glob("*.py"):
            if not file.name.startswith("__"):
                skills.append({
                    "name": file.stem,
                    "filepath": str(file)
                })
        return skills

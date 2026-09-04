import inspect
import importlib.util
import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from tools.system_tools import (
    execute_powershell,
    open_application,
    open_url,
    control_volume,
    get_system_stats,
    file_manager
)
from tools.web_tools import search_web, fetch_webpage
from tools.vision_tools import analyze_screen
from config import config

logger = logging.getLogger("TITAN.Tools")


class ToolRegistry:
    """
    Central Tool Registry supporting static built-in tools and dynamic learned skills.
    """

    def __init__(self, memory_instance=None):
        self.memory = memory_instance
        self.tools: Dict[str, Callable] = {}
        self.schemas: List[Dict[str, Any]] = []
        self._register_builtins()
        self.reload_dynamic_skills()

    def register(self, name: str, description: str, parameters: Dict[str, Any], func: Callable):
        """Register a tool with its JSON schema and execution callback."""
        self.tools[name] = func
        # Update or add schema
        self.schemas = [s for s in self.schemas if s["name"] != name]
        self.schemas.append({
            "name": name,
            "description": description,
            "parameters": parameters
        })

    def _register_builtins(self):
        # 1. PowerShell Execution
        self.register(
            name="execute_powershell",
            description="Run a Windows PowerShell command or script to automate tasks, check processes, inspect files, or control Windows.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The exact PowerShell command line to execute."
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "description": "Timeout in seconds. Default 20."
                    }
                },
                "required": ["command"]
            },
            func=execute_powershell
        )

        # 2. Open Application
        self.register(
            name="open_application",
            description="Launch a desktop app or Windows shortcut like 'notepad', 'calc', 'chrome', 'spotify', 'steam', 'discord', 'explorer', 'settings'.",
            parameters={
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "Name or executable of the application to open."
                    }
                },
                "required": ["app_name"]
            },
            func=open_application
        )

        # 2.5 Open URL or Website / Wiki
        self.register(
            name="open_url",
            description="Open a website, URL, or wiki/topic in the user's default web browser (e.g. 'valheim wiki', 'https://github.com', 'youtube.com'). Use this whenever asked to open or browse a website, wiki, or web page.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL, domain, or search topic (e.g. 'valheim wiki', 'https://reddit.com') to open in browser."
                    }
                },
                "required": ["url"]
            },
            func=open_url
        )

        # 3. Control Volume
        self.register(
            name="control_volume",
            description="Control or query Windows master audio volume.",
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["set", "mute", "unmute", "get"],
                        "description": "Audio action to perform."
                    },
                    "level": {
                        "type": "integer",
                        "description": "Volume percentage from 0 to 100 (used when action is 'set')."
                    }
                },
                "required": ["action"]
            },
            func=control_volume
        )

        # 4. System Stats
        self.register(
            name="get_system_stats",
            description="Get real-time CPU, RAM, Battery, and Disk usage on this laptop.",
            parameters={
                "type": "object",
                "properties": {}
            },
            func=get_system_stats
        )

        # 5. File Manager
        self.register(
            name="file_manager",
            description="Perform file operations: 'read', 'write', 'list', 'exists', 'mkdir'.",
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["read", "write", "list", "exists", "mkdir"],
                        "description": "Operation type."
                    },
                    "path": {
                        "type": "string",
                        "description": "File or folder path."
                    },
                    "content": {
                        "type": "string",
                        "description": "Text content (required when action is 'write')."
                    }
                },
                "required": ["action", "path"]
            },
            func=file_manager
        )

        # 6. Web Search
        self.register(
            name="search_web",
            description="Perform a live web search for fresh information, news, documentation, or solutions.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query terms."
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Number of results to return (default 5)."
                    }
                },
                "required": ["query"]
            },
            func=search_web
        )

        # 7. Fetch Webpage
        self.register(
            name="fetch_webpage",
            description="Read content from a specific web URL.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to fetch."
                    }
                },
                "required": ["url"]
            },
            func=fetch_webpage
        )

        # 7.5 Screen Perception & Multimodal Vision
        self.register(
            name="analyze_screen",
            description="Capture the user's active monitor display and perform AI visual perception/analysis. Use when asked to look at screen, inspect errors, summarize open documents, or describe visual UI.",
            parameters={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "What specific question or instruction to inspect on screen (e.g. 'explain this error', 'summarize this article', 'what is on screen')."
                    }
                },
                "required": []
            },
            func=analyze_screen
        )

        # 8. Remember Fact (Memory)
        if self.memory:
            self.register(
                name="remember_fact",
                description="Persistently store a user preference, habit, system fact, or custom rule into TITAN's long-term memory.",
                parameters={
                    "type": "object",
                    "properties": {
                        "fact": {
                            "type": "string",
                            "description": "The fact or preference to remember permanently."
                        },
                        "category": {
                            "type": "string",
                            "description": "Category (e.g. 'preference', 'hardware', 'work', 'personal')."
                        }
                    },
                    "required": ["fact"]
                },
                func=lambda fact, category="general": self.memory.remember_fact(fact, category) or {"status": "success", "message": f"Remembered: {fact}"}
            )

    def reload_dynamic_skills(self):
        """Scan tools/dynamic_skills directory and dynamically import user/agent-created skills."""
        skills_dir = config.SKILLS_DIR
        if not skills_dir.exists():
            return

        for file in skills_dir.glob("*.py"):
            if file.name.startswith("__"):
                continue
            try:
                module_name = f"dynamic_skill_{file.stem}"
                spec = importlib.util.spec_from_file_location(module_name, str(file))
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    
                    # Look for export metadata
                    if hasattr(mod, "SKILL_METADATA") and hasattr(mod, "run_skill"):
                        meta = mod.SKILL_METADATA
                        self.register(
                            name=meta.get("name", file.stem),
                            description=meta.get("description", "Dynamic TITAN Skill"),
                            parameters=meta.get("parameters", {"type": "object", "properties": {}}),
                            func=mod.run_skill
                        )
                        logger.info(f"[SKILL] Loaded dynamic skill: {meta.get('name', file.stem)}")
            except Exception as e:
                logger.error(f"Failed to load dynamic skill {file.name}: {e}")

    async def execute_tool(self, name: str, args: Dict[str, Any]) -> Any:
        """Execute a tool by name with arguments (supporting async & sync callables)."""
        if name not in self.tools:
            return {"status": "error", "message": f"Tool '{name}' is not registered."}
        
        func = self.tools[name]
        try:
            if inspect.iscoroutinefunction(func):
                result = await func(**args)
            else:
                result = func(**args)
            return result
        except Exception as e:
            logger.error(f"Error executing tool '{name}': {e}", exc_info=True)
            return {"status": "error", "message": f"Tool execution failed: {str(e)}"}

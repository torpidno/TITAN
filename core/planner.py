import json
import logging
import uuid
from typing import Dict, Any, List, Optional
from core.brain import HybridBrain
from core.memory import TitanMemory
from core.learning import TitanLearner
from tools.registry import ToolRegistry

logger = logging.getLogger("TITAN.Planner")

SYSTEM_PROMPT = """You are T.I.T.A.N. (Tactical Interface for Task Automation & Navigation), an advanced AI agent operating locally on the user's laptop (AMD Ryzen AI + Windows).

You have full tactical capabilities to:
1. Control and automate the Windows operating system (open applications, manage files, adjust system audio, run PowerShell commands, check hardware stats).
2. Browse the web, perform real-time searches, and extract information.
3. Access and update your persistent long-term memory (remembering user preferences, personal facts, and past interactions).
4. Learn new skills dynamically by writing Python modules for yourself using the 'learn_new_skill' tool.

Operational Directives:
- Be concise, tactical, sharp, and helpful.
- When the user asks you to perform an action on their PC, use your available tools immediately.
- When the user teaches you something or asks you to learn a habit, use 'remember_fact' or 'learn_new_skill'.
- If a command or tool fails, reflect on the error and try an alternative approach.

{memory_context}
"""


class TitanAgent:
    """
    Tactical Autonomous Agent Loop orchestrating Brain, Memory, Tools, and Learning.
    """

    def __init__(self):
        self.brain = HybridBrain()
        self.memory = TitanMemory()
        self.tools = ToolRegistry(memory_instance=self.memory)
        self.learner = TitanLearner(memory=self.memory, tool_registry=self.tools)
        self._register_meta_tools()
        self.session_id = str(uuid.uuid4())[:8]

    def _register_meta_tools(self):
        """Register agent self-modification & learning meta-tools."""
        self.tools.register(
            name="learn_new_skill",
            description="Synthesize and save a brand-new executable Python skill that becomes a permanent tool in TITAN's toolset.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Unique identifier for the new skill (e.g. 'lock_workstation', 'cleanup_temp_files')."
                    },
                    "description": {
                        "type": "string",
                        "description": "Clear explanation of what the skill does."
                    },
                    "parameters": {
                        "type": "object",
                        "description": "JSON schema definition of the input parameters."
                    },
                    "code_body": {
                        "type": "string",
                        "description": "Python code body for the function. Return a dictionary with 'status' and 'message'."
                    },
                    "param_args": {
                        "type": "string",
                        "description": "Function signature arguments, e.g. 'target_dir: str, dry_run: bool = False'."
                    }
                },
                "required": ["name", "description", "parameters", "code_body"]
            },
            func=self.learner.synthesize_skill
        )

    async def process_user_input(
        self,
        user_input: str,
        on_thought: Optional[callable] = None,
        on_tool_start: Optional[callable] = None,
        on_tool_end: Optional[callable] = None,
    ) -> str:
        """
        Main execution loop for user commands.
        Handles multi-turn ReAct tool execution until final answer is reached.
        """
        # Record user input in working and episodic memory
        self.memory.add_working_message("user", user_input)
        self.memory.record_episode(self.session_id, "user", user_input)

        system_instruction = SYSTEM_PROMPT.format(
            memory_context=self.memory.format_memory_for_prompt()
        )

        max_turns = 6
        current_turn = 0
        final_response = ""
        last_provider = "local_flm"
        force_cloud = False
        executed_sigs = set()

        while current_turn < max_turns:
            current_turn += 1
            messages = self.memory.get_working_messages(limit=10)

            # Query Brain (Local NPU first with smart Cloud escalation)
            response = await self.brain.generate_response(
                messages=messages,
                system_instruction=system_instruction,
                tools=self.schemas(),
                force_cloud=force_cloud
            )

            last_provider = response.get("provider", "local_flm")
            if last_provider == "gemini":
                force_cloud = True  # Maintain cloud engine for the remainder of this multi-step task
            response_text = response.get("text")
            tool_calls = response.get("tool_calls", [])

            if response_text and on_thought and not tool_calls:
                on_thought(response_text)

            # If no tool calls requested, we have the final answer
            if not tool_calls:
                final_response = response_text or "Task completed, Commander."
                self.memory.add_working_message("model", final_response)
                self.memory.record_episode(self.session_id, "model", final_response)
                break

            # Deduplicate against tools already executed in this interaction
            new_tool_calls = []
            for tc in tool_calls:
                t_name = tc.get("name")
                t_args = tc.get("args", {})
                sig = f"{t_name}:{json.dumps(t_args, sort_keys=True)}"
                if sig not in executed_sigs:
                    new_tool_calls.append(tc)

            if not new_tool_calls:
                clean_txt = (response_text or "").strip()
                if clean_txt and not clean_txt.startswith(("{", "'", '"', "[", "open_", "search_")):
                    final_response = clean_txt
                else:
                    final_response = "All requested applications and actions have been executed, Commander."
                self.memory.add_working_message("model", final_response)
                self.memory.record_episode(self.session_id, "model", final_response)
                break

            # Record model's functionCall turn
            self.memory.add_working_message(
                role="model",
                content=response_text or "",
                tool_calls=new_tool_calls,
                raw_parts=response.get("raw_parts")
            )

            # Execute Tool Calls
            for tc in new_tool_calls:
                tool_name = tc.get("name")
                tool_args = tc.get("args", {})
                tool_sig = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"
                executed_sigs.add(tool_sig)

                if on_tool_start:
                    on_tool_start(tool_name, tool_args)

                tool_result = await self.tools.execute_tool(tool_name, tool_args)
                
                if on_tool_end:
                    on_tool_end(tool_name, tool_result)

                # Record tool execution in memory
                self.memory.add_working_message(
                    role="tool",
                    content=json.dumps(tool_result),
                    name=tool_name
                )
                self.memory.record_episode(
                    self.session_id,
                    "tool",
                    json.dumps(tool_result),
                    tool_calls=[tc],
                    metadata={"tool_name": tool_name, "sig": tool_sig}
                )

                # Check if tool resulted in an error to trigger reflection
                if isinstance(tool_result, dict) and tool_result.get("status") == "error":
                    self.learner.reflect_on_error(
                        tool_name=tool_name,
                        error_msg=tool_result.get("message", "Unknown failure"),
                        context=user_input
                    )

        return {"text": final_response, "provider": last_provider}

    def schemas(self) -> List[Dict[str, Any]]:
        return self.tools.schemas

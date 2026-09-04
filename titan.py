import asyncio
import sys
import os
import argparse

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from core.planner import TitanAgent
from voice.tts import TitanTTS
from voice.wake_word import TitanWakeListener
from ui.terminal_ui import TitanTerminalUI, console
from config import config

class TitanApplication:
    """
    Main Application Manager for T.I.T.A.N.
    """

    def __init__(self, enable_voice: bool = False):
        self.agent = TitanAgent()
        self.tts = TitanTTS()
        self.voice_enabled = enable_voice or config.VOICE_ENABLED
        self.wake_listener = None
        self.loop = None

    def start_voice_listener(self):
        """Start the background wake word detector."""
        if not self.wake_listener:
            def handle_wake_command(command: str):
                if not command:
                    self.tts.speak("TITAN online. How can I assist you, Commander?")
                    return
                # Schedule processing on asyncio loop
                if self.loop and self.loop.is_running():
                    asyncio.run_coroutine_threadsafe(self.process_command(command), self.loop)

            self.wake_listener = TitanWakeListener(on_wake_callback=handle_wake_command)
            self.wake_listener.start()
            TitanTerminalUI.print_info("[VOICE] Wake-word listener activated ('TITAN')")

    def stop_voice_listener(self):
        if self.wake_listener:
            self.wake_listener.stop()
            self.wake_listener = None
            TitanTerminalUI.print_info("Voice wake-word listener deactivated.")

    async def process_command(self, user_text: str):
        """Execute a user query through the agent."""
        if not user_text.strip():
            return

        TitanTerminalUI.print_user_query(user_text)

        result = await self.agent.process_user_input(
            user_input=user_text,
            on_thought=TitanTerminalUI.print_thought,
            on_tool_start=TitanTerminalUI.print_tool_start,
            on_tool_end=TitanTerminalUI.print_tool_end,
        )

        response_text = result.get("text", "") if isinstance(result, dict) else str(result)
        provider = result.get("provider", "local_flm") if isinstance(result, dict) else "local_flm"

        TitanTerminalUI.print_response(response_text, provider=provider)
        
        if self.voice_enabled:
            # Speak response
            self.tts.speak(response_text, block=False)

    async def run_interactive_cli(self):
        """Interactive terminal CLI loop."""
        self.loop = asyncio.get_running_loop()
        TitanTerminalUI.print_banner()

        if self.voice_enabled:
            self.start_voice_listener()

        console.print("[dim]Type a command, or [bold]/help[/bold] for shortcuts, or [bold]/exit[/bold] to quit.[/dim]\n")

        try:
            from prompt_toolkit import PromptSession
            from prompt_toolkit.formatted_text import HTML
            from prompt_toolkit.history import InMemoryHistory
            session = PromptSession(history=InMemoryHistory())
            use_prompt_toolkit = True
        except Exception:
            session = None
            use_prompt_toolkit = False

        while True:
            try:
                if use_prompt_toolkit and session:
                    user_input = await session.prompt_async(
                        HTML("<ansigreen><b>Commander ></b></ansigreen> ")
                    )
                else:
                    user_input = await asyncio.to_thread(input, "Commander > ")

                user_input = user_input.strip()
                if not user_input:
                    continue

                # Slash Command Handlers
                if user_input.startswith("/"):
                    cmd = user_input.lower().split()[0]
                    if cmd in ("/exit", "/quit", "/q"):
                        TitanTerminalUI.print_info("Powering down T.I.T.A.N. systems. Goodbye Commander.")
                        break
                    elif cmd in ("/help", "/h"):
                        self._show_help()
                        continue
                    elif cmd in ("/stats", "/status"):
                        TitanTerminalUI.print_status_bar()
                        continue
                    elif cmd in ("/memory", "/mem"):
                        facts = self.agent.memory.get_all_facts()
                        TitanTerminalUI.print_memory(facts)
                        continue
                    elif cmd in ("/skills", "/tools"):
                        skills = self.agent.learner.list_learned_skills()
                        TitanTerminalUI.print_skills(skills)
                        continue
                    elif cmd in ("/history", "/evolve", "/git"):
                        history = self.agent.evolution.git.get_history(limit=8)
                        TitanTerminalUI.print_history(history)
                        continue
                    elif cmd == "/rollback":
                        parts = user_input.split()
                        steps = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
                        res = self.agent.evolution.git.rollback(steps=steps)
                        if res["success"]:
                            TitanTerminalUI.print_info(res["message"])
                        else:
                            TitanTerminalUI.print_error(res["message"])
                        continue
                    elif cmd == "/voice":
                        self.voice_enabled = not self.voice_enabled
                        config.VOICE_ENABLED = self.voice_enabled
                        if self.voice_enabled:
                            self.start_voice_listener()
                        else:
                            self.stop_voice_listener()
                        continue
                    elif cmd == "/clear":
                        self.agent.memory.clear_working_memory()
                        TitanTerminalUI.print_info("Working memory buffer cleared.")
                        continue
                    else:
                        TitanTerminalUI.print_error(f"Unknown shortcut: {cmd}. Type /help for options.")
                        continue

                await self.process_command(user_input)

            except (KeyboardInterrupt, EOFError):
                TitanTerminalUI.print_info("\nShutdown signal received.")
                break
            except Exception as e:
                TitanTerminalUI.print_error(f"Execution error: {e}")

        self.stop_voice_listener()

    def _show_help(self):
        console.print("""
[bold cyan]T.I.T.A.N. Quick Commands:[/bold cyan]
  [yellow]/help[/yellow]       - Show this help manual
  [yellow]/stats[/yellow]      - Display live CPU, RAM, and Battery metrics
  [yellow]/memory[/yellow]     - View persistent knowledge and saved facts
  [yellow]/skills[/yellow]     - View dynamic learned procedural skills
  [yellow]/history[/yellow]    - View autonomous code evolution & Git version history
  [yellow]/rollback[/yellow]   - Rollback codebase to previous Git commit (e.g. /rollback or /rollback 2)
  [yellow]/voice[/yellow]      - Toggle voice wake word and speech synthesizer
  [yellow]/clear[/yellow]      - Reset current conversation context
  [yellow]/exit[/yellow]       - Safely shutdown T.I.T.A.N.

[bold cyan]Example Natural Language Commands:[/bold cyan]
  - "Open chrome and search for quantum computing breakthroughs"
  - "Set volume to 50% and open Spotify"
  - "Check how much free disk space and RAM I have"
  - "Remember that my favorite code editor is VS Code"
  - "Learn a new skill called 'open_downloads' to open my Downloads folder"
  - "Inspect tools/system_tools.py and add a new tool to minimize all windows"
""")


def main():
    parser = argparse.ArgumentParser(description="T.I.T.A.N. - Tactical Interface for Task Automation & Navigation")
    parser.add_argument("--voice", action="store_true", help="Enable voice wake word & TTS at launch")
    parser.add_argument("--hud", action="store_true", help="Launch Cyberpunk Desktop Floating HUD Overlay GUI")
    parser.add_argument("--cloud-only", action="store_true", help="Force cloud Gemini model only")
    parser.add_argument("--local-only", action="store_true", help="Force local NPU/FLM model only")
    args = parser.parse_args()

    if args.cloud_only:
        config.TITAN_MODE = "cloud_only"
    elif args.local_only:
        config.TITAN_MODE = "local_only"

    if args.hud:
        from ui.hud_window import launch_hud
        launch_hud(enable_voice=args.voice)
        return

    app = TitanApplication(enable_voice=args.voice)
    try:
        asyncio.run(app.run_interactive_cli())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

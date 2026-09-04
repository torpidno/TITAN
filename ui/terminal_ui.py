import sys
import os
import psutil

# Ensure UTF-8 output encoding on Windows consoles
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

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from rich import box
from config import config

console = Console(force_terminal=True, highlight=False, legacy_windows=False)

BANNER = """
[bold cyan] _____ ___ _____  _    _   _ [/bold cyan]
[bold cyan]|_   _|_ _|_   _|/ \  | \ | |[/bold cyan]
[bold cyan]  | |  | |  | | / _ \ |  \| |[/bold cyan]
[bold cyan]  | |  | |  | |/ ___ \| |\  |[/bold cyan]
[bold cyan]  |_| |___| |_/_/   \_\_| \_|[/bold cyan]
[dim cyan]Tactical Interface for Task Automation & Navigation[/dim cyan]
"""

class TitanTerminalUI:
    """
    Rich Tactical Terminal User Interface for T.I.T.A.N.
    """

    @staticmethod
    def print_banner():
        try:
            console.print(BANNER)
        except Exception:
            print("\n=== T.I.T.A.N. (Tactical Interface for Task Automation & Navigation) ===\n")
        TitanTerminalUI.print_status_bar()

    @staticmethod
    def print_status_bar():
        try:
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent
            battery = psutil.sensors_battery()
            bat_str = f"{battery.percent}%" if battery else "N/A"
            
            status_table = Table(show_header=False, box=None, padding=(0, 2))
            status_table.add_row(
                f"[bold green]* SYSTEM ONLINE[/bold green]",
                f"[yellow]MODE:[/] {config.TITAN_MODE.upper()}",
                f"[blue]CPU:[/] {cpu}%",
                f"[magenta]RAM:[/] {ram}%",
                f"[cyan]BAT:[/] {bat_str}",
                f"[bold red]WAKE:[/] '{config.WAKE_WORD.upper()}'"
            )
            console.print(Panel(status_table, box=box.ASCII, style="dim white", border_style="cyan"))
        except Exception as e:
            print(f"[SYSTEM ONLINE] MODE: {config.TITAN_MODE.upper()}")

    @staticmethod
    def print_user_query(text: str):
        try:
            console.print(f"\n[bold green]Commander >[/bold green] [white]{text}[/white]")
        except Exception:
            print(f"\nCommander > {text}")

    @staticmethod
    def print_tool_start(tool_name: str, args: dict):
        try:
            args_str = ", ".join(f"{k}={repr(v)}" for k, v in args.items())
            console.print(f"  [bold yellow][EXEC][/bold yellow] [bold white]{tool_name}[/bold white]({args_str})")
        except Exception:
            print(f"  [EXEC] {tool_name}({args})")

    @staticmethod
    def print_tool_end(tool_name: str, result: any):
        try:
            res_str = str(result)
            if len(res_str) > 160:
                res_str = res_str[:160] + "..."
            console.print(f"  [bold green][DONE][/bold green] {res_str}")
        except Exception:
            print(f"  [DONE] {str(result)[:100]}")

    @staticmethod
    def print_thought(text: str):
        try:
            console.print(f"  [dim cyan]> {text}[/dim cyan]")
        except Exception:
            print(f"  > {text}")

    @staticmethod
    def print_response(text: str, provider: str = "local_flm"):
        try:
            badge = "[bold green][LOCAL NPU][/bold green]" if provider == "local_flm" else "[bold magenta][CLOUD GEMINI][/bold magenta]"
            console.print(f"\n[bold cyan]T.I.T.A.N. {badge} >[/bold cyan]")
            console.print(Markdown(text))
            console.print()
        except Exception:
            print(f"\nT.I.T.A.N. [{provider}] >\n{text}\n")

    @staticmethod
    def print_info(msg: str):
        try:
            console.print(f"[bold blue][INFO][/bold blue] {msg}")
        except Exception:
            print(f"[INFO] {msg}")

    @staticmethod
    def print_error(msg: str):
        try:
            console.print(f"[bold red][ERROR][/bold red] {msg}")
        except Exception:
            print(f"[ERROR] {msg}")

    @staticmethod
    def print_skills(skills: list):
        try:
            table = Table(title="[bold cyan]Dynamic Learned Skills[/bold cyan]", box=box.ASCII)
            table.add_column("Skill Name", style="bold green")
            table.add_column("File Path", style="dim white")
            for s in skills:
                table.add_row(s["name"], s["filepath"])
            console.print(table)
        except Exception:
            print("Learned Skills:", skills)

    @staticmethod
    def print_memory(facts: list):
        try:
            table = Table(title="[bold cyan]Persistent Long-Term Memory[/bold cyan]", box=box.ASCII)
            table.add_column("Category", style="yellow")
            table.add_column("Fact / Preference", style="white")
            for f in facts:
                table.add_row(f.get("category", "general"), f.get("fact", ""))
            console.print(table)
        except Exception:
            print("Memory Facts:", facts)

    @staticmethod
    def print_history(history: list):
        try:
            table = Table(title="[bold cyan]Code Evolution & Git Version History[/bold cyan]", box=box.ASCII)
            table.add_column("Commit", style="bold yellow")
            table.add_column("Time", style="dim cyan")
            table.add_column("Author", style="dim white")
            table.add_column("Changelog / Evolution", style="white")
            for h in history:
                table.add_row(h.get("hash", ""), h.get("time", ""), h.get("author", ""), h.get("message", ""))
            console.print(table)
        except Exception:
            print("Git History:", history)

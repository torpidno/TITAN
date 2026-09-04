import os
import subprocess
import shutil
import psutil
from pathlib import Path
from typing import Dict, Any, Optional

def execute_powershell(command: str, timeout_seconds: int = 20) -> Dict[str, Any]:
    """
    Execute a PowerShell command safely and return output, errors, and return code.
    """
    try:
        process = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            encoding="utf-8",
            errors="replace"
        )
        return {
            "success": process.returncode == 0,
            "stdout": process.stdout.strip(),
            "stderr": process.stderr.strip(),
            "return_code": process.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Execution timed out after {timeout_seconds} seconds.",
            "return_code": -1
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "return_code": -1
        }

def _open_single_application(app_name: str) -> Dict[str, Any]:
    """Internal helper to launch a single application, URL, or wiki query."""
    import re
    clean_name = re.sub(r'^(the|a)\s+', '', app_name.lower().strip(' "\''), flags=re.IGNORECASE).strip()
    if not clean_name:
        return {"status": "error", "message": "Empty application name."}

    # 1. Known Web Destinations / Services
    known_web_apps = {
        "github": "https://github.com",
        "youtube": "https://youtube.com",
        "reddit": "https://reddit.com",
        "gmail": "https://mail.google.com",
        "chatgpt": "https://chatgpt.com",
        "netflix": "https://netflix.com",
        "twitch": "https://twitch.tv",
        "amazon": "https://amazon.com",
        "twitter": "https://x.com",
        "x": "https://x.com",
        "google": "https://google.com",
        "wikipedia": "https://wikipedia.org",
    }
    
    # Direct URLs or web domains
    if "/" in clean_name or clean_name.startswith(("http://", "https://", "www.")) or any(clean_name.endswith(ext) for ext in [".com", ".org", ".io", ".net", ".dev", ".app", ".tv", ".wiki", ".gov", ".edu"]):
        url = clean_name if clean_name.startswith("http") else f"https://{clean_name}"
        res = execute_powershell(f'Start-Process "{url}"')
        if res["return_code"] == 0:
            return {"status": "success", "message": f"Opened {url} in default browser."}

    # 2. Known Windows Protocols and direct shortcuts
    known_shortcuts = {
        "steam": "start steam://open/main",
        "spotify": "start spotify:",
        "discord": "start discord:",
        "notepad": "notepad.exe",
        "calc": "calc.exe",
        "calculator": "calc.exe",
        "explorer": "explorer.exe",
        "chrome": "start chrome",
        "edge": "start msedge",
        "settings": "start ms-settings:",
        "taskmgr": "taskmgr.exe",
        "terminal": "wt.exe",
        "cmd": "cmd.exe",
        "vscode": "code",
        "code": "code",
    }
    
    if clean_name in known_shortcuts:
        res = execute_powershell(known_shortcuts[clean_name])
        if res["return_code"] == 0:
            return {"status": "success", "message": f"Successfully launched {clean_name}"}

    # Check known web aliases
    if clean_name in known_web_apps:
        target_url = known_web_apps[clean_name]
        res = execute_powershell(f'Start-Process "{target_url}"')
        if res["return_code"] == 0:
            return {"status": "success", "message": f"Opened {target_url} in default browser."}

    # 3. Check standard local installation paths
    candidate_paths = [
        Path(f"C:/Program Files (x86)/Steam/steam.exe") if clean_name == "steam" else None,
        Path(os.path.expandvars("%APPDATA%/Spotify/Spotify.exe")) if clean_name == "spotify" else None,
        Path(f"C:/Program Files/{clean_name}/{clean_name}.exe"),
        Path(f"C:/Program Files (x86)/{clean_name}/{clean_name}.exe"),
        Path(os.path.expandvars(f"%LOCALAPPDATA%/Programs/{clean_name}/{clean_name}.exe")),
        Path(os.path.expandvars(f"%APPDATA%/{clean_name}/{clean_name}.exe")),
    ]
    for p in filter(None, candidate_paths):
        if p.exists():
            res = execute_powershell(f'Start-Process "{p}"')
            if res["return_code"] == 0:
                return {"status": "success", "message": f"Launched {clean_name} from {p}"}

    # 4. Dynamic search in Windows Start Apps catalog
    ps_find_app = f"""
    $app = Get-StartApps | Where-Object {{ $_.Name -like '*{clean_name}*' }} | Select-Object -First 1
    if ($app) {{
        if ($app.AppID -match '^(http|steam|spotify|ms-):') {{
            Start-Process $app.AppID
        }} else {{
            Start-Process "explorer.exe" "shell:AppsFolder\\$($app.AppID)"
        }}
        Write-Output "LAUNCHED:$($app.Name)"
    }}
    """
    res = execute_powershell(ps_find_app)
    if "LAUNCHED:" in res.get("stdout", ""):
        return {"status": "success", "message": f"Successfully launched {clean_name}"}

    # 5. If query contains spaces, 'wiki', or is a web query, resolve via open_url
    if " " in clean_name or "wiki" in clean_name or clean_name in known_web_apps:
        return open_url(clean_name)

    # 6. Last fallback: try opening as website in default browser
    fallback_url = f"https://{clean_name}.com"
    res = execute_powershell(f'Start-Process "{fallback_url}"')
    if res["return_code"] == 0:
        return {"status": "success", "message": f"Opened {fallback_url} in default browser."}

    return {"status": "error", "message": f"Could not locate or launch application '{clean_name}'."}

def open_url(url: str) -> Dict[str, Any]:
    """
    Open a website, URL, wiki, or web search topic directly in the user's default web browser.
    Examples: 'https://github.com', 'valheim wiki', 'youtube.com', 'reddit.com'
    """
    import re
    import urllib.parse
    clean = url.strip(" /\\'\"")
    if not clean:
        return {"status": "error", "message": "Empty URL or topic."}

    # Direct URL
    if clean.startswith(("http://", "https://")):
        res = execute_powershell(f'Start-Process "{clean}"')
        if res["return_code"] == 0:
            return {"status": "success", "message": f"Opened {clean} in default browser."}

    # Direct domain (only if no spaces are present)
    if " " not in clean and ("/" in clean or any(clean.endswith(ext) for ext in [".com", ".org", ".io", ".net", ".dev", ".app", ".tv", ".wiki", ".gov", ".edu", ".gg"])):
        target = f"https://{clean}"
        res = execute_powershell(f'Start-Process "{target}"')
        if res["return_code"] == 0:
            return {"status": "success", "message": f"Opened {target} in default browser."}

    # Known web apps
    known_web_apps = {
        "github": "https://github.com",
        "youtube": "https://youtube.com",
        "reddit": "https://reddit.com",
        "gmail": "https://mail.google.com",
        "chatgpt": "https://chatgpt.com",
        "netflix": "https://netflix.com",
        "twitch": "https://twitch.tv",
        "amazon": "https://amazon.com",
        "twitter": "https://x.com",
        "x": "https://x.com",
        "google": "https://google.com",
        "wikipedia": "https://wikipedia.org",
    }
    lower_clean = clean.lower()
    if lower_clean in known_web_apps:
        target = known_web_apps[lower_clean]
        res = execute_powershell(f'Start-Process "{target}"')
        if res["return_code"] == 0:
            return {"status": "success", "message": f"Opened {target} in default browser."}

    # Search DuckDuckGo for topic/wiki and pick the most relevant candidate URL
    try:
        import httpx
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        r = httpx.post("https://html.duckduckgo.com/html/", data={"q": clean}, headers=headers, timeout=6.0)
        if r.status_code == 200:
            matches = re.findall(r'<a class="result__url"[^>]*href="([^"]*)"', r.text)
            candidate_urls = []
            for raw_url in matches:
                if "uddg=" in raw_url:
                    u = urllib.parse.unquote(raw_url.split("uddg=")[-1].split("&")[0])
                else:
                    u = raw_url if raw_url.startswith("http") else f"https://{raw_url}"
                if u not in candidate_urls and "duckduckgo.com" not in u:
                    candidate_urls.append(u)

            if candidate_urls:
                best_url = candidate_urls[0]
                best_score = -1
                keywords = [k.lower() for k in re.findall(r'\w+', clean) if len(k) > 2]

                for u in candidate_urls[:10]:
                    score = 0
                    u_lower = u.lower()
                    for k in keywords:
                        if k in u_lower:
                            score += 2
                    # Prioritize specific intent markers
                    if "wiki" in clean.lower() and ("wiki" in u_lower or "fandom" in u_lower or "fextralife" in u_lower):
                        score += 5
                    if "docs" in clean.lower() and ("doc" in u_lower or "readthe" in u_lower):
                        score += 5
                    if "reddit" in clean.lower() and "reddit" in u_lower:
                        score += 5
                    if "github" in clean.lower() and "github" in u_lower:
                        score += 5

                    if score > best_score and score > 0:
                        best_score = score
                        best_url = u

                res = execute_powershell(f'Start-Process "{best_url}"')
                if res["return_code"] == 0:
                    return {"status": "success", "message": f"Opened {best_url} in default browser."}
    except Exception:
        pass

    # Fallback to direct web search in browser
    encoded = urllib.parse.quote(clean)
    search_url = f"https://www.google.com/search?q={encoded}"
    res = execute_powershell(f'Start-Process "{search_url}"')
    if res["return_code"] == 0:
        return {"status": "success", "message": f"Searched for '{clean}' in default browser."}

    return {"status": "error", "message": f"Failed to open '{clean}' in browser."}

def open_application(app_name: str) -> Dict[str, Any]:
    """
    Launch a Windows application, URL protocol, website, or compound list of apps.
    Examples: 'steam', 'github', 'valheim wiki', 'discord, steam, spotify and valheim wiki'
    """
    import re
    # Check for compound list (e.g. separated by comma or ' and ')
    if "," in app_name or " and " in app_name.lower():
        items = [item.strip() for item in re.split(r',|\band\b', app_name, flags=re.IGNORECASE) if item.strip()]
        if len(items) > 1:
            results = []
            for it in items:
                results.append(_open_single_application(it))
            return {
                "status": "success",
                "message": f"Launched {len(results)} items: " + "; ".join([r.get("message", "") for r in results])
            }

    return _open_single_application(app_name)

def control_volume(action: str, level: Optional[int] = None) -> Dict[str, Any]:
    """
    Control Windows audio volume.
    action: 'mute', 'unmute', 'set', 'get'
    level: integer 0 to 100 (when action is 'set')
    """
    try:
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        from comtypes import CLSCTX_ALL
        from ctypes import cast, POINTER

        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))

        if action == "mute":
            volume.SetMute(1, None)
            return {"status": "success", "message": "System audio muted."}
        elif action == "unmute":
            volume.SetMute(0, None)
            return {"status": "success", "message": "System audio unmuted."}
        elif action == "set" and level is not None:
            clamped = max(0, min(100, level)) / 100.0
            volume.SetMasterVolumeLevelScalar(clamped, None)
            return {"status": "success", "message": f"Volume set to {level}%."}
        elif action == "get":
            curr = round(volume.GetMasterVolumeLevelScalar() * 100)
            muted = bool(volume.GetMute())
            return {"status": "success", "volume": curr, "muted": muted}
        else:
            return {"status": "error", "message": f"Unknown action '{action}'"}
    except Exception as e:
        # Fallback to PowerShell
        if action == "set" and level is not None:
            # Fallback script
            return {"status": "error", "message": f"PyCaw error: {e}"}
        return {"status": "error", "message": str(e)}

def get_system_stats() -> Dict[str, Any]:
    """
    Retrieve live system hardware metrics (CPU, RAM, Battery, Disk).
    """
    cpu_percent = psutil.cpu_percent(interval=0.2)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    battery = psutil.sensors_battery()

    battery_info = None
    if battery:
        battery_info = {
            "percent": battery.percent,
            "power_plugged": battery.power_plugged,
            "secs_left": battery.secsleft if battery.secsleft != psutil.POWER_TIME_UNLIMITED else "Unlimited"
        }

    return {
        "cpu_usage_percent": cpu_percent,
        "ram_used_gb": round(memory.used / (1024**3), 2),
        "ram_total_gb": round(memory.total / (1024**3), 2),
        "ram_percent": memory.percent,
        "disk_free_gb": round(disk.free / (1024**3), 2),
        "battery": battery_info
    }

def file_manager(action: str, path: str, content: Optional[str] = None) -> Dict[str, Any]:
    """
    Perform local file system actions: 'read', 'write', 'list', 'exists', 'mkdir'.
    """
    target = Path(path).resolve()
    try:
        if action == "read":
            if not target.exists():
                return {"status": "error", "message": f"File '{path}' does not exist."}
            text = target.read_text(encoding="utf-8", errors="replace")
            return {"status": "success", "content": text[:4000]} # capped preview
        elif action == "write":
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content or "", encoding="utf-8")
            return {"status": "success", "message": f"Wrote to '{path}'"}
        elif action == "list":
            if not target.exists():
                return {"status": "error", "message": f"Directory '{path}' does not exist."}
            items = [item.name + ("/" if item.is_dir() else "") for item in target.iterdir()]
            return {"status": "success", "items": items[:50]}
        elif action == "exists":
            return {"status": "success", "exists": target.exists()}
        elif action == "mkdir":
            target.mkdir(parents=True, exist_ok=True)
            return {"status": "success", "message": f"Directory '{path}' created."}
        else:
            return {"status": "error", "message": f"Unknown file action '{action}'"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

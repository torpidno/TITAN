import os
import subprocess
import logging
import ctypes
import time
from typing import Dict, Any, Optional

logger = logging.getLogger("TITAN.Tools.MediaWindow")


# --- Virtual Key Definitions for Windows API ---
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_LWIN = 0x5B
VK_TAB = 0x09
VK_LEFT = 0x25
VK_UP = 0x26
VK_RIGHT = 0x27
VK_DOWN = 0x28
VK_D = 0x44
VK_M = 0x4D
KEYEVENTF_KEYUP = 0x0002


def _send_key_press(vk_code: int):
    """Simulate a single virtual key press and release."""
    user32 = ctypes.windll.user32
    user32.keybd_event(vk_code, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)


def _send_hotkey(modifier_vk: int, key_vk: int):
    """Simulate key combination (e.g. Win + D, Win + Left)."""
    user32 = ctypes.windll.user32
    user32.keybd_event(modifier_vk, 0, 0, 0)
    time.sleep(0.04)
    user32.keybd_event(key_vk, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(key_vk, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(modifier_vk, 0, KEYEVENTF_KEYUP, 0)


def control_media(action: str) -> Dict[str, Any]:
    """
    Control system-wide media playback (Spotify, YouTube, browser, media players).
    action: 'play_pause', 'next', 'previous', 'stop', 'volume_up', 'volume_down', 'mute'
    """
    clean_action = action.lower().strip().replace("-", "_").replace(" ", "_")
    logger.info(f"[MEDIA] Executing media transport command: '{clean_action}'")

    if clean_action in ("play", "pause", "play_pause", "toggle"):
        _send_key_press(VK_MEDIA_PLAY_PAUSE)
        return {"status": "success", "action": "play_pause", "message": "Toggled media playback (Play/Pause)."}

    elif clean_action in ("next", "next_track", "skip", "forward"):
        _send_key_press(VK_MEDIA_NEXT_TRACK)
        return {"status": "success", "action": "next_track", "message": "Skipped to next media track."}

    elif clean_action in ("previous", "prev", "prev_track", "back"):
        _send_key_press(VK_MEDIA_PREV_TRACK)
        return {"status": "success", "action": "prev_track", "message": "Returned to previous media track."}

    elif clean_action in ("stop",):
        _send_key_press(VK_MEDIA_STOP)
        return {"status": "success", "action": "stop", "message": "Stopped media playback."}

    elif clean_action in ("volume_up", "vol_up", "louder"):
        for _ in range(3):
            _send_key_press(VK_VOLUME_UP)
        return {"status": "success", "action": "volume_up", "message": "Increased system audio volume."}

    elif clean_action in ("volume_down", "vol_down", "quieter"):
        for _ in range(3):
            _send_key_press(VK_VOLUME_DOWN)
        return {"status": "success", "action": "volume_down", "message": "Decreased system audio volume."}

    elif clean_action in ("mute", "unmute"):
        _send_key_press(VK_VOLUME_MUTE)
        return {"status": "success", "action": "mute_toggle", "message": "Toggled system audio mute state."}

    return {"status": "error", "message": f"Unknown media action: '{action}'. Options: play_pause, next, previous, stop, volume_up, volume_down, mute."}


def control_windows(action: str, target: Optional[str] = None) -> Dict[str, Any]:
    """
    Manage and arrange Windows desktop application windows.
    action: 'minimize_all', 'show_desktop', 'restore_all', 'snap_left', 'snap_right', 'maximize', 'minimize', 'task_view', 'focus'
    target: Application name or title (optional, used when action is 'focus' or 'close')
    """
    clean_action = action.lower().strip().replace("-", "_").replace(" ", "_")
    logger.info(f"[WINDOW] Window control action: '{clean_action}' (Target: {target})")

    if clean_action in ("minimize_all", "show_desktop", "desktop"):
        # Win + D toggles desktop / minimizes all
        _send_hotkey(VK_LWIN, VK_D)
        return {"status": "success", "action": "minimize_all", "message": "Minimized all windows to show desktop."}

    elif clean_action in ("restore_all", "unminimize"):
        _send_hotkey(VK_LWIN, VK_D)
        return {"status": "success", "action": "restore_all", "message": "Restored desktop windows."}

    elif clean_action in ("snap_left", "left", "tile_left"):
        _send_hotkey(VK_LWIN, VK_LEFT)
        return {"status": "success", "action": "snap_left", "message": "Snapped active window to the left half."}

    elif clean_action in ("snap_right", "right", "tile_right"):
        _send_hotkey(VK_LWIN, VK_RIGHT)
        return {"status": "success", "action": "snap_right", "message": "Snapped active window to the right half."}

    elif clean_action in ("maximize", "fullscreen", "max"):
        _send_hotkey(VK_LWIN, VK_UP)
        return {"status": "success", "action": "maximize", "message": "Maximized active window."}

    elif clean_action in ("minimize", "min"):
        _send_hotkey(VK_LWIN, VK_DOWN)
        return {"status": "success", "action": "minimize", "message": "Minimized active window."}

    elif clean_action in ("task_view", "switch", "alt_tab"):
        _send_hotkey(VK_LWIN, VK_TAB)
        return {"status": "success", "action": "task_view", "message": "Opened Windows Task View / App Switcher."}

    elif clean_action in ("focus", "switch_to") and target:
        # Find window by title / name and bring to front
        try:
            ps_script = f"""
            $proc = Get-Process | Where-Object {{ $_.MainWindowTitle -like '*{target}*' -or $_.ProcessName -like '*{target}*' }} | Select-Object -First 1
            if ($proc -and $proc.MainWindowHandle -ne 0) {{
                $w = Add-Type -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);' -Name "Win32Util" -Namespace "Win32" -PassThru
                $w::SetForegroundWindow($proc.MainWindowHandle)
                Write-Output "FOCUSED:$($proc.ProcessName)"
            }}
            """
            res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], capture_output=True, text=True, timeout=10)
            if "FOCUSED:" in res.stdout:
                return {"status": "success", "action": "focus", "message": f"Focused window '{target}'."}
        except Exception as e:
            logger.debug(f"Focus window error: {e}")

    return {"status": "error", "message": f"Unsupported window action: '{action}'. Options: minimize_all, restore_all, snap_left, snap_right, maximize, minimize, task_view, focus."}


def control_workstation(action: str, timer_seconds: Optional[int] = None) -> Dict[str, Any]:
    """
    Control workstation power, security, and lock states.
    action: 'lock', 'sleep', 'turn_off_screens', 'restart', 'shutdown', 'cancel_shutdown'
    timer_seconds: Optional countdown in seconds (for restart or shutdown)
    """
    clean_action = action.lower().strip().replace("-", "_").replace(" ", "_")
    logger.info(f"[WORKSTATION] Executing workstation power/security action: '{clean_action}'")

    if clean_action in ("lock", "lock_workstation", "lock_screen"):
        ctypes.windll.user32.LockWorkStation()
        return {"status": "success", "action": "lock", "message": "Workstation locked securely."}

    elif clean_action in ("turn_off_screens", "turn_off_display", "screen_off", "display_off"):
        # SendMessage(HWND_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER, 2)
        HWND_BROADCAST = 0xFFFF
        WM_SYSCOMMAND = 0x0112
        SC_MONITORPOWER = 0xF170
        ctypes.windll.user32.SendMessageW(HWND_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER, 2)
        return {"status": "success", "action": "turn_off_screens", "message": "Turned off display monitors (will wake on mouse/keyboard input)."}

    elif clean_action in ("sleep", "suspend", "standby"):
        # Put system to sleep safely
        subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
        return {"status": "success", "action": "sleep", "message": "Putting workstation to sleep."}

    elif clean_action in ("shutdown", "power_off"):
        t = timer_seconds if timer_seconds is not None else 60
        subprocess.run(["shutdown", "/s", "/t", str(t)], capture_output=True)
        return {"status": "success", "action": "shutdown", "message": f"System shutdown initiated in {t} seconds. Use 'cancel_shutdown' to abort."}

    elif clean_action in ("restart", "reboot"):
        t = timer_seconds if timer_seconds is not None else 60
        subprocess.run(["shutdown", "/r", "/t", str(t)], capture_output=True)
        return {"status": "success", "action": "restart", "message": f"System restart initiated in {t} seconds. Use 'cancel_shutdown' to abort."}

    elif clean_action in ("cancel_shutdown", "abort_shutdown", "cancel"):
        subprocess.run(["shutdown", "/a"], capture_output=True)
        return {"status": "success", "action": "cancel_shutdown", "message": "Aborted scheduled shutdown/restart."}

    return {"status": "error", "message": f"Unknown workstation action: '{action}'. Options: lock, sleep, turn_off_screens, shutdown, restart, cancel_shutdown."}

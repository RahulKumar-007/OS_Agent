"""
Desktop Environment Awareness Tools.

Gives the agent actual control over the Linux desktop:
  - Clipboard read/write/history
  - Screenshots (full/region/active window)
  - Desktop notifications
  - Window management (list/focus/minimize/maximize)
  - Display/monitor info
"""

import asyncio
import base64
import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime
from typing import Dict, List, Optional

from tools.base import Tool, ToolResult


# ── helper ──────────────────────────────────────────────────────────────────

def _run(cmd: list[str], timeout: float = 5.0, input_data: Optional[bytes] = None) -> subprocess.CompletedProcess:
    """Run a subprocess synchronously, capturing output."""
    return subprocess.run(
        cmd,
        capture_output=True,
        input=input_data,
        timeout=timeout,
    )


def _has(*cmds: str) -> Optional[str]:
    """Return the first available command from the list, or None."""
    for cmd in cmds:
        if shutil.which(cmd):
            return cmd
    return None


# ── Clipboard ────────────────────────────────────────────────────────────────

_CLIP_HISTORY: List[dict] = []  # in-process history (up to 50 entries)
_MAX_HISTORY = 50


class ClipboardReadTool(Tool):
    name = "clipboard_read"
    description = "Read the current text content of the system clipboard."
    parameters_schema = {}

    async def execute(self, args: Dict) -> ToolResult:
        content = await asyncio.to_thread(self._read)
        if content is None:
            return ToolResult(success=False, message="No clipboard tool found (install xclip or xsel).")
        return ToolResult(success=True, data={"content": content}, message="Clipboard read successfully.")

    @staticmethod
    def _read() -> Optional[str]:
        for tool, flag in [("xclip", ["-selection", "clipboard", "-o"]),
                           ("xsel",  ["--clipboard", "--output"]),
                           ("wl-paste", [])]:
            if shutil.which(tool):
                try:
                    r = subprocess.run([tool] + flag, capture_output=True, timeout=3)
                    if r.returncode == 0:
                        return r.stdout.decode(errors="replace")
                except Exception:
                    pass
        return None


class ClipboardWriteTool(Tool):
    name = "clipboard_write"
    description = "Write text to the system clipboard."
    parameters_schema = {
        "text": "The text to copy to the clipboard.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        text = args.get("text", "")
        success = await asyncio.to_thread(self._write, text)
        if not success:
            return ToolResult(success=False, message="No clipboard tool found (install xclip or xsel).")
        # Record history
        _CLIP_HISTORY.insert(0, {"content": text, "timestamp": datetime.now().isoformat()})
        if len(_CLIP_HISTORY) > _MAX_HISTORY:
            _CLIP_HISTORY.pop()
        return ToolResult(success=True, data={"written": len(text)}, message="Text copied to clipboard.")

    @staticmethod
    def _write(text: str) -> bool:
        for tool, flag in [("xclip", ["-selection", "clipboard"]),
                           ("xsel",  ["--clipboard", "--input"]),
                           ("wl-copy", [])]:
            if shutil.which(tool):
                try:
                    r = subprocess.run([tool] + flag, input=text.encode(), capture_output=True, timeout=3)
                    return r.returncode == 0
                except Exception:
                    pass
        return False


class ClipboardHistoryTool(Tool):
    name = "clipboard_history"
    description = "Get in-session clipboard history (content copied via clipboard_write)."
    parameters_schema = {
        "limit": "(optional) Number of entries to return. Default 20.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        limit = int(args.get("limit", 20))
        return ToolResult(
            success=True,
            data={"history": _CLIP_HISTORY[:limit], "total": len(_CLIP_HISTORY)},
            message=f"{min(limit, len(_CLIP_HISTORY))} clipboard entries.",
        )


# ── Screenshots ──────────────────────────────────────────────────────────────

class ScreenshotTool(Tool):
    name = "take_screenshot"
    description = (
        "Take a screenshot and save it to disk. Supports full screen, active window, "
        "or a region (x,y,width,height). Returns the saved file path and base64-encoded image."
    )
    parameters_schema = {
        "mode": "(optional) 'full' | 'window' | 'region'. Default 'full'.",
        "x":      "(optional, region) Left pixel.",
        "y":      "(optional, region) Top pixel.",
        "width":  "(optional, region) Width in pixels.",
        "height": "(optional, region) Height in pixels.",
        "output": "(optional) Destination file path. Defaults to ~/Screenshots/<timestamp>.png.",
        "delay":  "(optional) Seconds to wait before capturing. Default 0.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        mode   = args.get("mode", "full")
        delay  = int(args.get("delay", 0))
        output = args.get("output") or os.path.join(
            os.path.expanduser("~"), "Screenshots",
            f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png",
        )
        os.makedirs(os.path.dirname(output), exist_ok=True)

        region = None
        if mode == "region":
            region = (
                int(args.get("x", 0)),
                int(args.get("y", 0)),
                int(args.get("width", 800)),
                int(args.get("height", 600)),
            )

        ok, msg = await asyncio.to_thread(self._capture, mode, delay, output, region)
        if not ok:
            return ToolResult(success=False, message=msg)

        b64 = ""
        try:
            with open(output, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
        except Exception:
            pass

        return ToolResult(
            success=True,
            data={"path": output, "image_base64": b64},
            message=f"Screenshot saved to {output}",
        )

    @staticmethod
    def _capture(mode: str, delay: int, output: str, region) -> tuple[bool, str]:
        if delay:
            time.sleep(delay)

        # Try scrot (most common on X11)
        if shutil.which("scrot"):
            cmd = ["scrot", output]
            if mode == "window":
                cmd = ["scrot", "--focused", output]
            elif mode == "region" and region:
                x, y, w, h = region
                cmd = ["scrot", "--area", f"{x},{y},{w},{h}", output]
            r = subprocess.run(cmd, capture_output=True, timeout=10)
            if r.returncode == 0:
                return True, "scrot capture"

        # Try gnome-screenshot
        if shutil.which("gnome-screenshot"):
            cmd = ["gnome-screenshot", f"--file={output}"]
            if mode == "window":
                cmd.append("--window")
            elif mode == "region":
                cmd.append("--area")
            r = subprocess.run(cmd, capture_output=True, timeout=10)
            if r.returncode == 0:
                return True, "gnome-screenshot capture"

        # Try import (ImageMagick)
        if shutil.which("import"):
            if mode == "region" and region:
                x, y, w, h = region
                cmd = ["import", "-window", "root", "-crop", f"{w}x{h}+{x}+{y}", output]
            else:
                cmd = ["import", "-window", "root", output]
            r = subprocess.run(cmd, capture_output=True, timeout=10)
            if r.returncode == 0:
                return True, "ImageMagick capture"

        # Try Python PIL/Pillow
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            if mode == "region" and region:
                x, y, w, h = region
                img = img.crop((x, y, x + w, y + h))
            img.save(output)
            return True, "PIL capture"
        except Exception:
            pass

        return False, "No screenshot tool available. Install scrot, gnome-screenshot, or ImageMagick."


# ── Desktop Notifications ─────────────────────────────────────────────────────

class DesktopNotificationTool(Tool):
    name = "desktop_notify"
    description = "Send a native Linux desktop notification via notify-send."
    parameters_schema = {
        "title":   "Notification title.",
        "body":    "(optional) Notification body text.",
        "urgency": "(optional) 'low' | 'normal' | 'critical'. Default 'normal'.",
        "icon":    "(optional) Icon name or path.",
        "timeout": "(optional) Duration in milliseconds. Default 5000.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        title   = args.get("title", "JARVIS Notification")
        body    = args.get("body", "")
        urgency = args.get("urgency", "normal")
        icon    = args.get("icon", "dialog-information")
        timeout = int(args.get("timeout", 5000))

        if not shutil.which("notify-send"):
            return ToolResult(success=False, message="notify-send not found. Install libnotify-bin.")

        cmd = [
            "notify-send",
            "--urgency", urgency,
            "--icon", icon,
            f"--expire-time={timeout}",
            title,
        ]
        if body:
            cmd.append(body)

        r = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, timeout=5)
        if r.returncode != 0:
            return ToolResult(success=False, message=r.stderr.decode(errors="replace") or "notify-send failed.")
        return ToolResult(success=True, message=f"Notification sent: {title}")


# ── Window Management ─────────────────────────────────────────────────────────

class ListWindowsTool(Tool):
    name = "list_windows"
    description = "List all open windows on the desktop (title, class, PID, window ID)."
    parameters_schema = {}

    async def execute(self, args: Dict) -> ToolResult:
        windows = await asyncio.to_thread(self._list)
        if windows is None:
            return ToolResult(
                success=False,
                message="Window listing requires wmctrl or xdotool. Install one of them.",
            )
        return ToolResult(
            success=True,
            data={"windows": windows, "count": len(windows)},
            message=f"{len(windows)} window(s) found.",
        )

    @staticmethod
    def _list() -> Optional[list]:
        if shutil.which("wmctrl"):
            r = subprocess.run(["wmctrl", "-l", "-p"], capture_output=True, timeout=5)
            if r.returncode == 0:
                windows = []
                for line in r.stdout.decode(errors="replace").strip().splitlines():
                    parts = line.split(None, 4)
                    if len(parts) >= 5:
                        windows.append({
                            "id":      parts[0],
                            "desktop": parts[1],
                            "pid":     parts[2],
                            "host":    parts[3],
                            "title":   parts[4],
                        })
                return windows

        if shutil.which("xdotool"):
            r = subprocess.run(
                ["xdotool", "search", "--onlyvisible", "--name", ""],
                capture_output=True, timeout=5,
            )
            if r.returncode == 0:
                ids = r.stdout.decode().strip().splitlines()
                windows = []
                for wid in ids[:50]:
                    rn = subprocess.run(["xdotool", "getwindowname", wid], capture_output=True, timeout=2)
                    windows.append({"id": wid, "title": rn.stdout.decode().strip()})
                return windows
        return None


class FocusWindowTool(Tool):
    name = "focus_window"
    description = "Focus/raise a window by title substring or window ID."
    parameters_schema = {
        "title":     "(optional) Window title substring to match.",
        "window_id": "(optional) Exact window ID (hex) from list_windows.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        title     = args.get("title", "")
        window_id = args.get("window_id", "")
        ok, msg = await asyncio.to_thread(self._focus, title, window_id)
        return ToolResult(success=ok, message=msg)

    @staticmethod
    def _focus(title: str, window_id: str) -> tuple[bool, str]:
        if shutil.which("wmctrl"):
            if window_id:
                r = subprocess.run(["wmctrl", "-ia", window_id], capture_output=True, timeout=5)
            else:
                r = subprocess.run(["wmctrl", "-a", title], capture_output=True, timeout=5)
            if r.returncode == 0:
                return True, f"Focused: {title or window_id}"
        if shutil.which("xdotool"):
            if title:
                r = subprocess.run(
                    ["xdotool", "search", "--name", title, "windowfocus", "--sync"],
                    capture_output=True, timeout=5,
                )
                if r.returncode == 0:
                    return True, f"Focused: {title}"
        return False, "Could not focus window. Install wmctrl or xdotool."


class WindowActionTool(Tool):
    name = "window_action"
    description = "Minimize, maximize, restore, or close a window by title or window ID."
    parameters_schema = {
        "action":    "'minimize' | 'maximize' | 'restore' | 'close'",
        "title":     "(optional) Window title substring.",
        "window_id": "(optional) Exact window ID from list_windows.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        action    = args.get("action", "minimize")
        title     = args.get("title", "")
        window_id = args.get("window_id", "")
        ok, msg = await asyncio.to_thread(self._action, action, title, window_id)
        return ToolResult(success=ok, message=msg)

    @staticmethod
    def _action(action: str, title: str, window_id: str) -> tuple[bool, str]:
        if not shutil.which("wmctrl"):
            return False, "wmctrl is required for window actions. Install it with: sudo apt install wmctrl"

        _map = {
            "minimize": "remove,shaded",
            "maximize": "add,maximized_vert,maximized_horz",
            "restore":  "remove,maximized_vert,maximized_horz",
        }

        if action == "close":
            if window_id:
                r = subprocess.run(["wmctrl", "-ic", window_id], capture_output=True, timeout=5)
            else:
                r = subprocess.run(["wmctrl", "-c", title], capture_output=True, timeout=5)
        elif action in _map:
            prop = _map[action]
            if window_id:
                r = subprocess.run(
                    ["wmctrl", "-ir", window_id, "-b", prop],
                    capture_output=True, timeout=5,
                )
            else:
                r = subprocess.run(
                    ["wmctrl", "-r", title, "-b", prop],
                    capture_output=True, timeout=5,
                )
        else:
            return False, f"Unknown action: {action}"

        return (r.returncode == 0), (r.stderr.decode(errors="replace") or f"{action} applied")


class GetActiveWindowTool(Tool):
    name = "get_active_window"
    description = "Get the currently focused/active window title, class, and PID."
    parameters_schema = {}

    async def execute(self, args: Dict) -> ToolResult:
        info = await asyncio.to_thread(self._active)
        if info is None:
            return ToolResult(success=False, message="xdotool or xprop required.")
        return ToolResult(success=True, data=info, message="Active window retrieved.")

    @staticmethod
    def _active() -> Optional[dict]:
        if shutil.which("xdotool"):
            wid_r = subprocess.run(["xdotool", "getactivewindow"], capture_output=True, timeout=3)
            if wid_r.returncode == 0:
                wid = wid_r.stdout.decode().strip()
                name_r = subprocess.run(["xdotool", "getwindowname", wid], capture_output=True, timeout=3)
                pid_r  = subprocess.run(["xdotool", "getwindowpid",  wid], capture_output=True, timeout=3)
                return {
                    "window_id": wid,
                    "title": name_r.stdout.decode().strip(),
                    "pid":   pid_r.stdout.decode().strip(),
                }
        if shutil.which("xprop"):
            r = subprocess.run(
                ["xprop", "-root", "_NET_ACTIVE_WINDOW"],
                capture_output=True, timeout=3,
            )
            if r.returncode == 0:
                return {"raw": r.stdout.decode().strip()}
        return None


# ── Display / Monitor Info ────────────────────────────────────────────────────

class DisplayInfoTool(Tool):
    name = "display_info"
    description = "Get information about connected monitors: resolution, refresh rate, position."
    parameters_schema = {}

    async def execute(self, args: Dict) -> ToolResult:
        monitors = await asyncio.to_thread(self._monitors)
        if monitors is None:
            return ToolResult(success=False, message="xrandr is required. Install x11-xserver-utils.")
        return ToolResult(
            success=True,
            data={"monitors": monitors, "count": len(monitors)},
            message=f"{len(monitors)} monitor(s) detected.",
        )

    @staticmethod
    def _monitors() -> Optional[list]:
        if not shutil.which("xrandr"):
            return None
        r = subprocess.run(["xrandr", "--query"], capture_output=True, timeout=5)
        if r.returncode != 0:
            return None

        monitors = []
        current = None
        for line in r.stdout.decode(errors="replace").splitlines():
            if " connected" in line or " disconnected" in line:
                connected = " connected" in line
                parts = line.split()
                name = parts[0]
                if current:
                    monitors.append(current)
                current = {"name": name, "connected": connected, "resolution": None, "primary": "primary" in line}
            elif current and "*" in line:
                parts = line.strip().split()
                if parts:
                    current["resolution"] = parts[0] if "x" in parts[0] else None
        if current:
            monitors.append(current)
        return monitors


# ── Registry ─────────────────────────────────────────────────────────────────

ALL_DESKTOP_TOOLS = [
    ClipboardReadTool(),
    ClipboardWriteTool(),
    ClipboardHistoryTool(),
    ScreenshotTool(),
    DesktopNotificationTool(),
    ListWindowsTool(),
    FocusWindowTool(),
    WindowActionTool(),
    GetActiveWindowTool(),
    DisplayInfoTool(),
]

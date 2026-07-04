"""
PTY-backed interactive shell session.

Spawns a real shell (bash/zsh/etc.) attached to a pseudo-terminal so the
frontend gets a genuine interactive terminal experience — full-screen apps,
line editing, colors, job control — not just one-shot command execution.

Linux/macOS only (relies on the stdlib `pty` module, which does not exist
on Windows). Callers should catch ImportError and degrade gracefully.
"""

import fcntl
import os
import pty
import signal
import struct
import termios
from typing import Optional


class PtySession:
    """A single interactive shell process bound to a pseudo-terminal."""

    def __init__(self, shell: Optional[str] = None, cwd: Optional[str] = None):
        self.shell = shell or os.environ.get("SHELL", "/bin/bash")
        self.cwd = os.path.expanduser(cwd) if cwd else os.path.expanduser("~")
        self.pid: Optional[int] = None
        self.fd: Optional[int] = None

    def spawn(self):
        """Fork the shell process. Must be called before read/write/resize."""
        pid, fd = pty.fork()
        if pid == 0:
            # ── Child process: replace with the shell ──
            try:
                os.chdir(self.cwd)
            except OSError:
                pass
            env = os.environ.copy()
            env["TERM"] = "xterm-256color"
            try:
                os.execvpe(self.shell, [self.shell], env)
            except OSError:
                os._exit(1)
        else:
            # ── Parent process ──
            self.pid = pid
            self.fd = fd
            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
            self.resize(24, 80)

    def write(self, data: bytes):
        if self.fd is None:
            return
        try:
            os.write(self.fd, data)
        except OSError:
            pass

    def read(self, size: int = 65536) -> bytes:
        if self.fd is None:
            return b""
        try:
            return os.read(self.fd, size)
        except (OSError, BlockingIOError):
            return b""

    def resize(self, rows: int, cols: int):
        if self.fd is None:
            return
        try:
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self.fd, termios.TIOCSWINSZ, winsize)
        except OSError:
            pass

    def alive(self) -> bool:
        if self.pid is None:
            return False
        try:
            pid, _status = os.waitpid(self.pid, os.WNOHANG)
            return pid == 0
        except ChildProcessError:
            return False

    def close(self):
        if self.pid:
            try:
                os.kill(self.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None

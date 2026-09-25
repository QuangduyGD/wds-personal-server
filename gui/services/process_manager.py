"""Manage the local API server and mitmdump without creating console windows."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal


class ManagedProcess(QObject):
    output = Signal(str, str)  # name, line
    state_changed = Signal(str, str)  # name, stopped/running/exited/failed

    def __init__(self, name, command, cwd):
        super().__init__()
        self.name = name
        self.command = command
        self.cwd = cwd
        self.process: subprocess.Popen | None = None
        self._lock = threading.RLock()

    @property
    def running(self):
        return self.process is not None and self.process.poll() is None

    def start(self):
        with self._lock:
            if self.running:
                self.state_changed.emit(self.name, "running")
                return False
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
            startupinfo = None
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            try:
                self.process = subprocess.Popen(
                    self.command, cwd=str(self.cwd), stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace", bufsize=1,
                    creationflags=flags, startupinfo=startupinfo,
                )
            except OSError as exc:
                self.process = None
                self.output.emit(self.name, f"ERROR: cannot start ({type(exc).__name__}): {exc}")
                self.state_changed.emit(self.name, "failed")
                return False
            self.state_changed.emit(self.name, "running")
            threading.Thread(target=self._read_output, daemon=True, name=f"{self.name}-log").start()
            threading.Thread(target=self._wait, daemon=True, name=f"{self.name}-wait").start()
            return True

    def _read_output(self):
        stream = self.process.stdout if self.process else None
        if stream:
            for line in stream:
                self.output.emit(self.name, line.rstrip())

    def _wait(self):
        process = self.process
        if process is None:
            return
        code = process.wait()
        with self._lock:
            self.process = None
        self.output.emit(self.name, f"Process exited with code {code}")
        self.state_changed.emit(self.name, "exited" if code == 0 else "failed")

    def stop(self, timeout=5):
        with self._lock:
            process = self.process
            if process is None or process.poll() is not None:
                self.process = None
                self.state_changed.emit(self.name, "stopped")
                return True
            self.output.emit(self.name, "Stopping...")
            process.terminate()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.output.emit(self.name, "Graceful stop timed out; terminating child process.")
            process.kill()
            process.wait(timeout=2)
        with self._lock:
            if self.process is process:
                self.process = None
        self.state_changed.emit(self.name, "stopped")
        return True

    def restart(self):
        self.stop()
        return self.start()


class ProcessManager(QObject):
    log = Signal(str, str)
    state_changed = Signal(str, str)

    def __init__(self, project_root=None, parent=None):
        super().__init__(parent)
        self.root = Path(project_root or Path(__file__).resolve().parents[2])
        python = self.root / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        mitmdump = self.root / "venv" / ("Scripts/mitmdump.exe" if os.name == "nt" else "bin/mitmdump")
        self.processes = {
            "server": ManagedProcess("server", [str(python), "main.py"], self.root),
            "proxy": ManagedProcess("proxy", [str(mitmdump), "-s", "mitm_redirect_sirius_to_local.py"], self.root),
        }
        for process in self.processes.values():
            process.output.connect(self.log)
            process.state_changed.connect(self.state_changed)

    def start(self, name):
        return self.processes[name].start()

    def stop(self, name):
        return self.processes[name].stop()

    def restart(self, name):
        return self.processes[name].restart()

    def stop_all(self):
        for process in self.processes.values():
            process.stop()

    def is_running(self, name):
        return self.processes[name].running

    def status(self):
        return {name: process.running for name, process in self.processes.items()}

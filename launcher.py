"""
launcher.py — starts midi_bridge.py and cloudflared, captures the tunnel URL,
copies it to the clipboard, and pipes both processes' logs to stdout.

Replaces the brittle shell-quoting in the previous .bat/.sh launchers.
"""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
TRYCF_RE = re.compile(r"https://[A-Za-z0-9.-]+\.trycloudflare\.com")
HEALTH_URL = "http://127.0.0.1:8080/health"


def _venv_python() -> str:
    """Return the venv's python executable, falling back to current interpreter."""
    if os.name == "nt":
        cand = HERE / ".venv" / "Scripts" / "python.exe"
    else:
        cand = HERE / ".venv" / "bin" / "python"
    if cand.exists():
        return str(cand)
    return sys.executable


def _which_cloudflared() -> str | None:
    return shutil.which("cloudflared")


def _wait_http_ready(timeout_s: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=1.5) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.2)
    return False


def _stream(stream, prefix: str, sink_lines: list[str] | None = None) -> None:
    for raw in iter(stream.readline, b""):
        try:
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        except Exception:
            continue
        print(f"[{prefix}] {line}", flush=True)
        if sink_lines is not None:
            sink_lines.append(line)
    try:
        stream.close()
    except Exception:
        pass


def _copy_to_clipboard(text: str) -> bool:
    if os.name == "nt":
        try:
            subprocess.run("clip", input=text.encode("utf-16le"), check=True)
            return True
        except Exception:
            return False
    if sys.platform == "darwin":
        try:
            subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
            return True
        except Exception:
            return False
    if shutil.which("xclip"):
        try:
            subprocess.run(["xclip", "-selection", "clipboard"],
                           input=text.encode("utf-8"), check=True)
            return True
        except Exception:
            return False
    return False


def main() -> int:
    py = _venv_python()
    if not (HERE / ".venv").exists() and py == sys.executable:
        print("WARNING: no .venv detected. Create it with:")
        print(f'  python -m venv "{HERE / ".venv"}"')
        print(f'  "{HERE / ".venv" / ("Scripts" if os.name=="nt" else "bin") / "pip"}" install -r "{HERE / "requirements.txt"}"')

    cf = _which_cloudflared()
    if not cf:
        print("ERROR: cloudflared not found on PATH.")
        print("  macOS:   brew install cloudflared")
        print("  Windows: download from https://github.com/cloudflare/cloudflared/releases")
        return 1

    print(f"[launcher] python: {py}")
    print(f"[launcher] cloudflared: {cf}")

    bridge_proc = subprocess.Popen(
        [py, "-u", str(HERE / "midi_bridge.py")],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(HERE),
    )
    threading.Thread(target=_stream, args=(bridge_proc.stdout, "bridge"), daemon=True).start()

    if not _wait_http_ready(10.0):
        print("[launcher] WARNING: bridge HTTP health check did not respond in 10s; continuing anyway")

    tunnel_log: list[str] = []
    tunnel_proc = subprocess.Popen(
        [cf, "tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:8080"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(HERE),
    )
    threading.Thread(
        target=_stream, args=(tunnel_proc.stdout, "tunnel", tunnel_log), daemon=True
    ).start()

    # Watch the tunnel log for a trycloudflare URL.
    url = None
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        for line in tunnel_log:
            m = TRYCF_RE.search(line)
            if m:
                url = m.group(0)
                break
        if url:
            break
        time.sleep(0.25)

    if url:
        copied = _copy_to_clipboard(url)
        bar = "=" * 64
        print()
        print(bar)
        print(f"  Tunnel URL:  {url}")
        print(f"  Health URL:  {url}/health")
        print()
        print(f"  In Roblox chat (as admin):")
        print(f"      /pianourl {url}")
        if copied:
            print("  (URL copied to clipboard)")
        print(bar)
        print()
    else:
        print("[launcher] WARNING: did not detect a trycloudflare.com URL within 30s.")
        print("[launcher] cloudflared may still be starting; watch the [tunnel] lines above.")

    def _shutdown(signum=None, frame=None):
        print("\n[launcher] stopping subprocesses...")
        for p in (tunnel_proc, bridge_proc):
            if p.poll() is None:
                try:
                    if os.name == "nt":
                        p.terminate()
                    else:
                        p.send_signal(signal.SIGINT)
                except Exception:
                    pass
        for p in (tunnel_proc, bridge_proc):
            try:
                p.wait(timeout=5)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
        sys.exit(0)

    try:
        signal.signal(signal.SIGINT, _shutdown)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, _shutdown)
    except Exception:
        pass

    # Block forever until a subprocess dies or user Ctrl+C.
    try:
        while True:
            if bridge_proc.poll() is not None:
                print(f"[launcher] midi_bridge exited (code={bridge_proc.returncode}); stopping.")
                break
            if tunnel_proc.poll() is not None:
                print(f"[launcher] cloudflared exited (code={tunnel_proc.returncode}); stopping.")
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    _shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())

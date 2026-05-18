"""
midi_bridge.py — reads MIDI from the Yamaha CLP-885 (or any USB-MIDI piano) and
exposes a long-poll HTTP endpoint for Roblox HttpService to consume.

Endpoints:
  GET /poll?since=<id>&timeout=25 — long-poll. Blocks up to <timeout> seconds (max 28)
                                   until events with id > <since> arrive.
  GET /health                     — returns MIDI port info.

Event format returned by /poll:
  {
    "cursor": <last id>,
    "events": [
      {"id": N, "t": <ms relative to batch t0>, "type": "on|off|cc",
       "note": N, "vel": V}   # for on/off
       or
       {..., "type":"cc", "num": C, "val": V}
    ]
  }

CC numbers tracked: 64 (damper), 66 (sostenuto), 67 (soft).
Consecutive CC events on the same controller within a 10 ms window are coalesced
(only the last value is kept) to reduce stream pressure during pedal sweeps.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import mido

HOST = "127.0.0.1"
PORT = 8080
MAX_TIMEOUT_S = 28          # safely below Roblox HttpService 30s limit
TRACKED_CC = {64, 66, 67}   # damper, sostenuto, soft
CC_COALESCE_MS = 10
BUF_SOFT_CAP = 4096

_lock = threading.Lock()
_cv = threading.Condition(_lock)
_buf: list[dict] = []
_cursor = 0
_active_port_name: str | None = None


def _pick_port() -> str:
    names = mido.get_input_names()
    if not names:
        raise RuntimeError(
            "No MIDI input devices detected. Plug in the CLP-885 via USB and try again."
        )
    # Prefer obvious matches; fall back to first device.
    keywords = ("CLP", "Yamaha", "Piano", "Digital", "USB")
    for kw in keywords:
        for n in names:
            if kw.lower() in n.lower():
                return n
    return names[0]


def _now_ms() -> float:
    return time.time() * 1000.0


def _push(ev: dict) -> None:
    """Append an event under the lock; coalesce trailing CC of same controller."""
    global _cursor
    with _cv:
        # Coalesce: if last event in buffer is a CC of the same controller
        # arriving within CC_COALESCE_MS, overwrite its value rather than appending.
        if (
            ev.get("type") == "cc"
            and _buf
            and _buf[-1].get("type") == "cc"
            and _buf[-1].get("num") == ev["num"]
            and _now_ms() - _buf[-1]["wall_ms"] < CC_COALESCE_MS
        ):
            _buf[-1]["val"] = ev["val"]
            _buf[-1]["wall_ms"] = _now_ms()
            return
        _cursor += 1
        ev["id"] = _cursor
        ev["wall_ms"] = _now_ms()
        _buf.append(ev)
        if len(_buf) > BUF_SOFT_CAP:
            del _buf[: BUF_SOFT_CAP // 2]
        _cv.notify_all()


def _midi_loop() -> None:
    global _active_port_name
    while True:
        try:
            port_name = _pick_port()
            _active_port_name = port_name
            print(f"[midi] opening: {port_name}", flush=True)
            with mido.open_input(port_name) as port:
                for msg in port:
                    if msg.type == "note_on" and msg.velocity > 0:
                        _push({"type": "on", "note": msg.note, "vel": msg.velocity})
                    elif msg.type == "note_off" or (
                        msg.type == "note_on" and msg.velocity == 0
                    ):
                        _push({"type": "off", "note": msg.note, "vel": 0})
                    elif msg.type == "control_change" and msg.control in TRACKED_CC:
                        _push({"type": "cc", "num": msg.control, "val": msg.value})
        except Exception as exc:
            _active_port_name = None
            print(f"[midi] error: {exc!r}; retrying in 3s", flush=True)
            time.sleep(3.0)


def _slice_since(since: int) -> list[dict]:
    return [e for e in _buf if e["id"] > since]


def _serialize_batch(events: list[dict]) -> dict:
    if not events:
        return {"cursor": _cursor, "events": []}
    t0 = events[0]["wall_ms"]
    out_events = []
    for e in events:
        out = {"id": e["id"], "t": int(round(e["wall_ms"] - t0)), "type": e["type"]}
        if e["type"] in ("on", "off"):
            out["note"] = e["note"]
            out["vel"] = e["vel"]
        else:  # cc
            out["num"] = e["num"]
            out["val"] = e["val"]
        out_events.append(out)
    return {"cursor": _cursor, "events": out_events}


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # quiet default access log
        return

    def _send_json(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json(
                200,
                {
                    "ok": True,
                    "midi_in": _active_port_name,
                    "available": mido.get_input_names(),
                    "cursor": _cursor,
                },
            )
            return
        if parsed.path == "/poll":
            qs = parse_qs(parsed.query or "")
            try:
                since = int(qs.get("since", ["0"])[0])
            except ValueError:
                since = 0
            try:
                timeout = float(qs.get("timeout", ["25"])[0])
            except ValueError:
                timeout = 25.0
            timeout = max(0.1, min(MAX_TIMEOUT_S, timeout))
            deadline = time.monotonic() + timeout

            with _cv:
                while True:
                    pending = _slice_since(since)
                    if pending:
                        break
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    _cv.wait(timeout=remaining)
                batch = _serialize_batch(pending)
            self._send_json(200, batch)
            return
        self._send_json(404, {"error": "not_found", "path": parsed.path})


def main() -> None:
    print(f"[midi] available ports: {mido.get_input_names()}", flush=True)
    threading.Thread(target=_midi_loop, daemon=True).start()
    print(f"[http] listening on http://{HOST}:{PORT}", flush=True)
    print("[http] try:  curl http://127.0.0.1:8080/health", flush=True)
    ThreadingHTTPServer((HOST, PORT), _Handler).serve_forever()


if __name__ == "__main__":
    main()

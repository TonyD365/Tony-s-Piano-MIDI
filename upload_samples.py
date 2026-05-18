"""
upload_samples.py — upload the 6 anchor OGG files to Roblox via the Open Cloud
Assets API, then print a Lua snippet you can paste into PianoConfig.lua.

Prerequisites:
  1. A Roblox account with Premium (Audio uploads require Premium).
  2. An Open Cloud API key with the `asset:write` scope, created at
     https://create.roblox.com/dashboard/credentials
  3. Your numeric userId (or groupId if uploading on behalf of a group).
     Find userId at https://www.roblox.com/users/<name>/profile (URL contains it),
     or in Studio: print(game.Players.LocalPlayer.UserId).

Usage:
  python upload_samples.py --api-key <KEY> --user-id <ID>
  python upload_samples.py --api-key <KEY> --group-id <ID>

The script writes the resulting asset IDs to bridge/.cache/asset_ids.json and
emits a Lua snippet to stdout that you copy into
src/ReplicatedStorage/PianoLib/PianoConfig.lua.

Audio upload moderation can take seconds to minutes. The script polls until each
operation completes or times out (default 90 s/asset).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

API_BASE = "https://apis.roblox.com/assets/v1"
ANCHORS = ["A1", "A2", "A3", "A4", "A5", "A6"]

HERE = Path(__file__).resolve().parent
SOUNDS = HERE.parent / "assets" / "sounds"
CACHE = HERE / ".cache"


def _creation_context(user_id: int | None, group_id: int | None) -> dict:
    if user_id:
        return {"creator": {"userId": str(user_id)}}
    return {"creator": {"groupId": str(group_id)}}


def _upload_one(api_key: str, note: str, path: Path, ctx: dict, timeout_s: float) -> int:
    request_json = {
        "assetType": "Audio",
        "displayName": f"CLP885 Piano {note}",
        "description": "Salamander Grand Piano anchor sample (CC-BY Alexander Holm).",
        "creationContext": ctx,
    }
    files = {
        "request": (None, json.dumps(request_json), "application/json"),
        "fileContent": (path.name, path.read_bytes(), "audio/ogg"),
    }
    headers = {"x-api-key": api_key}
    print(f"[upload] POST {note} ({path.stat().st_size // 1024} KB)")
    r = requests.post(f"{API_BASE}/assets", headers=headers, files=files, timeout=60)
    if r.status_code >= 300:
        raise RuntimeError(f"upload {note} failed: HTTP {r.status_code}: {r.text[:400]}")
    op = r.json()
    op_path = op.get("path") or op.get("operationId")
    if not op_path:
        raise RuntimeError(f"unexpected upload response for {note}: {op}")

    # Poll the operation until done.
    op_url = f"https://apis.roblox.com/assets/v1/{op_path}" if not op_path.startswith("http") else op_path
    deadline = time.monotonic() + timeout_s
    while True:
        if time.monotonic() > deadline:
            raise TimeoutError(f"operation {op_path} did not complete in {timeout_s}s")
        time.sleep(2.0)
        pr = requests.get(op_url, headers=headers, timeout=30)
        if pr.status_code >= 300:
            raise RuntimeError(f"poll {note} failed: HTTP {pr.status_code}: {pr.text[:400]}")
        data = pr.json()
        if data.get("done"):
            resp = data.get("response") or {}
            asset_id = resp.get("assetId")
            if not asset_id:
                raise RuntimeError(f"completed op for {note} had no assetId: {data}")
            print(f"[upload] {note} -> rbxassetid://{asset_id}")
            return int(asset_id)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", required=True, help="Open Cloud API key with asset:write scope")
    parser.add_argument("--user-id", type=int, help="Roblox userId of the uploader (mutually exclusive with --group-id)")
    parser.add_argument("--group-id", type=int, help="Roblox groupId for group uploads")
    parser.add_argument("--timeout", type=float, default=90.0, help="Per-asset polling timeout in seconds")
    args = parser.parse_args(argv)

    if bool(args.user_id) == bool(args.group_id):
        print("ERROR: provide exactly one of --user-id or --group-id", file=sys.stderr)
        return 2

    missing = [n for n in ANCHORS if not (SOUNDS / f"piano_{n}.ogg").exists()]
    if missing:
        print(f"ERROR: missing local sample files: {missing}", file=sys.stderr)
        print("Run `python download_samples.py` first.", file=sys.stderr)
        return 2

    ctx = _creation_context(args.user_id, args.group_id)
    results: dict[str, int] = {}
    for note in ANCHORS:
        path = SOUNDS / f"piano_{note}.ogg"
        try:
            results[note] = _upload_one(args.api_key, note, path, ctx, args.timeout)
        except Exception as exc:
            print(f"ERROR on {note}: {exc}", file=sys.stderr)
            return 1

    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / "asset_ids.json").write_text(json.dumps(results, indent=2))
    print(f"[upload] wrote {CACHE / 'asset_ids.json'}")

    print("\n--- paste this into PianoConfig.lua under `Anchors = {`: ---")
    midi_for = {"A1": 33, "A2": 45, "A3": 57, "A4": 69, "A5": 81, "A6": 93}
    print("Anchors = {")
    for n in ANCHORS:
        print(f'    {{ note = "{n}", midi = {midi_for[n]}, assetId = "rbxassetid://{results[n]}" }},')
    print("},")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

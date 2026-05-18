# MIDI Bridge (CLP-885 → Roblox)

Reads MIDI from your Yamaha CLP-885 (or any USB-MIDI piano) and exposes a
long-poll HTTP endpoint that the Roblox game server consumes via
`HttpService:RequestAsync`. A free `cloudflared` quick tunnel makes the local
endpoint reachable from Roblox without a server, signup, or credit card.

## What's here

| File                  | Purpose |
|-----------------------|---------|
| `midi_bridge.py`      | Reads MIDI; serves `GET /poll` long-poll and `GET /health`. |
| `download_samples.py` | Downloads Salamander Grand Piano (Ogg) and extracts 6 anchor notes to `../assets/sounds/`. |
| `upload_samples.py`   | Uploads those 6 OGGs to Roblox via Open Cloud Assets API and prints a Lua snippet. |
| `run.sh` / `run.bat`  | One-click launchers: start the bridge + cloudflared, print/copy the public URL. |
| `requirements.txt`    | Python deps: `mido`, `python-rtmidi`, `requests`. |
| `.venv/`              | Local virtualenv (created by setup). |
| `.cache/`             | Downloaded SGP tarball + saved asset IDs. |

## First-time setup (macOS)

```bash
cd "Tony's Multifunctional Hall - Piano"
python3 -m venv bridge/.venv
bridge/.venv/bin/pip install -r bridge/requirements.txt
brew install cloudflared             # if not already installed
bridge/.venv/bin/python bridge/download_samples.py   # extracts 6 anchor OGGs
```

## Uploading audio to Roblox

Audio uploads require **Roblox Premium** on the uploading account. Once you have
Premium and have created an Open Cloud API key with the `asset:write` scope:

```bash
bridge/.venv/bin/python bridge/upload_samples.py \
    --api-key <YOUR_KEY> \
    --user-id <YOUR_NUMERIC_USERID>
```

The script prints a Lua snippet — paste it into the `Anchors = { ... }` block
in `src/ReplicatedStorage/PianoLib/PianoConfig.lua`.

If you'd rather upload by hand: go to
<https://create.roblox.com/dashboard/creations>, click "Audio", upload each of
the 6 OGGs in `assets/sounds/`, copy the asset IDs, and paste them into the
config manually.

## Running the live bridge

```bash
bash bridge/run.sh
```

This:
1. Starts `midi_bridge.py` (HTTP on `127.0.0.1:8080`).
2. Starts `cloudflared tunnel --url http://127.0.0.1:8080`.
3. Greps the tunnel log for `https://<random>.trycloudflare.com`.
4. Prints the URL and copies it to your clipboard.

Then in Roblox chat (as the admin UserId configured in
`PianoBridge_Admin`), run:

```
/pianourl https://<random>.trycloudflare.com
```

The URL is stored in a DataStore so subsequent server starts pick it up
automatically. You only need to re-run `/pianourl` after restarting the
tunnel (which gets a new random URL each time).

## Verifying without Roblox

With the bridge running:

```bash
curl http://127.0.0.1:8080/health
# {"ok":true,"midi_in":"Yamaha CLP-885 ...","cursor":0,...}

# Play a few notes on the CLP-885, then:
curl 'http://127.0.0.1:8080/poll?since=0&timeout=1'
# {"cursor":3,"events":[{"id":1,"t":0,"type":"on","note":60,"vel":92}, ...]}
```

## Troubleshooting

- **"No MIDI input devices detected"** — plug the CLP-885 into the computer
  via USB-B, power it on, and confirm with:
  ```bash
  bridge/.venv/bin/python -c "import mido; print(mido.get_input_names())"
  ```
- **`pip install` fails on `python-rtmidi`** — install `portaudio` first:
  `brew install portaudio` (macOS) or `apt install libasound2-dev` (Linux).
- **cloudflared URL keeps rotating** — quick tunnels regenerate URLs each
  restart. Sign up for free at <https://dash.cloudflare.com> and create a
  named tunnel for a stable URL.

"""
download_samples.py — download Salamander Grand Piano V3 (Ogg Vorbis edition)
and extract 6 anchor notes (A1..A6) to assets/sounds/ for upload to Roblox.

SGP V3 is by Alexander Holm, licensed CC-BY 3.0. Attribution is recorded in
assets/sounds/LICENSE.txt.

The tarball is already in OGG, so no transcoding is needed. We just untar,
locate the 6 anchor files at a chosen velocity layer, copy them to the right
names, and discard the rest.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

URL = "https://archive.org/download/SalamanderGrandPianoV3/SalamanderGrandPianoV3_OggVorbis.tar.bz2"
HERE = Path(__file__).resolve().parent
CACHE = HERE / ".cache"
OUT = HERE.parent / "assets" / "sounds"
ANCHORS = ["A1", "A2", "A3", "A4", "A5", "A6"]

# SGP V3 uses 16 velocity layers (v1..v16). v8 is mid-strong, a good sample
# for note-on events that we re-shape with Sound.Volume client-side.
PREFERRED_VEL = 8


def _download_if_needed() -> Path:
    CACHE.mkdir(exist_ok=True, parents=True)
    archive = CACHE / "sgp_ogg.tar.bz2"
    if archive.exists() and archive.stat().st_size > 50_000_000:
        print(f"[download] using cached {archive} ({archive.stat().st_size//1_000_000} MB)")
        return archive
    print(f"[download] fetching {URL}")
    tmp = archive.with_suffix(archive.suffix + ".part")
    with urllib.request.urlopen(URL, timeout=120) as resp, open(tmp, "wb") as f:
        shutil.copyfileobj(resp, f, length=1 << 20)
    tmp.rename(archive)
    print(f"[download] saved {archive} ({archive.stat().st_size//1_000_000} MB)")
    return archive


def _pick_member(members: list[tarfile.TarInfo], note: str) -> tarfile.TarInfo | None:
    """Pick the best velocity-layer file for `note` from the tar listing.

    SGP V3 file naming inside the OGG tarball:
        SalamanderGrandPianoV3/OggVorbis/A1v1.ogg ... A1v16.ogg
    Some velocity layers may be absent for some notes — fall back to the
    closest velocity that exists.
    """
    pat = re.compile(rf"{note}v(\d+)\.ogg$", re.IGNORECASE)
    candidates: list[tuple[int, tarfile.TarInfo]] = []
    for m in members:
        mt = pat.search(m.name)
        if mt:
            candidates.append((int(mt.group(1)), m))
    if not candidates:
        return None
    # Sort by closeness to preferred velocity, then prefer the higher layer.
    candidates.sort(key=lambda kv: (abs(kv[0] - PREFERRED_VEL), -kv[0]))
    return candidates[0][1]


def _write_license() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    license_text = (
        "Piano samples in this directory are from\n"
        "  Salamander Grand Piano V3 (OggVorbis edition)\n"
        "  by Alexander Holm — http://sfzformat.com/legacy/\n"
        "Licensed CC-BY 3.0: https://creativecommons.org/licenses/by/3.0/\n"
        "\n"
        f"Source: {URL}\n"
        "\n"
        "If you redistribute the Roblox experience using these samples, please\n"
        "credit Alexander Holm in your in-game credits or game description.\n"
    )
    (OUT / "LICENSE.txt").write_text(license_text, encoding="utf-8")


def main() -> int:
    archive = _download_if_needed()
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"[extract] opening {archive}")
    with tarfile.open(archive, "r:bz2") as tf:
        members = tf.getmembers()
        ogg_members = [m for m in members if m.isfile() and m.name.lower().endswith(".ogg")]
        print(f"[extract] tar contains {len(ogg_members)} ogg files")
        chosen: dict[str, tarfile.TarInfo] = {}
        for note in ANCHORS:
            m = _pick_member(ogg_members, note)
            if m is None:
                print(f"[extract] WARN: no sample found for {note}", file=sys.stderr)
                continue
            chosen[note] = m
            print(f"[extract] {note} -> {m.name} ({m.size//1024} KB)")
        for note, m in chosen.items():
            dest = OUT / f"piano_{note}.ogg"
            with tf.extractfile(m) as src, open(dest, "wb") as dst:
                shutil.copyfileobj(src, dst)
            print(f"[extract] wrote {dest} ({dest.stat().st_size//1024} KB)")
    _write_license()
    missing = [n for n in ANCHORS if n not in chosen]
    if missing:
        print(f"[extract] DONE with missing anchors: {missing}", file=sys.stderr)
        return 1
    print(f"[extract] DONE — 6 anchor files written to {OUT}")
    print("[next] upload them to Roblox (see bridge/upload_samples.py)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

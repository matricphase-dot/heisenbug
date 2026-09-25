#!/usr/bin/env python3
"""Mux each recorded segment with its narration, then concatenate to one MP4."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
VO = os.path.join(os.path.dirname(HERE), "voiceover")
PARTS = os.path.join(HERE, "parts")
FINAL = os.path.join(HERE, "heisenbug_demo.mp4")

PAIRS = [
    ("01_cold_open",   "01_cold_open.mp3"),
    ("02_why_rerun",   "02_why_rerunning_fails.mp3"),
    ("03_insight",     "03_the_insight.mp3"),
    ("04_live_run",    "04_live_run.mp3"),
    ("05_why_matters", "05_why_it_matters.mp3"),
    ("06_close",       "06_close.mp3"),
]


def run(args: list[str]) -> None:
    p = subprocess.run(args, capture_output=True, text=True)
    if p.returncode:
        print(p.stderr[-2500:])
        raise SystemExit(f"ffmpeg failed: {' '.join(args[:6])}…")


def duration(path: str) -> float:
    out = subprocess.run(
        [FFMPEG, "-i", path, "-hide_banner"], capture_output=True, text=True
    ).stderr
    for line in out.splitlines():
        if "Duration:" in line:
            h, m, s = line.split("Duration:")[1].split(",")[0].strip().split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    return 0.0


def main() -> int:
    os.makedirs(PARTS, exist_ok=True)
    listfile = os.path.join(PARTS, "concat.txt")
    entries = []

    print(f"{'segment':<16}{'video':>8}{'audio':>8}{'out':>8}")
    for vid, aud in PAIRS:
        vpath = os.path.join(RAW, f"{vid}.webm")
        apath = os.path.join(VO, aud)
        opath = os.path.join(PARTS, f"{vid}.mp4")
        vd, ad = duration(vpath), duration(apath)

        # Pad video with its last frame if the narration outruns it, so audio is
        # never clipped; then cut both to the audio length.
        run([
            FFMPEG, "-y", "-loglevel", "error",
            "-i", vpath, "-i", apath,
            "-filter_complex",
            f"[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
            f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30,tpad=stop_mode=clone:stop_duration=3[v]",
            "-map", "[v]", "-map", "1:a",
            "-t", f"{ad:.3f}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
            "-movflags", "+faststart",
            opath,
        ])
        od = duration(opath)
        print(f"  {vid:<14}{vd:>7.1f}s{ad:>7.1f}s{od:>7.1f}s")
        entries.append(opath)

    with open(listfile, "w") as fh:
        for e in entries:
            fh.write(f"file '{e}'\n")

    run([FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", listfile, "-c", "copy", "-movflags", "+faststart", FINAL])

    total = duration(FINAL)
    size = os.path.getsize(FINAL) / 1e6
    print(f"\nFINAL: {FINAL}")
    print(f"  duration {int(total//60)}:{total%60:05.2f}  ({total:.1f}s)")
    print(f"  size     {size:.1f} MB")
    print(f"  limit    3:00 -> {'OK' if total < 180 else 'OVER'}")
    return 0 if total < 180 else 1


if __name__ == "__main__":
    sys.exit(main())

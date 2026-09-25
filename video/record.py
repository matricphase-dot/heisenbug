#!/usr/bin/env python3
"""Record the Heisenbug demo video, segment by segment.

Each segment is captured at exactly the duration of its narration clip, so the
audio drops straight onto the timeline with no manual sync. Segments 3-6 record
the REAL deployed demo driving itself in a real browser.
"""

from __future__ import annotations

import glob
import os
import shutil
import sys

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
SCENES = os.path.join(HERE, "scenes")
OUT = os.path.join(HERE, "raw")
DEMO = os.environ.get("HB_DEMO_URL", "https://heisenbug-aditya-mehras-projects.vercel.app/")

W, H = 1920, 1080

# Durations come from the generated narration (voiceover/*.mp3), padded slightly
# so video never runs short under its audio.
SEGMENTS = [
    ("01_cold_open",   18.4),
    ("02_why_rerun",   20.8),
    ("03_insight",     37.0),
    ("04_live_run",    43.1),
    ("05_why_matters", 33.0),
    ("06_close",       22.5),
]


def record(name: str, seconds: float, drive) -> str:
    """Record one segment; `drive(page)` performs the on-screen actions."""
    d = os.path.join(OUT, name)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage",
                                    "--force-device-scale-factor=1"])
        ctx = b.new_context(viewport={"width": W, "height": H},
                            record_video_dir=d,
                            record_video_size={"width": W, "height": H},
                            device_scale_factor=1)
        pg = ctx.new_page()
        drive(pg, seconds)
        ctx.close()
        b.close()
    vids = glob.glob(os.path.join(d, "*.webm"))
    if not vids:
        raise RuntimeError(f"no video produced for {name}")
    final = os.path.join(OUT, f"{name}.webm")
    shutil.move(vids[0], final)
    shutil.rmtree(d, ignore_errors=True)
    print(f"  {name:<16} {seconds:>5.1f}s  {os.path.getsize(final)//1024:>6} KB")
    return final


# --- per-segment direction --------------------------------------------------

def s1(pg, secs):
    pg.goto("file://" + os.path.join(SCENES, "s1_terminal.html"))
    pg.wait_for_timeout(int(secs * 1000))


def s2(pg, secs):
    pg.goto("file://" + os.path.join(SCENES, "s2_diagram.html"))
    pg.wait_for_timeout(int(secs * 1000))


def _load_demo(pg):
    pg.goto(DEMO, wait_until="networkidle")
    pg.wait_for_function("() => !document.getElementById('go').disabled", timeout=30000)


def s3(pg, secs):
    """Idle UI while the narration explains the insight. Gentle highlight pass."""
    _load_demo(pg)
    pg.wait_for_timeout(2000)
    # Draw the eye down the page: banner -> thesis -> empty matrix.
    for sel in ("#capdate", ".thesis", "#matrix"):
        try:
            pg.locator(sel).first.scroll_into_view_if_needed(timeout=3000)
        except Exception:
            pass
        pg.wait_for_timeout(int((secs * 1000 - 2000) / 3))


def s4(pg, secs):
    """THE money shot: click Replay and let the matrix fill for real."""
    _load_demo(pg)
    pg.wait_for_timeout(1200)
    pg.click("#go")
    pg.wait_for_timeout(int(secs * 1000) - 1200)


def s5(pg, secs):
    """Run the replay, then scroll slowly through the finding cards."""
    _load_demo(pg)
    pg.click("#go")
    pg.wait_for_timeout(15500)          # let the replay complete
    fd = pg.locator("#findings")
    steps = 14
    per = max(int((secs * 1000 - 15500) / steps), 60)
    for i in range(steps):
        fd.evaluate("(e,i)=>e.scrollTop = e.scrollHeight * (i/14)", i + 1)
        pg.wait_for_timeout(per)


def s6(pg, secs):
    """Finished state, full matrix in frame."""
    _load_demo(pg)
    pg.click("#go")
    pg.wait_for_timeout(15500)
    pg.locator("#matrix").scroll_into_view_if_needed()
    pg.wait_for_timeout(int(secs * 1000) - 15500)


DRIVERS = {"01_cold_open": s1, "02_why_rerun": s2, "03_insight": s3,
           "04_live_run": s4, "05_why_matters": s5, "06_close": s6}


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    only = sys.argv[1:] or None
    print(f"Recording {W}x{H} from {DEMO}")
    for name, secs in SEGMENTS:
        if only and name not in only:
            continue
        record(name, secs, DRIVERS[name])
    print("done ->", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())

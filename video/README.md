# Demo video

`heisenbug_demo.mp4` — **2:50**, 1920×1080 @30fps, H.264 + AAC. 17 MB.
Under the hackathon's 3:00 limit with 10s to spare.

Segments 3–6 are a genuine browser recording of the deployed demo at
https://heisenbug-aditya-mehras-projects.vercel.app driving itself — not a mockup.

## Reproducing it

```bash
pip install playwright imageio-ffmpeg
python -m playwright install chromium
python video/record.py      # captures 6 segments to video/raw/
python video/assemble.py    # muxes narration, concatenates -> heisenbug_demo.mp4
```

`record.py` captures each segment at exactly the duration of its narration clip in
`../voiceover/`, so audio drops onto the timeline with no manual sync. `assemble.py`
pads any short segment with its final frame, then cuts to the audio length.

On a headless box without root you may need Chromium's shared libraries extracted
locally (`dpkg-deb -x` into a prefix, then `LD_LIBRARY_PATH`).

## Structure

| # | Segment | Duration | Content |
|---|---------|---------:|---------|
| 1 | cold open | 17.6s | Animated terminal: fail → retry → pass → fail |
| 2 | why re-running fails | 20.0s | Diagram: 100 runs from 100 different states |
| 3 | the insight | 36.2s | Live UI, banner and thesis |
| 4 | **the run** | 42.3s | **Real replay — matrix fills column by column** |
| 5 | why it matters | 32.2s | Scroll through the three class-specific patches |
| 6 | close | 21.7s | Finished matrix, full frame |

# Tests

## `test_classifier.py` — classification logic
```bash
python -m pytest tests/ -q
```
Pins the decision logic: monotonicity rejection, sampling-error guards, and that
more replicas convert marginal evidence into decisive evidence.

## `test_web_replay.js` — hosted demo smoke test
```bash
npm install jsdom
node tests/test_web_replay.js
```
Loads `web/index.html` in a headless DOM, stubs `fetch` with the captured session,
fires the replay, and asserts the matrix, finding cards and report all render with
**zero JS errors**.

This exists because an earlier build shipped with `addLog`/`renderMatrix` accidentally
stripped out — the page returned HTTP 200 and looked fine to `curl`, but the replay
threw `ReferenceError` on every event. Checking status codes and grepping for strings
is not enough; the script has to actually run.

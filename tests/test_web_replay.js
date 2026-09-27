/**
 * Headless smoke test for the hosted replay demo.
 *
 *   node tests/test_web_replay.js            # test the local build in web/
 *   node tests/test_web_replay.js --live     # test the deployed site
 *
 * Loads the page in a real DOM, stubs fetch with the captured session, fires the
 * replay, and asserts the matrix, finding cards and Ultra report all render with
 * zero JS errors.
 *
 * This exists because an earlier build shipped with addLog()/renderMatrix()
 * accidentally stripped out. The page returned HTTP 200 and looked fine to curl,
 * but every replay event threw ReferenceError. Status codes and grepping for
 * strings are not enough — the script has to actually run.
 */

const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");
const https = require("https");

const LIVE_URL = "https://heisenbug-aditya-mehras-projects.vercel.app/";
const useLive = process.argv.includes("--live");
const root = path.join(__dirname, "..");

function get(url) {
  return new Promise((res, rej) => {
    https.get(url, r => { let d = ""; r.on("data", c => d += c); r.on("end", () => res(d)); })
         .on("error", rej);
  });
}

async function load() {
  if (useLive) {
    return {
      html: await get(LIVE_URL),
      session: JSON.parse(await get(LIVE_URL + "session.json")),
      label: "LIVE " + LIVE_URL,
    };
  }
  return {
    html: fs.readFileSync(path.join(root, "web/index.html"), "utf8"),
    session: JSON.parse(fs.readFileSync(path.join(root, "web/session.json"), "utf8")),
    label: "LOCAL web/index.html",
  };
}

(async () => {
  const { html, session, label } = await load();
  const errors = [];
  const dom = new JSDOM(html, {
    runScripts: "dangerously",
    pretendToBeVisual: true,
    url: LIVE_URL,
    beforeParse(w) {
      w.fetch = () => Promise.resolve({ json: () => Promise.resolve(session) });
      w.addEventListener("error", e => errors.push(e.message));
    },
  });
  process.on("uncaughtException", e => errors.push("uncaught: " + e.message));

  console.log("target:", label);

  setTimeout(() => {
    const d = dom.window.document;
    const btn = d.getElementById("go");
    if (!btn) { console.log("FAIL: no #go button"); process.exit(1); }
    btn.onclick();

    setTimeout(() => {
      const rows = d.getElementById("matrix").querySelectorAll("tbody tr").length;
      const cards = d.getElementById("findings").querySelectorAll(".card").length;
      const report = d.getElementById("findings").querySelectorAll(".report").length;
      const logs = d.getElementById("log").children.length;

      console.log(`  matrix rows   : ${rows}  (expect 5)`);
      console.log(`  finding cards : ${cards}  (expect 3)`);
      console.log(`  ultra report  : ${report}  (expect 1)`);
      console.log(`  log lines     : ${logs}  (expect >15)`);
      console.log(errors.length ? "  JS ERRORS: " + errors.join("; ") : "  no JS errors");

      const ok = rows === 5 && cards === 3 && report === 1 && logs > 15 && !errors.length;
      console.log(ok ? "\nPASS" : "\nFAIL");
      process.exit(ok ? 0 : 1);
    }, 17000);
  }, 900);
})();
